---
name: update
description: Checks GitHub Releases for a newer agent-ui version and installs it. "update", "アップデート", "最新版を確認", "agent-uiを更新して" などで起動。 / Checks GitHub Releases for a newer agent-ui build and installs it if found.
---

# /update — agent-ui の更新 / Update agent-ui

## 言語設定 / Language Policy
ユーザーへの全ての返答は日英バイリンガルで表示してください。日本語を先に表示し、改行の後に英語を続けてください。
Always respond to the user in both Japanese and English. Display Japanese first, then English on the next line.

## 概要 / Overview

agent-ui の GitHub Releases（`kh813/agent-ui`）を確認し、現在インストールされているバージョンより新しいものがあればダウンロードして置き換えます。実行中の agent-ui 自体を書き換えるわけではないため、更新適用後はウィンドウを再起動する必要があります。
Checks agent-ui's GitHub Releases (`kh813/agent-ui`) and, if a newer version exists, downloads and installs it in place. This does not hot-swap the running process, so a restart is required to use the new version after applying an update.

## サブコマンド / Subcommands

| コマンド | 内容 |
|---|---|
| `python3 python/scripts/setup/self_update.py check` | 更新の有無だけを確認（ダウンロードしない） |
| `python3 python/scripts/setup/self_update.py apply` | 最新版を確認し、あればダウンロード・インストール |

Windowsでは `python3` を `python` に読み替えてください。
On Windows, replace `python3` with `python`.

## 手順 / Workflow

ユーザーが `/update` と言った場合、まず `check` を実行して更新の有無を確認します：
When the user says `/update`, first run `check` to see if an update is available:

```bash
python3 python/scripts/setup/self_update.py check
```

出力が `Already up to date: <tag>` の場合はそのままユーザーに伝えて終了します。
If the output is `Already up to date: <tag>`, report that and stop.

出力が `Update available: <old> -> <new>` の場合は適用してよいか確認し、承諾されたら `apply` を実行します：
If the output is `Update available: <old> -> <new>`, ask for confirmation, then on approval run:

```bash
python3 python/scripts/setup/self_update.py apply
```

## 完了後の案内 / Post-Update Instructions

`apply` の出力に "installed to" が含まれる場合、以下をユーザーに伝えてください：
If `apply`'s output contains "installed to", tell the user:

「更新が完了しました。新しいバージョンを使うには、このウィンドウを閉じて agent-ui を再起動してください。」
"The update is complete. Please close this window and restart agent-ui to use the new version."

## エラー対応 / Error Handling

ネットワークエラーやGitHub APIのレート制限に達した場合、`self_update.py` は例外を送出して終了します。エラーメッセージをそのままユーザーに伝え、しばらく待ってから再試行するよう案内してください。
On network errors or GitHub API rate limiting, `self_update.py` exits with an exception. Show the error message as-is and suggest retrying after a while.
