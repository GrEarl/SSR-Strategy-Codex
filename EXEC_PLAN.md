# SSRローカル分析Webアプリの設計と実装

このExecPlanは生きた文書であり、作業の進行に合わせて`Progress`、`Surprises & Discoveries`、`Decision Log`、`Outcomes & Retrospective`を更新する。リポジトリ直下の`.agent/PLANS.md`の規約に従って維持する。

## Purpose / Big Picture

消費者調査の代替として、論文「LLMs Reproduce Human Purchase Intent via Semantic Similarity Elicitation of Likert Ratings」で示されるSemantic Similarity Rating(SSR)手法をローカルで再現できるWebアプリを提供する。ユーザーはペルソナと評価基準を登録し、画像またはテキストの刺激を与えてSSR分析を実行できる。Codex execのようにAPIに依存せずローカルで完結し、年齢・性別別の集計やセッションファイルのダウンロードが可能になる。最新の改修では、ソーシャルゲーム運営戦略の評価やPDFレポート出力、簡単セットアップ、論文再現性向上のための設定を強化する。

## Progress

- [x] (2025-02-26 13:30Z) 初期ExecPlan作成。リポジトリ構造と論文の概要を確認。
- [x] (2025-02-26 14:20Z) SQLModelによるDBスキーマ、SSR類似度計算(TF-IDF+コサイン)、キュー/セッション管理の骨格を実装。
- [x] (2025-02-26 14:40Z) FastAPIエンドポイントとフロントエンド(UI, Chart.js, 画像Base64送信)を組み込み、SSRタスク実行フローを結合。
- [x] (2025-02-26 14:55Z) 依存インストールと`python -m compileall app`による構文検証を実施。手動検証はサーバ起動手順に委ねる。
- [x] (2025-02-27 10:10Z) ソーシャルゲーム運営向けの運営コンテキスト入力、プロンプトテンプレート管理、PDFレポート出力、サンプルデータ投入API、再現性設定(シード・計算手法)を追加し、UIを拡充。

## Surprises & Discoveries

- reportlabの日本語出力にはCIDフォント登録が必要なため、標準のHeiseiKakuGo-W5を登録してPDF生成を安定化させた。

## Decision Log

- Decision: 実装基盤にFastAPI+SQLite(SQLModel)とシンプルなフロントエンド(JS+Chart.js)を採用し、外部API不要のテキスト類似度(TF-IDFコサイン)でSSRを模倣する。
  Rationale: Python標準と軽量依存でローカル実行が容易。論文のSSRは埋め込み類似度を用いるため、TF-IDFコサインで代替する。
  Date/Author: 2025-02-26/assistant
- Decision: ソーシャルゲーム運営評価のため、タスクに運営コンテキスト(JSON)とプロンプトテンプレートIDを付与し、シード指定・類似度手法切替を許容する。
  Rationale: 再現性(論文追試)と運営シナリオごとの評価を両立し、研究者とマーケターが任意条件で予測生成できるようにする。
  Date/Author: 2025-02-27/assistant

## Outcomes & Retrospective

- SSRダッシュボードのフロント/バックエンドとジョブキューが整備され、ペルソナ・評価基準管理からセッションファイル生成まで一連の動線を構築した。構文検証は通過済み。今後は実サーバ起動での手動動作確認を行い、フィードバックに応じてUI/指標を磨く。
- 運営コンテキストとPDFレポート出力により、ソーシャルゲーム施策の比較検証が行いやすくなった。引き続きモデル改善や実データ検証で精度を高める。

## Context and Orientation

リポジトリには`docs/2510.08338v3.md`としてSSR手法の論文全文があり、Likertスケールとアンカー文を用いた類似度マッピングが核心となる。現状アプリコードは存在しないため、API、データモデル、UIを新規に構築する。主要な要件は以下：
- ペルソナ(名前、年齢、性別、属性メモ)の登録・一括選択。
- 評価基準(ラベル、質問文、アンカーセット)管理。
- テキスト/画像入力からSSRを実行し、分布・レポート生成。
- Codex exec同等の同期処理を模したキュー管理とセッションファイル保存(~/.codex/session/<year>/<month>/<day>/)。
- 年齢・性別別の評価レポートとグラフ。
- ソーシャルゲーム運営戦略に必要なコンテキスト入力とPDFレポート出力。

## Plan of Work

