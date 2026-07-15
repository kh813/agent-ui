---
name: notify-chat
description: Google Chatのスペースを新規作成し、Incoming Webhookを発行してconfig.tomlに設定するまでをガイドします。定期実行・ヘッドレス実行（例: `agy --print`をcronから起動）した結果をChatに届けたいときに使用。「通知の設定をして」「Chatに通知を送れるようにして」「Webhookを設定して」「自動実行の結果をChatに送りたい」などで起動。 / Guides you through creating a Google Chat space, issuing an Incoming Webhook, and saving it to config.toml. Use this to deliver results from scheduled/headless runs (e.g. a cron job invoking `agy --print`) to a Chat space. Trigger with phrases like "set up chat notifications" or "I want scheduled results sent to Chat".
---

# Chat通知セットアップ / Chat Notification Setup

## 言語設定 / Language Policy
ユーザーへの全ての返答は日英バイリンガルで表示してください。日本語を先に表示し、改行の後に英語を続けてください。
Always respond to the user in both Japanese and English. Display Japanese first, then English on the next line.

## 概要 / Overview

Google ChatのIncoming Webhookは、OAuthの新規スコープ追加やユーザーごとの再認証が不要で、スペースごとに発行されるURLへHTTPS POSTするだけでメッセージを送れます。このスキルは、スペースの作成からWebhook URLの発行、`config.toml`への保存、送信テストまでをガイドします。

Google Chat's Incoming Webhooks need no new OAuth scope and no per-user re-authentication — just an HTTPS POST to a URL issued per space. This skill guides you from creating the space through issuing the webhook URL, saving it to `config.toml`, and sending a test message.

セットアップ後は `python3 python/scripts/automation/notify_chat.py "<メッセージ>"` でどのスクリプト・スキルからでも通知を送れるようになります。定期実行そのもの（OSのスケジューラ設定など）はこのスキルの範囲外です。

Once set up, any script or skill can send a notification via `python3 python/scripts/automation/notify_chat.py "<message>"`. Setting up the recurring execution itself (OS scheduler configuration, etc.) is out of scope for this skill.

**目的が「定期実行の結果をChatに送りたい」であれば、先に `agy-schedule` スキルを案内してください** — そちらでGoogle Workspace Studio（クラウド実行・スケジュール＋Chat通知が標準機能）との比較を行った上で、それでもagy側の通知設定が必要ならこのスキルに戻ってきます。

**If the goal is "send results from a scheduled run to Chat," point the user to the `agy-schedule` skill first** — it walks through the comparison with Google Workspace Studio (cloud-based, with scheduling and Chat notifications built in natively), and only comes back to this skill if agy-side notification setup is still needed.

## 手順 / Workflow

### 1. 既存設定の確認 / Check Existing Configuration

`config.toml` を確認します（存在しない場合は先に初期セットアップ（`setup` スキル）の完了を案内して終了してください）。

Check `config.toml` (if it doesn't exist yet, tell the user to complete initial setup via the `setup` skill first, and stop here).

`[notifications]` セクションの `chat_webhook_url` が既に空でない値を持っている場合は、ユーザーに選ばせます：

If `[notifications]` already has a non-empty `chat_webhook_url`, ask the user which they want:

```
既にChat通知が設定されています。
  1. テストメッセージを送って動作確認する
  2. 新しいスペース/Webhookに設定し直す
どちらにしますか？

Chat notifications are already configured.
  1. Send a test message to confirm it still works
  2. Reconfigure with a new space/webhook
Which would you like?
```

「1」の場合は Step 5（動作確認）に進みます。「2」の場合は Step 2 から続けます。
For "1", skip to Step 5 (Test). For "2", continue from Step 2.

### 2. Chatスペースの準備 / Prepare a Chat Space

通知専用の新しいスペースを作ることを推奨してください（既存の雑談スペースに流すと埋もれるため）。既存スペースを使いたい場合はそれでも構いません。

Recommend creating a dedicated new space (posting into a busy existing space means notifications get lost) — but using an existing space is fine if the user prefers.

ユーザーに次の手順で作成してもらいます（Google Chat Web版: `chat.google.com`）:

Have the user create it via Google Chat's web UI (`chat.google.com`):

```
1. chat.google.com を開く
2. 左上の「+」→「スペースを作成」を選択
3. スペース名を入力（例: 「agent-ui 通知」）し、「作成」をクリック

1. Open chat.google.com
2. Click "+" in the top-left → "Create space"
3. Name it (e.g. "agent-ui notifications") and click "Create"
```

### 3. Webhookの追加 / Add the Incoming Webhook

作成した（または既存の）スペース内で、次の手順でWebhookを発行してもらいます:

Within that space, have the user issue a webhook:

```
1. スペース名の右にあるスペース名／下矢印をクリック
2. 「アプリと統合」→「Webhookを追加」を選択
3. 名前を入力（例: 「agent-ui」）し、「追加」をクリック
4. 表示されたURLをコピーする（一度しか表示されない場合があるので必ずコピー）

1. Click the space name / dropdown arrow near the top
2. Select "Apps & integrations" → "Add webhooks"
3. Give it a name (e.g. "agent-ui") and click "Add"
4. Copy the generated URL (it may not be shown again, so copy it now)
```

### 4. URLの受け取りと検証 / Collect and Validate the URL

コピーしたURLを貼り付けてもらいます。`https://chat.googleapis.com/` で始まらない場合は形式が違う可能性があるため、手順3をやり直したかを確認してください（ただし将来的にGoogle側でURL形式が変わる可能性もあるため、厳密なフォーマットチェックで弾かない）。

Ask the user to paste the URL. If it doesn't start with `https://chat.googleapis.com/`, it may be the wrong thing — confirm they followed step 3 correctly. Don't hard-reject on format alone, since Google could change the URL shape over time.

### 5. config.tomlへの保存 / Save to config.toml

`config.toml` をバックアップしてから、`[notifications]` セクションの `chat_webhook_url` を貼り付けられたURLで更新します（セクションが無ければ追記）。

Back up `config.toml`, then update `chat_webhook_url` under `[notifications]` with the pasted URL (append the section if it doesn't exist yet).

```bash
cp config.toml config.toml.bak
```

編集後、バックアップを削除します。書き込みに失敗した場合はバックアップから復元してください。
After editing, delete the backup. If the write fails, restore from the backup.

### 6. 動作確認 / Test

```bash
python3 python/scripts/automation/notify_chat.py "✅ agent-ui: Chat通知の設定が完了しました。"
```

実行後、ユーザーに該当スペースにメッセージが届いているか確認してもらいます。届いていなければ、URLの貼り間違いやWebhookの削除がないか確認し、Step 3〜5をやり直してください。

Ask the user to confirm the message arrived in the space. If not, check for a mistyped URL or a deleted webhook, and redo Steps 3–5.

## 使用例 / Examples

### シナリオ1: 初回セットアップ / Scenario 1: First-Time Setup
**ユーザー / User**: 「自動実行の結果をChatに送りたい」

**アクション / Action**: Step 1〜6を順に実行し、最後にテストメッセージが届いたことを確認して完了を報告。

### シナリオ2: 既存設定の動作確認のみ / Scenario 2: Just Testing an Existing Setup
**ユーザー / User**: 「Chat通知がちゃんと届くか確認して」

**アクション / Action**: Step 1で既存設定ありと判定 → 「1」を選ばせて Step 5 のテストのみ実行。
