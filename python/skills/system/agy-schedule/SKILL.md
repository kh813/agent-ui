---
name: agy-schedule
description: agyを使ったプロンプトをOS標準のスケジューラ（macOS launchd / Windows タスクスケジューラ）で定期実行するための作成・一覧・編集・有効化・無効化・削除を行います。「毎朝為替をチェックして」「定期実行を設定して」「自動実行の一覧を見せて」「定期実行を止めて」などで起動。このスキルが作成・表示・操作するのは、agy経由での実行を想定してこのスキル自身が登録したタスクのみです（他の既存のcron/タスクスケジューラの項目には触れません）。 / Creates, lists, edits, enables/disables, and deletes recurring agy prompts registered with the OS's native scheduler (macOS launchd / Windows Task Scheduler). Trigger with phrases like "check forex every morning", "set up a scheduled task", "show my scheduled tasks", or "stop this scheduled task". This skill only ever shows or touches tasks it registered itself for running through agy — never other pre-existing cron entries or Scheduled Tasks on the machine.
---

# agyの定期実行管理 / agy Scheduled Task Management

## 言語設定 / Language Policy
ユーザーへの全ての返答は日英バイリンガルで表示してください。日本語を先に表示し、改行の後に英語を続けてください。
Always respond to the user in both Japanese and English. Display Japanese first, then English on the next line.

## 概要 / Overview

agyを起動しっぱなしにしておく必要はありません。OS標準のスケジューラ（macOSは`launchd`、Windowsはタスクスケジューラ）から、指定した時刻に `agy --print` をヘッドレス実行し、結果を Chat（`notify-chat` スキルで設定）に届けます。

You don't need to leave agy running. This skill registers `agy --print` to run headlessly at a specified time via the OS's native scheduler (`launchd` on macOS, Task Scheduler on Windows), delivering the result to Chat (set up via the `notify-chat` skill).

**重要な制約 / Important constraint:** 作成されるタスクは全て専用の名前空間に登録されます（macOS: `~/Library/LaunchAgents/` 内の `com.agent-ui.agy.*` というラベルのファイルのみ。Windows: タスクスケジューラの `\AgentUI\AGY\` フォルダ内のみ）。**一覧・編集・無効化・削除の対象は常にこの名前空間内のタスクだけ**であり、ユーザーが別途設定した他のcronジョブやタスクスケジューラのタスクを表示・変更・削除することは一切ありません。

All tasks are registered into a dedicated namespace (macOS: files labeled `com.agent-ui.agy.*` under `~/Library/LaunchAgents/`; Windows: the `\AgentUI\AGY\` Task Scheduler folder only). **List/edit/disable/delete only ever operate on tasks within this namespace** — this skill never displays, modifies, or removes any other cron job or Scheduled Task the user has set up independently.

実体は `python/scripts/automation/agy_scheduler.py`（作成・一覧・編集・有効化・無効化・削除）と `python/scripts/automation/agy_scheduled_prompt.py`（実際に呼ばれるヘッドレス実行本体）です。

Implemented by `python/scripts/automation/agy_scheduler.py` (create/list/edit/enable/disable/delete) and `python/scripts/automation/agy_scheduled_prompt.py` (the actual headless payload each task runs).

## 手順 / Workflow

### 0. 前提条件の確認 / Prerequisite Check

`config.toml` の `[notifications] chat_webhook_url` が空の場合、結果の届け先が無いことを伝え、先に `notify-chat` スキルでの設定を勧めてください（それでもログのみで良ければ続行して構いません）。

If `[notifications] chat_webhook_url` in `config.toml` is empty, tell the user there's currently no delivery destination and suggest running the `notify-chat` skill first (but proceed anyway if they're fine with log-only output for now).

### 1. サブコマンドの判定 / Determine the Subcommand

ユーザーの発言から以下のどれかを判定します。曖昧な場合は聞き返してください。

Determine which of the following the user wants; ask if ambiguous.

| 操作 | コマンド |
|---|---|
| 新規作成 | `agy-schedule create` |
| 一覧表示 | `agy-schedule list` |
| 編集 | `agy-schedule edit <name>` |
| 無効化（一時停止） | `agy-schedule disable <name>` |
| 有効化（再開） | `agy-schedule enable <name>` |
| 削除 | `agy-schedule delete <name>` |

### 2. agy-schedule create

**新規作成の前に必ず Google Workspace Studio との比較を案内してください（スキップ不可）。**

**Before creating anything new, you must always surface the Google Workspace Studio comparison below — do not skip this.**

Google Workspace Studio（[studio.workspace.google.com](https://studio.workspace.google.com/)）は、Googleが提供するノーコードのGemini搭載自動化ビルダーで、スケジュールトリガーとChat/Slack/Teams等への通知を標準機能として持っています。**最大の違いはクラウド実行であること** — `agy-schedule` はこのPCが電源オン・スリープ解除状態でないと指定時刻に実行されませんが、Workspace StudioはユーザーのPCの状態に関係なく実行されます。

Google Workspace Studio ([studio.workspace.google.com](https://studio.workspace.google.com/)) is Google's no-code, Gemini-powered automation builder, with schedule triggers and Chat/Slack/Teams notifications built in natively. **The key difference is that it runs in the cloud** — `agy-schedule` only fires if this machine is powered on and awake at the scheduled time, whereas Workspace Studio runs regardless of the user's PC state.

次の基準でユーザーに伝えてください:

Tell the user based on the following:

| ケース / Case | 案内 / Guidance |
|---|---|
| 外部API・Google Workspace内のデータ（Gmail/Sheets/カレンダー等）・一般的なWebページなど、Workspace Studioでも扱えそうなソース | Workspace Studioの方が信頼性が高い（PCの電源状態に依存しない）ことを伝え、それでもagy-scheduleを使いたいか確認する / Tell the user Workspace Studio is likely more reliable here (no PC-uptime dependency), and confirm they still want agy-schedule anyway |
| ActionPassport・DocuSign・Sansan・TeamSpirit等、ブラウザ自動化やagy固有のスキル（`ask-portal`など）が必要なソース | agy-scheduleが妥当であることを伝え、そのまま進める / Tell the user agy-schedule is the right tool here, and proceed |

ユーザーが「それでもagy-scheduleで」と言った場合は、以降の手順をそのまま実行してください（無理に止めない）。

If the user says they want agy-schedule anyway, proceed with the rest of this workflow — don't block them.

以下をヒアリングします（既に発言に含まれていれば聞き直さない）:

Gather the following (skip anything already given):

- **名前 / Name**: 英数字・ハイフン・アンダースコアのみ（例: `forex-check`）。既存タスクと重複しないこと。
- **実行内容 / What to run**: agyに渡すプロンプト。多くの場合 `info-collector` スキルの利用を想定した文（例:「info-collectorスキルで今日のドル円レートを確認して」）。
- **頻度 / Frequency**: 毎日 (daily) か、曜日指定 (weekly: MON/TUE/WED/THU/FRI/SAT/SUN)。
- **時刻 / Time**: 24時間形式 HH:MM。

内容を確認してから実行します：
Confirm the details before running:

```bash
# 毎日 / Daily
python3 python/scripts/automation/agy_scheduler.py create <name> --prompt "<prompt>" --daily HH:MM

