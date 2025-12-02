# SSR Strategy Codex

A local-first dashboard for Semantic Similarity Rating (SSR) experiments that mirror the paper “LLMs Reproduce Human Purchase Intent via Semantic Similarity Elicitation of Likert Ratings.” Researchers and marketers can register personas and criteria, apply prompt templates, enqueue SSR tasks with operational context, and export JSON, PDF, and Codex session artifacts for reproducible analysis.

## Features
- **Shoelace-powered UI** with glassy panels, pill tags, and modern form controls.
- **Personas & criteria**: manage demographic personas and Likert-scale anchors, then attach them to tasks.
- **Prompt templates**: store evaluation prompts that can be injected per task.
- **Task queue**: enqueue SSR tasks with text/image stimuli, operational context, similarity strategy, and random seed.
- **Reports**: download PDF summaries, view persona-level aggregates, and export raw `~/.codex/session/...` files.
- **Benchmarks**: record human distributions, compute KS similarity, and show correlation attainment versus paper targets.
- **Live overview**: command bar to jump between flows plus live persona/template/task counters.

## Requirements
- Python 3.11+
- Local Codex CLI authentication (expects `~/.codex/auth.json` to exist). For testing, decode the `Codex_Auth_Json` secret and place it at `~/.codex/auth.json`.

## Setup
1. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
2. Run the FastAPI server:
   ```bash
   uvicorn app.main:app --reload
   ```
3. Open `http://localhost:8000` in a browser. Use **Quick setup** to load sample personas, criteria, and templates.

## Codex exec (gpt-5.1) モード

- デフォルト手法は `codex`。バックエンドが `codex exec --model gpt-5.1 --sandbox read-only --color never --output-last-message <tmp>` を呼び出し、生成された自然文からアンカー5文へのTF-IDFコサイン類似度で分布を計算し、最頻値をratingとします（分布はCodex出力に依存せずローカルで計算）。
- 画像を添付した場合は一時ファイルへデコードして `--image` で渡します。
- Codexが生成するセッションJSONLは `~/.codex/sessions/<year>/<month>/<day>/...jsonl` に保存され、`/api/sessions` から列挙・ダウンロードできます。アプリ側で独自セッションJSONは生成しません。
- Codex execがエラーの場合のみタスクを失敗扱いとし、必要に応じて `tfidf`/`uniform` 手法を明示的に選択してください。

## 計算 (docs/2510.08338v3 に基づく要約)

- SSRは自由記述をアンカー文との意味類似度に写像し、Likert 5件法の分布を得る手法。論文では埋め込みのコサイン類似度を用い、KS類似度と相関達成度で人間データに近さを評価。
- 本実装では Codex(gpt-5.1) でペルソナ・評価基準・運営コンテキストを含む自由記述を生成し、そのテキストをアンカー5文に対するTF-IDFコサインで正規化した分布へ変換します。ratingは分布の最頻値(1-5)です。
- ヒューマンベンチマークとの比較には KS類似度と相関達成度(correlation attainment)を計算し、PDFでは分布バーとアンカー、年齢/性別別平均を併記します。

## テスト用認証情報

環境シークレット `Codex_Auth_Json` に `~/.codex/auth.json` がBase64で格納されています。必要なら以下で復元してください。

```bash
mkdir -p ~/.codex
echo "$Codex_Auth_Json" | base64 -d > ~/.codex/auth.json
```

## Usage tips
- Upload an image or provide a short description to enrich the stimulus text; both are sent to the SSR worker.
- Choose **Similarity strategy** (`codex` = gpt-5.1 via codex exec, or `tfidf` / `uniform`) and optionally fix a **Seed** for reproducibility.
- Download PDF reports or the raw session files for offline inspection and paper-aligned evaluation.

## Project structure
- `app/`: FastAPI application, models, jobs, evaluation, and PDF report generation.
- `static/`: JavaScript and CSS for the dashboard experience.
- `templates/`: Jinja2 templates for the HTML shell.
- `docs/`: Reference papers and supporting materials about SSR.
