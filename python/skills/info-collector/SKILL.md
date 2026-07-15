---
name: info-collector
description: ユーザーが指定した情報源（URL、GitHubリポジトリ、Googleドライブのファイル/フォルダ、ローカルファイルなど）から、指定した確認項目だけを自動的に収集・抽出して報告します。「このサイトから〇〇を調べて」「この情報源から情報収集して」「定点観測して」などで起動。トピックを指定せず自由に調査してほしい場合は `research-assistant` を使用してください。 / Collects and extracts only the requested fields from a user-specified information source (a URL, a GitHub repo, a Google Drive file/folder, a local file, etc.). Trigger with phrases like "collect info from this source", "check this page for X", or "情報収集して". For open-ended topic research without a specific source, use `research-assistant` instead.
---

# 情報収集 / Info Collector

## 言語設定 / Language Policy
ユーザーへの全ての返答は日英バイリンガルで表示してください。日本語を先に表示し、改行の後に英語を続けてください。
Always respond to the user in both Japanese and English. Display Japanese first, then English on the next line.

## 概要 / Overview

ユーザーが指定した1つ以上の情報源から、指定した確認項目だけを取得して報告します。情報源そのもの（生のHTML、長大なページ全文など）をそのまま貼り付けるのではなく、必要な情報だけを抽出して簡潔に伝えることが目的です。

Fetches only the requested fields from one or more user-specified sources and reports them concisely. The goal is to extract exactly what was asked for — never dump the raw source (a full HTML page, an entire long document, etc.) back to the user.

`research-assistant` との違い: あちらは「トピックを渡して自由に調べてもらう」深い調査向け。このスキルは「情報源」と「確認項目」の両方が既知の、繰り返し可能な定点収集向け。
Difference from `research-assistant`: that skill is for open-ended deep research on a topic. This skill is for repeatable, targeted extraction where both the source and the fields to check are already known.

## 手順 / Workflow

### 1. 情報源と確認項目のヒアリング / Gather the Source and Criteria

ユーザーの依頼に以下の両方が含まれているか確認します。片方でも欠けていたら、欠けている分だけ聞いてください（両方揃っているのに聞き直さない）。

Check whether the request already specifies both of the following. Ask only for whatever is missing — never re-ask for something already given.

- **情報源 / Source**: URL、GitHubリポジトリ、Google Driveのファイル/フォルダ、ローカルファイル、APIエンドポイントなど。複数指定も可。
  A URL, GitHub repo, Google Drive file/folder, local file, API endpoint, etc. Multiple sources are allowed.
- **確認項目 / Criteria**: 何を確認・抽出してほしいか（例: 「最新バージョン番号」「価格と在庫」「新着記事のタイトルだけ」）。
  What specifically to check or extract (e.g. "the latest version number", "price and stock status", "just the titles of new articles").

### 2. 情報源の種類を判定し、取得方法を選ぶ / Identify Source Type and Fetch Method

情報源の形式に応じて、その場で使える手段を選びます（利用可能なツールはツールセットに応じて読み替えてください）:

Pick the appropriate method based on the source type (substitute whatever tools are actually available in the current environment):

| 情報源 / Source type | 取得方法 / Method |
|---|---|
| 一般的なWebページ・記事 / General web page | Web fetch/ブラウズ系ツール、無ければ `curl` |
| GitHubのリリース・コミット・Issue等 / GitHub releases, commits, issues | GitHub REST API（`curl -fsSL https://api.github.com/...`）。認証済みCLI（`gh`）があればそちらを優先 |
| Google Driveのファイル・フォルダ / Google Drive file or folder | `download-from-drive` スキルの手順、またはDrive APIスクリプト |
| ローカルファイル / Local file | Read系ツール、またはPDF/Office文書は `convert-to-markdown` スキル |
| その他API / Other APIs | エンドポイントの形式に応じて `curl` またはWeb fetch系ツール |

複数の情報源が指定された場合は、それぞれに対して独立に取得・抽出を行ってから結果を統合します。
When multiple sources are given, fetch and extract from each independently, then combine the results.

### 3. 取得内容の検証 / Validate What Was Fetched

抽出前に、取得した内容が期待される形式か簡単に確認してください。例えば「バージョン文字列を期待しているのにHTMLページ全体が返ってきた」「404やリダイレクト先のログインページが返ってきた」といった場合は、それをそのまま確認項目の答えとして扱わず、取得失敗として報告してください。

Before extracting, sanity-check that what came back matches what was expected. If (for example) a short version string was expected but a full HTML page came back instead, or a 404/login-redirect page came back, treat that as a fetch failure and report it as such — never surface the raw unexpected content as if it were the answer.

### 4. 抽出と報告 / Extract and Report

確認項目ごとに、抽出した情報のみを簡潔に報告します。生のページ全文やHTML、長大なJSON応答をそのまま貼り付けないでください。情報源が複数ある場合は情報源ごとに分けて示します。見つからなかった項目は「見つからず」と明記します。

Report only the extracted information for each requested criterion — never paste the raw page, HTML, or a large JSON blob verbatim. When there are multiple sources, group the findings by source. Explicitly note any criterion that could not be found.

### 5. 詳細の保存（任意）/ Save Details (Optional)

取得した生データの詳細をユーザーが後で参照したい場合は、`tmp/` ディレクトリに保存することを提案してください。
If the user may want to reference the raw fetched details later, offer to save them under `tmp/`.

### 6. 繰り返し実行したい場合 / For Recurring Checks

「毎回」「定期的に」「監視して」など継続的な収集を求められた場合、このスキル自体はループ機能を持たないため、`agy-schedule` スキル（agy経由でのOS定期実行の作成・管理）の利用を案内してください。`agy-schedule` は、状況によっては Google Workspace Studio の方が適していることも案内します。

If the user wants this repeated on an interval ("every day", "keep monitoring", etc.), this skill itself has no looping mechanism — point them to the `agy-schedule` skill (creates and manages recurring OS-level agy runs) instead of trying to reimplement that here. `agy-schedule` will itself flag when Google Workspace Studio may be a better fit.

## 使用例 / Examples

### シナリオ1: バージョンチェック / Scenario 1: Version Check
**ユーザー / User**: 「GitHubの kh813/agent-ui のリリースページから、v0.0.5より新しいバージョンが出てないか確認して」

**アクション / Action**: GitHub REST APIでリリース一覧を取得し、タグ名だけを比較。結果を「v0.0.5が最新です」のように一言で報告。

### シナリオ2: 複数ソースからの部分抽出 / Scenario 2: Partial Extraction from Multiple Sources
**ユーザー / User**: 「このニュースサイトとこのブログの両方から、AIに関する新着記事のタイトルだけ集めて」

**アクション / Action**: 2つのURLをそれぞれ取得し、AI関連記事のタイトルのみを抽出、情報源ごとに箇条書きで報告。

### シナリオ3: 取得失敗の検知 / Scenario 3: Detecting a Bad Fetch
**ユーザー / User**: 「このAPIエンドポイントから現在のステータスコードを教えて」

**アクション / Action**: 取得結果がエラーページやリダイレクト先のHTMLだった場合、それをステータスコードとして誤報告せず、「取得に失敗しました（ログインページにリダイレクトされました）」と伝える。
