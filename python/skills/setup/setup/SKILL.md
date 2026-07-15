---
name: setup
description: Initial setup (初期セットアップ) and automation dry-run testing (テスト/動作確認). Triggered by "setup init", "setup test", "セットアップして", "動作確認して", "dry-runして". For skill list/enable/disable/rebuild use the my-skills skill instead; for updating the tool use the update skill instead.
---

# セットアップスキル / Setup Skill

## 言語設定 / Language Policy
ユーザーへの全ての返答は日英バイリンガルで表示してください。日本語を先に表示し、改行の後に英語を続けてください。
Always respond to the user in both Japanese and English. Display Japanese first, then English on the next line.

## 概要 / Overview

このスキルは初期セットアップと、自動化スクリプトの dry-run テストを担います。
This skill handles initial setup and dry-run testing of automation scripts.

| サブコマンド / Subcommand | 内容 / Description |
|---|---|
| `setup init` | 初期セットアップ / Initial setup |
| `setup test [<target>]` | 自動化スクリプトのdry-runテスト / Dry-run test for automation scripts |

スキルの一覧表示・有効化・無効化・リビルドは `my-skills` スキルを使用してください。ツールのアップデートは `update` スキルを使用してください。
For skill list/enable/disable/rebuild, use the `my-skills` skill. For updating the tool, use the `update` skill.

---

## setup init — 初期セットアップ / Initial Setup

「セットアップして」「環境を構築して」などで起動します。
Triggered by "セットアップして", "環境を構築して", "setup init", "run setup".

### Step 1 — セットアップ要否の確認 / Check if setup is needed

```bash
ls app/bin/
```

- バイナリが存在する場合はセットアップ済みをユーザーに伝えます。 / If binaries exist, inform the user setup is already complete.
- 存在しない場合は Step 2 へ。 / If not, proceed to Step 2.

### Step 2 — セットアップの実行 / Run setup

```bash
python3 python/scripts/setup/setup.py init
```

完了後、`app/bin/` にバイナリが配置されたことをユーザーに伝えます。
After completion, inform the user that binaries have been deployed to `app/bin/`.

---

## setup test — 動作確認（Dry-Run）/ Test

「テストして」「動作確認して」「dry-runして」などで起動します。引数にテスト対象を指定できます。
Triggered by "テストして", "動作確認して", "setup test", "dry-run". An optional target can be specified.

自動化スクリプトを `--dry-run` モードで実行します。Chrome が開いて対象ページに遷移し、ボタンや入力欄が正しく検出できるかを確認します。**打刻・ダウンロードは一切行いません。**
Runs automation scripts in `--dry-run` mode. Chrome opens, navigates to the target page, and verifies buttons and fields. **No clock-in/out or downloads are performed.**

### テスト対象 / Test Targets

| 引数 / Argument | 確認内容 / What is Verified | コマンド / Command |
|---|---|---|
| `clockin` | 出勤ボタンが存在するか / Clock-in button exists | `automate.py clockin --dry-run` |
| `clockout` | 退勤ボタンが存在するか / Clock-out button exists | `automate.py clockout --dry-run` |
| `docusign` | ダウンロードボタンが存在するか / Download button exists | `automate.py docusign --dry-run` |
| `actionpassport` | エクスポート・ダウンロードボタンが存在するか / Export and download buttons exist | `automate.py actionpassport --dry-run` |
| `sansan` | SSO入力欄が存在するか / SSO input field exists | `automate.py sansan --dry-run` |
| `ext-devices` | チェックボックスと出力ボタンが存在するか / Checkbox and output button exist | `automate.py ext-devices --dry-run` |
| `portal` | 検索ボタンと入力欄が検出できるか / Search button and input field detected | `automate.py portal テスト --dry-run` |
| (なし / none) | 全対象を順番に実行 / Run all targets in sequence | 上記すべて / All above |

引数が指定されない場合は全対象を実行します。
If no argument is given, run all targets in sequence.

