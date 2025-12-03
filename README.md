# SSR Strategy Codex

ローカル環境でSemantic Similarity Rating (SSR) 実験を行うダッシュボードです。論文「LLMs Reproduce Human Purchase Intent via Semantic Similarity Elicitation of Likert Ratings」の流れを再現し、ペルソナ・評価基準・プロンプトテンプレートを登録してタスクをキュー実行し、PDFやCodexセッションファイルを取得できます。

## 主な機能
- **UI**: Shoelaceベースのガラス風パネルとモダンなフォーム。
- **ペルソナ／評価基準**: 年代・性別などのペルソナとLikertアンカーを管理し、タスクに紐付け。
- **プロンプトテンプレート**: 評価用プロンプトを保存しタスクごとに適用。
- **タスクキュー**: テキスト／画像刺激と運営コンテキストを指定し、類似度手法やSeedを設定してSSRを実行（Codex exec または tfidf/uniform）。
- **レポート**: PDFで詳細レポートとサマリーを生成。`~/.codex/session/...` のセッションJSONLを列挙・ダウンロード可能。
- **ベンチマーク**: 人間分布を登録し、KS類似度・相関達成度を表示。
- **ライブカウンタ**: ペルソナ／テンプレート／タスク数を即時把握。

## 前提
- Python 3.11+
- Codex CLI にログイン済み（`~/.codex/auth.json` が存在）。テスト用には環境シークレット `Codex_Auth_Json` をBase64デコードして配置できます。

## セットアップ
```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 開発サーバー起動
```bash
uvicorn app.main:app --reload
```
ブラウザで `http://localhost:8000` を開き、Quick setup でサンプルデータをロードしてください。

## Codex exec (gpt-5.1) モード
- 既定の類似度手法は `codex`。`codex exec --model gpt-5.1` を呼び出し、生成された自由記述をローカルTF-IDFでアンカー5文に写像し分布と最頻値ratingを算出します。
- 画像入力があれば一時ファイルに展開し `--image` で渡します。
- セッションJSONLは `~/.codex/sessions/<year>/<month>/<day>/...jsonl` に保存され、アプリが列挙・ダウンロードを提供します。独自JSONは生成しません。
- Codex失敗時のみタスクを失敗扱いにし、必要なら `SSR_METHOD=tfidf` などを明示してください。

## 計算の要点（docs/2510.08338v3 準拠）
- SSRは自由記述をアンカー文との意味類似度に写像し、5件法分布を得て最頻値をratingとする。
- 本実装では Codex(gpt-5.1) でペルソナ・評価基準・運営コンテキスト込みの自由記述を生成し、TF-IDFコサイン類似度で分布化。評価指標はKS類似度と相関達成度。
- PDFには分布バー、アンカー、年齢／性別集計を記載。

## テスト用認証復元
```bash
mkdir -p ~/.codex
echo "$Codex_Auth_Json" | base64 -d > ~/.codex/auth.json
```

## 使い方のヒント
- 画像または短い説明文を刺激として渡すと評価が具体化しやすいです。
- 類似度手法（`codex` / `tfidf` / `uniform`）と Seed を指定すると再現性が確保できます。
- PDFやセッションファイルをダウンロードしてオフライン評価や論文再現に利用できます。

## ディレクトリ構成
- `app/` : FastAPI本体、モデル、ジョブ、評価、レポート生成。
- `static/` : JS/CSS。
- `templates/` : Jinja2テンプレート。
- `docs/` : SSR関連文献。
- `reports/` : 生成されたPDFとtex。
- `samples/` : サンプル画像とペルソナMarkdown。
