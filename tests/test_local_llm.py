import io
import json
import unittest
from unittest import mock
from urllib.error import HTTPError

from pipeline.local_llm import LocalLLM, LocalLLMError


class LocalLLMTests(unittest.TestCase):
    @mock.patch("pipeline.local_llm.urlopen")
    @mock.patch.dict("os.environ", {
        "LLM_MODEL": "gemma",
        "LLM_BASE_URL": "http://127.0.0.1:8001/v1/",
        "LLM_API_KEY": "test-key",
        "LLM_TIMEOUT_SECONDS": "15",
    })
    def test_checks_exact_model_and_sends_separate_messages(self, urlopen):
        urlopen.side_effect = [
            io.BytesIO(b'{"data":[{"id":"gemma"}]}'),
            io.BytesIO(json.dumps({
                "choices": [{"message": {"content": "日本語の要約"}, "finish_reason": "stop"}],
            }).encode()),
        ]
        llm = LocalLLM()
        llm.check_model()
        self.assertEqual(llm.generate("要約してください", "Paper evidence."), "日本語の要約")

        models, chat = urlopen.call_args_list
        self.assertEqual(models.args[0].full_url, "http://127.0.0.1:8001/v1/models")
        request = chat.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:8001/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        self.assertEqual(chat.kwargs["timeout"], 15)
        payload = json.loads(request.data)
        self.assertEqual(payload["model"], "gemma")
        self.assertEqual(payload["messages"], [
            {"role": "system", "content": "要約してください"},
            {"role": "user", "content": "Paper evidence."},
        ])

    @mock.patch("pipeline.local_llm.urlopen")
    def test_rejects_unavailable_model_and_http_error(self, urlopen):
        llm = LocalLLM(model="gemma")
        urlopen.return_value = io.BytesIO(b'{"data":[{"id":"plamo-3-translate"}]}')
        with self.assertRaisesRegex(LocalLLMError, "not available: gemma"):
            llm.check_model()

        urlopen.side_effect = HTTPError(llm.base_url, 503, "Unavailable", {}, None)
        with self.assertRaisesRegex(LocalLLMError, "HTTP 503"):
            llm.generate("system", "user")

    @mock.patch("pipeline.local_llm.urlopen")
    @mock.patch.dict("os.environ", clear=True)
    def test_plamo_uses_the_translation_chat_template(self, urlopen):
        urlopen.return_value = io.BytesIO(
            '{"choices":[{"message":{"content":"翻訳です。"},"finish_reason":"stop"}]}'.encode()
        )
        llm = LocalLLM()
        self.assertEqual(llm.translate_to_japanese("An English sentence."), "翻訳です。")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:18000/v1/chat/completions")
        payload = json.loads(request.data)
        self.assertEqual(payload["model"], "plamo-3-translate")
        self.assertEqual(payload["messages"], [{"role": "user", "content": "An English sentence."}])
        self.assertEqual(payload["chat_template_kwargs"], {"source_lang": "en", "target_lang": "ja"})
        with self.assertRaisesRegex(LocalLLMError, "論文を統合・要約できるモデル"):
            llm.check_article_model()
        with self.assertRaisesRegex(LocalLLMError, "translation-only"):
            llm.generate("Provide an answer.", "A question.")
        self.assertEqual(urlopen.call_count, 1)

    @mock.patch.object(LocalLLM, "translate_to_japanese")
    @mock.patch.dict("os.environ", clear=True)
    def test_builds_an_english_excerpt_article_and_translates_populated_fields(self, translate):
        from pipeline.schema import Paper
        from pipeline.summarize import Summarizer

        paper = Paper(source="arxiv", title="Warehouse planning", abstract=(
            "The multi-agent pathfinding problem requires planning collision-free routes for warehouse robots. "
            "We propose a priority inheritance algorithm for fleets working in narrow warehouse aisles."
        ))
        method = "The planner assigns new reservations by visiting each reachable cell in priority order."
        result = "The planner solved all 200 warehouse cases while retaining the original routing requirements."
        sections = [("Method", method), ("Evaluation", result)]
        translate.side_effect = lambda passage: {
            paper.title: "倉庫の経路計画",
            paper.abstract.split(". ")[0] + ".": "倉庫ロボットが衝突を避ける経路を計画する問題です。",
            paper.abstract.split(". ")[1]: "狭い通路で働くロボット向けに優先度継承を提案します。",
            method: "到達可能なセルを優先順に訪問して新しい予約を割り当てます。",
            result: "経路条件を維持して倉庫の200件すべてを解決しました。",
        }[passage]
        articles = Summarizer().summarize_bilingual(paper, sections, "fulltext(pdf)")

        self.assertEqual(articles["ja"]["title"], "倉庫の経路計画")
        self.assertEqual(articles["en"]["method"], method)
        self.assertEqual(articles["en"]["validation"], result)
        self.assertIn("200件", articles["ja"]["validation"])
        self.assertEqual(articles["ja"]["_engine"], "local-llm:plamo-3-translate")
