"""Inference through the server's OpenAI-compatible model endpoint."""
import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

PLAMO_MODEL = "plamo-3-translate"
DEFAULT_MODEL = PLAMO_MODEL


class LocalLLMError(RuntimeError):
    pass


class LocalLLM:
    def __init__(self, model=None):
        self.model = model or os.environ.get("LLM_MODEL") or DEFAULT_MODEL
        default_base = (
            "http://127.0.0.1:18000/v1" if self.translation_only else "http://127.0.0.1:8000/v1"
        )
        self.base_url = (os.environ.get("LLM_BASE_URL") or default_base).rstrip("/")
        self.api_key = os.environ.get("LLM_API_KEY")
        self.timeout = int(os.environ.get("LLM_TIMEOUT_SECONDS", "300"))

    @property
    def translation_only(self):
        return self.model == PLAMO_MODEL

    def _request(self, path, payload=None):
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(self.base_url + path, data=body, headers=headers)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except HTTPError as exc:
            raise LocalLLMError(f"Local LLM {path}: HTTP {exc.code}") from None
        except (OSError, ValueError) as exc:
            raise LocalLLMError(f"Local LLM {path}: {type(exc).__name__}") from None

    def check_model(self):
        response = self._request("/models")
        try:
            models = {model["id"] for model in response["data"]}
        except (KeyError, TypeError):
            raise LocalLLMError("Local LLM returned an invalid model list") from None
        if self.model not in models:
            raise LocalLLMError(f"Configured local model is not available: {self.model}")

    def check_article_model(self):
        if self.translation_only:
            raise LocalLLMError(
                "日次公開には論文を統合・要約できるモデルが必要です。"
                "LLM_MODEL と LLM_BASE_URL に Gemma 4 などを設定してください。"
            )
        self.check_model()

    def generate(self, system, user, max_tokens=None):
        if self.translation_only:
            raise LocalLLMError("PLaMo Translate is translation-only. Set LLM_MODEL to an instruction model for questions.")
        return self._complete({
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens or 8192,
            "temperature": 0.2,
        })

    def translate_to_japanese(self, text):
        return self._complete({
            "messages": [{"role": "user", "content": text}],
            "chat_template_kwargs": {"source_lang": "en", "target_lang": "ja"},
            "max_tokens": 2048,
            "temperature": 0,
        })

    def _complete(self, payload):
        response = self._request("/chat/completions", {"model": self.model, **payload})
        try:
            choice = response["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise LocalLLMError("Local LLM returned an invalid chat response") from None
        if choice.get("finish_reason") == "length":
            raise LocalLLMError("Local LLM reached the output token limit")
        if not isinstance(content, str) or not content.strip():
            raise LocalLLMError("Local LLM returned empty content")
        return content