### 前提条件：セッションの保存 / Prerequisite: Save Session

初回またはセッションが切れている場合は先にセッションを保存してください。
For the first run or if the session has expired, save the session first:

**Mac/Linux:**
```bash
python3 python/scripts/automation/automate.py update-user-data
```
**Windows:**
```
python\scripts\automation\automate.bat update-user-data
```

Chrome が開くので各サービスにログインし、Chrome を閉じる。以降は自動でログイン済み状態になる。
Chrome will open — log in to each service, then close Chrome. Subsequent runs will use the saved session automatically.

### Step 1 — dry-run を実行する / Run dry-run

**Mac/Linux:**
```bash
python3 python/scripts/automation/automate.py <target> --dry-run
```
**Windows:**
```
python\scripts\automation\automate.bat <target> --dry-run
```

各コマンドは独立して実行する（前のコマンドの結果を待ってから次へ）。
Run each command independently (wait for the previous to finish before running the next).

### Step 2 — 結果を報告する / Report Results

各テストのログ出力から結果を読み取り、以下の形式でまとめてユーザーに日英バイリンガルで伝える：
Read results from each log and summarize in the following format:

```
テスト結果サマリー / Test Result Summary
-----------------------------------------
✓ 出勤打刻 / Clock-in    — 出勤ボタン 検出OK / Clock-in button detected（tmp/dryrun/dryrun_clockin.png）
✓ 退勤打刻 / Clock-out   — 退勤ボタン 検出OK / Clock-out button detected
✗ DocuSign               — ダウンロードボタンが見つかりません / Download button not found
...
```

`✗` があった場合は原因と対処法を案内する：
If there is a `✗`, provide the cause and remedy:

- **セレクタが見つからない / Selector not found**: ページのUI変更の可能性。スクリーンショット（`tmp/dryrun/`）を確認するよう伝える。
- **ログインページにリダイレクト / Redirected to login page**: `update-user-data` でセッションを保存するよう案内する。

---

## アンインストール / Uninstall

「アンインストールしたい」「環境を削除したい」と言われた場合は、以下の手順をユーザーに案内します。
If the user asks to uninstall or remove the environment, guide them with the steps below.

Node.js・Gemini CLI・Python 環境などはすべてプロジェクトフォルダ内に収まっているため、**フォルダを削除するだけでアンインストールできます**。ただし、フォルダ外に書き込んだポリシーファイルは別途削除が必要です。
Node.js, Gemini CLI, and Python environments are all stored inside the project folder. **Deleting the folder is sufficient to uninstall.** However, the policy file written outside the folder must be removed separately.

### 手順 / Steps

1. Gemini CLI を終了する / Quit Gemini CLI

2. プロジェクトフォルダを削除する / Delete the project folder:
   ```
   # フォルダごと削除 / Delete the entire project folder
   rm -rf /path/to/agent-ui      # Mac/Linux
   rmdir /S /Q C:\path\to\agent-ui  # Windows
   ```

3. ポリシーファイルを削除する / Delete the policy file:
   ```bash
   rm ~/.gemini/policies/agent-ui.toml      # Mac/Linux
   del "%USERPROFILE%\.gemini\policies\agent-ui.toml"  # Windows
   ```

以上でアンインストールは完了です。`files/` フォルダはプロジェクト内にあるため、必要なデータは事前にバックアップしてください。
That's all. Since `files/` is inside the project folder, back up any needed data before deleting.

---

## 使用例 / Examples

| ユーザーの入力 / User input | 実行コマンド / Command |
|---|---|
| 「セットアップして」| `setup.py init` |
| 「動作確認して」| `setup test` — 全対象を dry-run |
| 「アンインストールしたい」| 手動手順をユーザーに案内 / Guide manual uninstall steps |

スキル管理（一覧・有効化・無効化・リビルド）は `my-skills` スキル、アップデートは `update` スキルを参照してください。
For skill management (list/enable/disable/rebuild), see the `my-skills` skill. For updates, see the `update` skill.