1. **環境/基盤整備**: Python依存( fastapi, uvicorn, sqlmodel, scikit-learn, python-multipart, jinja2, reportlab )を`requirements.txt`に定義。`app/`配下にFastAPIエントリ`main.py`、データモデル`models.py`、SSRロジック`ssr.py`、キュー/セッション管理`jobs.py`、PDF生成`reports.py`を配置。`templates/`と`static/`でUIを提供。
2. **データモデルとSSRエンジン**: SQLiteファイル`app.db`に`Persona`、`Criterion`、`PromptTemplate`、`Task`、`Result`テーブルを定義。タスクへ運営コンテキスト(JSON)、プロンプトテンプレート参照、シード値、類似度手法を格納し、TF-IDFコサインを中心に分布計算を行う。
3. **ジョブ/キュー処理**: `asyncio.Queue`で直列処理。タスク処理時に運営コンテキストとテンプレートをプロンプトへ統合し、結果を保存。完了時に`~/.codex/session/<year>/<month>/<day>/task-<id>.json`へリクエストと結果を保存し、PDF生成に必要な情報を保持。
4. **APIとUI**: FastAPIでCRUDエンドポイント(ペルソナ、評価基準、プロンプトテンプレート、タスク作成、結果取得、集計取得、セッション閲覧/ダウンロード、PDFレポート)を提供。テンプレートでは運営コンテキスト入力、テンプレート選択、PDFダウンロードボタン、サンプルデータ投入を追加し、研究者/マーケターが直感的に任意条件で予測生成できるようにする。
5. **バリデーションと運用**: `uvicorn app.main:app --reload`で起動し、基本シナリオ(サンプル投入→ペルソナ/基準確認→運営コンテキスト付きタスク送信→PDFダウンロード)を確認。`python -m compileall app`で構文チェック。

## Concrete Steps

- 依存を更新し、reportlabで日本語PDFを生成できるようにする。
- モデルへ`PromptTemplate`とタスクの運営コンテキスト/シード/類似度手法を追加する。
- SSRロジックに運営文脈を組み込んだ応答生成と計算手法切替を実装する。
- ジョブ処理でテンプレート・コンテキスト統合とセッション書き出しを拡張し、PDF生成ユーティリティを実装する。
- API/UIを拡張し、テンプレート管理、コンテキスト入力、サンプル投入、PDFダウンロードをサポートする。

## Validation and Acceptance

- `uvicorn app.main:app --reload`でサーバを起動し、サンプル投入後にソーシャルゲーム運営シナリオを入力してタスク送信し、結果とPDFレポートが取得できること。
- 年齢・性別別平均スコアの棒グラフが更新されること。
- `~/.codex/session/<year>/<month>/<day>/task-<id>.json`が生成され、ダウンロードエンドポイントから取得できること。
- `python -m compileall app`がエラーなく完了すること。

## Idempotence and Recovery

- DB初期化は既存テーブルを保持しつつ不足テーブルのみ作成するため再実行可能。新規カラムは既存DBでは追加されないため、必要に応じてDB再作成を推奨する。キューはプロセス起動毎に空になるが既存タスクの`status`が`pending`であれば再投入できる。
- セッションファイル保存はタスク完了時に上書きされる。PDFは都度生成されるため破損しにくい。失敗タスクは`failed`でマークし、エラーメッセージを保持する。

## Artifacts and Notes

- SSRアンカー文は論文のLikertスケールを反映し、購入意向の強弱を表す5文を`ssr.py`に定義する。運営シナリオ向け補助アンカーもUIで編集可能。
- Chart.jsはCDNロードとし、追加インストール不要。
- reportlabのCIDフォント`HeiseiKakuGo-W5`を登録し、日本語PDFを生成する。

## Interfaces and Dependencies

- 主要依存: `fastapi`, `uvicorn`, `sqlmodel`, `scikit-learn`, `python-multipart`, `jinja2`, `reportlab`。
- API概要:
    - `POST /api/personas`, `GET /api/personas`, `DELETE /api/personas/{id}`。
    - `POST /api/criteria`, `GET /api/criteria`, `DELETE /api/criteria/{id}`。
    - `POST /api/prompt-templates`, `GET /api/prompt-templates`, `DELETE /api/prompt-templates/{id}`。
    - `POST /api/tasks` (payload: テキスト/画像Base64、説明、選択ペルソナID配列、評価基準ID配列、評価指示、セッション名、運営コンテキスト、プロンプトテンプレートID、シード値、類似度手法)。
    - `GET /api/tasks`, `GET /api/tasks/{id}`で結果と分布を返す。`GET /api/tasks/{id}/report`でPDFを返す。
    - `POST /api/tasks/{id}/enqueue`で未処理タスクを再キュー。
    - `GET /api/aggregates`で年齢・性別別平均スコアとサンプル数。
    - `GET /api/sessions`でセッションファイル一覧、`GET /api/sessions/{path}`でダウンロード。
    - `POST /api/bootstrap`でサンプルデータ投入。
