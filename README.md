# survey-mapf — MAPF Paper Survey

[論文サーベイサイト](https://abigworld1.github.io/survey-mapf/)

サーバーの cron が毎日 **06:00 JST** にMAPF論文を検索し、未処理の論文を **最大2本**、原文から抜粋してローカルの PLaMo で日本語に翻訳します。検証済みの記事をサーバーから `main` にpushすると、GitHub Actionsが静的サイトをビルドし、GitHub Pagesへ公開します。

## サーバー設定

既定では、このサーバーで稼働中の `plamo-3-translate` を使います。接続先を変更する場合はリポジトリ直下の `.env` で上書きできます。

```dotenv
LLM_BASE_URL=http://127.0.0.1:18000/v1
LLM_MODEL=plamo-3-translate
# 認証が必要なローカルAPIの場合は LLM_API_KEY を設定
```

`LLM_TIMEOUT_SECONDS` の既定値は300秒です。サーバー運用アカウントで `.venv` を作成し、`requirements.txt` をインストールしてください。cronからのpushには `main` に書き込めるGit認証と、Gitのユーザー名・メールアドレスが必要です。

```cron
0 6 * * * /bin/bash /home/hirayama/survey-app/deploy/run-daily.sh >> /home/hirayama/survey-app/cron.log 2>&1
```

cronのタイムゾーンは **Asia/Tokyo** を想定します。手動確認は `bash deploy/run-daily.sh --dry-run` で候補と本文を確認できます。引数なしで起動すると `.env` を読み込み、設定モデルが利用可能か確認してから生成・公開します。日次ジョブと手動の本番ジョブの重複は `flock` で防ぎます。

GitHub Pagesの公開元は **GitHub Actions** を選択してください。`Publish MAPF survey` は `main` へのpushと手動起動に対応します。

## 要約と検証

PLaMo は翻訳モデルです。Survey が問題設定・手法・検証・限界などに該当する英文を論文から選び、PLaMo に英日翻訳を依頼します。英語版は選んだ原文、日本語版はその訳文です。抽出できなかった詳細項目はその旨を表示し、既存の本文・記事品質チェックを通過した日英ペアを保存します。APIの接続エラー時はその回の翻訳を停止し、先に完了した記事を保存します。

## 長文・本文品質

既存のarXiv HTML → ar5iv → arXiv PDF → OA PDF取得を再利用します。日次公開は本文が取れた論文だけに限定し、abstractしかない場合は推論せず次候補を探します。

`pipeline/evidence.py` で参考文献・謝辞・ナビゲーション・フッター・HTMLタグ・重複文を除去し、method/experiments/results/conclusionを優先してセクションごとに抜粋します。長い節では冒頭だけでなく数値・結果・限界と末尾も残します。本文抜粋の上限は既定で24,000文字（`LLM_CONTEXT_CHARS`）かつ60,000 UTF-8バイトです。要約の根拠は選択した本文抜粋であり、全文すべての事実確認ではありません。

Pythonで内容重複や品質不足を検出し、公開前にチェックします。生成テキストは既存rendererでHTMLエスケープします。原典URLはモデル出力から採用せず、取得済みメタデータから生成します。

## 履歴・公開・障害復旧

永続データは従来どおり `data/seen.json` と記事HTMLです。DOI、バージョンを除いたarXiv ID、正規化タイトルを全分野の履歴と照合します。上位2本を切り出す前に既処理を除き、深い候補プールから選びます。本文取得は1実行で最大12候補です。新着1本＋重要1本という既存の選定を維持します。関連候補内では本文リンクのある論文を優先し、取得不能な高適合候補だけで待ち続けないようにします。1日あたりの件数はJSTの日付で数えます。

日本語記事・英語記事・seenはatomic writeし、検証済みの1論文分が揃ってからcheckpointを保存します。過去のseenレコードと記事の削除・上書き、英語版の欠落、旧カテゴリへの新規記事、スタブ公開、1日2論文超過を公開前に拒否します。

サーバーは公開バリデータを通った生成ファイルだけをcommitします。Git pushに失敗した場合、commit済みの結果はサーバーの `main` に残り、次の実行で再送します。競合が発生したらGitの状態を確認して解消してください。

Pagesのビルドに含まれるのは公開HTMLと実行レポートです。

## ローカル検証

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m compileall -q pipeline tests ask.py add-pdfs.py
python -m unittest discover -s tests -q
bash deploy/run-daily.sh --dry-run
python -m pipeline.run --render-indexes-only
python -m pipeline.publish build /tmp/survey-pages-preview
```

最後の出力先は空ディレクトリを指定します。テストは一時ディレクトリとmockを使い、論文履歴を変更しません。`--render-indexes-only` は既存の一覧HTMLを更新します。`--offline` / `--stub` は開発用で、生成物は公開バリデータが拒否します。本番作業ディレクトリではdry runを使ってください。

PDFの手動追加や既存記事の再生成にも PLaMo を利用できます。既存記事への追加質問や指示に従った要約・事実確認を使う場合は、Gemma 4 などの指示応答モデルの API を用意し、`LLM_BASE_URL` と `LLM_MODEL` を指定してください。日次スクリプト以外では、必要な設定を環境変数で渡します。
