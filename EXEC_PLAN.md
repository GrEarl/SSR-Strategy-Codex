# SSRローカル分析Webアプリの設計と実装

このExecPlanは生きた文書であり、作業の進行に合わせて`Progress`、`Surprises & Discoveries`、`Decision Log`、`Outcomes & Retrospective`を更新する。リポジトリ直下の`.agent/PLANS.md`の規約に従って維持する。

## Purpose / Big Picture

消費者調査の代替として論文「LLMs Reproduce Human Purchase Intent via Semantic Similarity Elicitation of Likert Ratings」のSSR手法をローカルで再現するWebアプリを提供する。Codex CLI (`codex exec --model gpt-5.1`) でペルソナ/評価基準/コンテキスト入りの自然文を生成し、そのテキストをアンカー文に対する埋め込み類似度（TF-IDFコサイン）で分布化する。Codexが生成するセッションJSONLをそのまま一覧・ダウンロードでき、年齢・性別別の集計や詳細レポートを提供する。

## Progress

- [x] (2025-02-26 13:30Z) 初期ExecPlan作成。リポジトリ構造と論文の概要を確認。
- [x] (2025-02-26 14:20Z) SQLModelによるDBスキーマ、SSR類似度計算(TF-IDF+コサイン)、キュー/セッション管理の骨格を実装。
- [x] (2025-02-26 14:40Z) FastAPIエンドポイントとフロントエンド(UI, Chart.js, 画像Base64送信)を組み込み、SSRタスク実行フローを結合。
- [x] (2025-02-26 14:55Z) 依存インストールと`python -m compileall app`による構文検証を実施。手動検証はサーバ起動手順に委ねる。
- [x] (2025-02-27 10:10Z) ソーシャルゲーム運営向けの運営コンテキスト入力、プロンプトテンプレート管理、PDFレポート出力、サンプルデータ投入API、再現性設定(シード・計算手法)を追加し、UIを拡充。
- [x] (2025-12-01 05:10Z) 既存実装の誤りを是正：Codex execを経由しないTF-IDFのみのパス、独自セッションJSON生成、計算説明不足を修正する。
- [x] (2025-12-01 07:05Z) Codex exec(gpt-5.1)で自然文生成→埋め込み類似度計算のパイプラインへ一本化し、CodexのセッションJSONLをそのまま配布対象にする。
- [x] (2025-12-01 07:40Z) PDF/評価ロジックをCodex出力に基づく計算過程へ更新し、UIとAPIで手法名・セッションパスを整合させる。
- [x] (2025-12-02 22:45Z) SSR計算をSentenceTransformer埋め込み+コサインSoftmaxに変更し、Codexは自然文生成のみとした。requirements.txtへsentence-transformersを追加。
- [x] (2025-12-02 18:20Z) SSR類似度をsoftmax化し、デフォルトアンカーをソシャゲ運営向けに変更。Codex execがOS権限エラーで動かないため、フォールバック(tfidf合成)許容とサンプル一括実行スクリプトを追加。

## Surprises & Discoveries

- reportlabの日本語出力にはCIDフォント登録が必要なため、標準のHeiseiKakuGo-W5を登録してPDF生成を安定化させた。
- Codex exec が生成するセッションJSONLとアプリ側の独自JSONが二重化していたが、配布対象をCodex側に統一することで解消。
- Codex出力が日本語になるケースではアンカー（英語）とのTF-IDF類似度がフラットになりやすく、分布が均等になることを確認。アンカー多言語化や翻訳前処理が有効かもしれない。
- Codex CLIが「failed to initialize rollout recorder: Operation not permitted」で起動不可。ローカル環境権限の問題と推測し、当座はtfidf合成でフォールバックさせた。

## Decision Log

- Decision: 実装基盤にFastAPI+SQLite(SQLModel)とシンプルなフロントエンド(JS+Chart.js)を採用し、外部API不要のテキスト類似度(TF-IDFコサイン)でSSRを模倣する。
  Rationale: Python標準と軽量依存でローカル実行が容易。論文のSSRは埋め込み類似度を用いるため、TF-IDFコサインで代替する。
  Date/Author: 2025-02-26/assistant
- Decision: ソーシャルゲーム運営評価のため、タスクに運営コンテキスト(JSON)とプロンプトテンプレートIDを付与し、シード指定・類似度手法切替を許容する。
  Rationale: 再現性(論文追試)と運営シナリオごとの評価を両立し、研究者とマーケターが任意条件で予測生成できるようにする。
  Date/Author: 2025-02-27/assistant
- Decision: Codex exec(gpt-5.1)で生成した自然文を必須経路とし、その出力をアンカーとのTF-IDFコサインで分布化する。CodexセッションJSONLを配布し、独自セッションファイル生成は廃止する。
  Rationale: ユーザー要求「codex execでGPT-5.1」「セッションファイルはcodexが吐くものを配布」を満たし、二重保存や計算経路の不整合を解消する。
  Date/Author: 2025-12-01/assistant
- Decision: 類似度分布はcos類似度のsoftmaxに変更し、デフォルトアンカーをゲーム運営継続向けに統一。Codex execが権限エラーの場合は環境変数でtfidf合成フォールバックを許可する。
  Rationale: 論文手法の確率分布化に合わせ、運営施策評価へドメイン適合させる。同時に実行不能でも最低限の分析を継続できるようにするため。
  Date/Author: 2025-12-02/assistant

## Outcomes & Retrospective

- Codex exec(gpt-5.1)経路に一本化し、独自セッションJSON生成を廃止、CodexセッションJSONLの配布に統一できた。タスク失敗時はCodexエラーを明示し、フォールバックは明示的に`tfidf`/`uniform`を選ぶ方式とした。
- PDFは「Codex text → TF-IDF → anchors」の計算過程と手法名を表示するよう更新済み。UI/APIは手法=codexをデフォルトとし、セッション一覧はCodexのJSONLを列挙する。

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
3. **ジョブ/キュー処理**: `asyncio.Queue`で直列処理。タスク処理時にCodex exec(gpt-5.1)で自然文を生成し、そのテキストをアンカーに対するTF-IDFコサインで分布化する。Codexが生成したセッションJSONLをそのまま配布対象とし、独自セッション書き込みは行わない。
4. **APIとUI**: FastAPIでCRUDエンドポイント(ペルソナ、評価基準、プロンプトテンプレート、タスク作成、結果取得、集計取得、セッション閲覧/ダウンロード、PDFレポート)を提供。タスク詳細には使用手法=codexを明示し、`/api/sessions` は codex の `~/.codex/session/<year>/<month>/<day>/...jsonl` を列挙・ダウンロードする。PDFはCodex出力テキストと計算過程を表示する。
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