# 曜日指定 / Weekly
python3 python/scripts/automation/agy_scheduler.py create <name> --prompt "<prompt>" --weekly MON,WED,FRI HH:MM
```

成功したら、次回実行予定と「`agy-schedule list`でいつでも確認できる」ことを伝えます。

On success, tell the user when it will next run and that they can check it anytime with `agy-schedule list`.

### 3. agy-schedule list

```bash
python3 python/scripts/automation/agy_scheduler.py list
```

出力をそのまま整形して見せます。`(⚠ not registered — recreate it)` と表示されたタスクは、OS側の登録が何らかの理由で失われています（手動削除など）。再作成（削除→作成、または`edit`で内容そのまま指定し直す）を提案してください。

Present the output. Any task flagged `(⚠ not registered — recreate it)` has lost its OS-level registration (e.g. manually deleted) — offer to recreate it (delete + create again, or run `edit` with the same values to force re-registration).

### 4. agy-schedule edit <name>

まず一覧で現在の設定を見せ、何を変更したいか聞きます（プロンプト・頻度・時刻のいずれか、複数可）。

Show the current settings from `list` first, then ask what to change (prompt, frequency, and/or time).

```bash
python3 python/scripts/automation/agy_scheduler.py edit <name> --prompt "<new prompt>"
python3 python/scripts/automation/agy_scheduler.py edit <name> --daily HH:MM
python3 python/scripts/automation/agy_scheduler.py edit <name> --weekly MON,FRI HH:MM
```

内部的には削除して同名で再作成するため、有効/無効の状態はリセットされ有効になります。必要であれば編集後に `disable` してください。

Internally this deletes and recreates the task under the same name, so it comes back enabled regardless of its prior state — `disable` it again afterward if needed.

### 5. agy-schedule disable / enable <name>

削除せずに一時停止・再開します。

Pause or resume without deleting.

```bash
python3 python/scripts/automation/agy_scheduler.py disable <name>
python3 python/scripts/automation/agy_scheduler.py enable <name>
```

### 6. agy-schedule delete <name>

**この操作は取り消せません。** 確認を取ってから実行します：

**This cannot be undone.** Ask for confirmation first:

```
「<name>」を完全に削除します。この操作は取り消せません。よろしいですか？（はい / いいえ）
Permanently delete "<name>". This cannot be undone. Proceed? (Yes / No)
```

```bash
python3 python/scripts/automation/agy_scheduler.py delete <name>
```

## 使用例 / Examples

### シナリオ1: 毎朝の為替チェック / Scenario 1: Daily Forex Check
**ユーザー / User**: 「毎朝9時にドル円レートをチェックしてChatに送って」

**アクション / Action**:
```bash
python3 python/scripts/automation/agy_scheduler.py create forex-check \
  --prompt "info-collectorスキルを使って今日のドル円為替レートを確認して" \
  --daily 09:00
```

### シナリオ2: 一覧確認 / Scenario 2: Listing Tasks
**ユーザー / User**: 「今設定してる自動実行を見せて」

**アクション / Action**: `agy-schedule list` を実行し、名前・頻度・時刻・有効状態を整形して提示。

### シナリオ3: 不要になったので停止 / Scenario 3: No Longer Needed
**ユーザー / User**: 「forex-checkはもう使わないから消して」

**アクション / Action**: 削除確認 → `agy-schedule delete forex-check`。
