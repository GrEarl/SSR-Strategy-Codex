# ExecPlans
 
When writing complex features or significant refactors, use an ExecPlan (as described in .agent/PLANS.md) from design to implementation.

# Skills

Use .agent/SKILL.md for Front-end Design Guideline

# Response Rule

You can think and make app by English but, you should response to user as Japanese.

# 要求

## 主目標
SSRを行うWebアプリを作成する
./docs傘下のpdf(もしくはそれをmdに変換してあるファイルがある)を参考に、SSRについて学習し、
Codex execコマンドを利用してAPIを使わないでローカルでSSR分析が可能なWebアプリを作成することを目的とする
具体的なSSRの実装は同論文に記載されているGithubレポジトリを参考にして良い(そのまま利用してもいい)

## 機能
 - ペルソナを登録し、一括で選択してSSRをタスク実行できる
 - 評価基準を管理できる
 - 自動でペルソナの年齢や性別ごとの評価レポートを生成できる
 - Codex Execが同期のため、キュー管理を実装
 - 画像でも入力できる
 - モデルはGPT-5.1(Codexモデルではない)
 - 評価指示プロンプトも登録して変更できる(例えば、純粋な広告ではなく、宣伝戦略にどれほど影響されるかを評価させるなど)
 - レポートは計算過程やグラフや図表、評価元の自然言語のレスポンスなどを記載し、詳細に
 - https://github.com/openai/codex の実装を参考にCodex CLIの動作を規定すること
 - 生成時のセッションファイル(~/.codex/session/<year>/<month>/<day>/ 以下)をダウンロードできるように

## 実装
ローカルのWebアプリケーションとして実行
外部に公開も想定できる形式
Codex execに適切なオプションを付す

## 計算
docs/2510.08338v3 に基づき、SSRは「LLMが生成した自由記述」を「アンカー文(5件法)」に対する意味類似度で分布化し、最頻値をratingとする。ここでは Codex CLI の `codex exec --model gpt-5.1` でペルソナ・評価基準・運営コンテキスト込みの自由記述を生成し、そのテキストを TF-IDF コサイン類似度でアンカー5文に写像して分布を得る。評価指標は KS類似度と相関達成度(correlation attainment)で論文手法と整合させる。

- セッションファイルは Codex exec が自動で `~/.codex/session/<year>/<month>/<day>/...` に生成する JSONL を扱い、これをダウンロード可能にする（追加で独自JSONを量産しない）。

## テスト用認証情報
基本的には実行者のCodexがすでにログインしていることを前提とするが、
テスト用に、実行環境のシークレット "Codex_Auth_Json" に ~/.codex/auth.json の内容をbase64でエンコードして配置した
これをデコードし、~/.codex/auth.jsonへ配置して認証せよ
