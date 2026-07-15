---
name: attendance
description: Automates TeamSpirit punch-in and punch-out. Use when asked to clock in, clock out, 出勤, 退勤, or 打刻. Not for schedule or "remaining tasks" questions — use the daily-schedule skill instead. / TeamSpirit での出勤・退勤打刻を自動化します。出勤・退勤・打刻・clock in・clock outと言われたときに使用してください。スケジュール確認や「残りタスク」の質問には使用しないでください（daily-schedule スキルを使用）。
---

# 出退勤打刻 / Skill: Attendance

## 言語設定 / Language Policy
ユーザーへの全ての返答は日英バイリンガルで表示してください。日本語を先に表示し、改行の後に英語を続けてください。
Always respond to the user in both Japanese and English. Display Japanese first, then English on the next line.

**形式例 / Format example:**
「出勤の打刻が完了しました。」
"Clock-in has been completed."

TeamSpiritで出勤・退勤の打刻を自動化します。
Automates clock-in and clock-out in TeamSpirit.

新しいChromeウィンドウが開き、保存済みセッションでTeamSpiritに接続して打刻を行います。
A new Chrome window opens and connects to TeamSpirit using the saved session to perform the time entry.

## 手順 / Workflow

### Step 1 — アクションを確認する / Confirm Action

| ユーザーの発言 / User Input | 実行するコマンド / Command |
|---|---|
| 出勤・clock in・clockin | `clockin` |
| 退勤・clock out・clockout | `clockout` |

### Step 2 — スクリプトを実行する / Run the Script

**Mac/Linux:**
```bash
python3 python/scripts/automation/automate.py clockin
# または / or
python3 python/scripts/automation/automate.py clockout
```

**Windows:**
```
python\scripts\automation\automate.bat clockin
python\scripts\automation\automate.bat clockout
```

スクリプトが初回実行の場合、venvとPlaywrightのセットアップが自動で行われます（数分かかる場合があります）。
On first run, venv and Playwright will be set up automatically (this may take a few minutes).

### Step 3 — ログイン対応（初回 / 再認証が必要なとき） / Handle Login (First Time or Re-authentication Required)

初回、またはしばらく使っていなかった場合はセッションが切れており、TeamSpiritへの手動ログインが必要です。
On first use, or after a period of inactivity, the session may have expired and manual login to TeamSpirit is required.

スクリプトの出力に以下のメッセージが表示された場合、手動ログインが必要です：
If the script output shows the following message, manual login is required:

```
【手動ログインが必要です】 / 【Manual login required】
```

このとき：
In this case:

1. ユーザーに伝える：「Chromeが開いています。TeamSpiritにGoogleアカウントでログインしてください。ログインが完了すると自動で続行します。」
   Tell the user: "Chrome is open. Please log in to TeamSpirit with your Google account. The script will continue automatically after login."
2. スクリプトはログイン完了を最大2分間待機します。ユーザーが認証を完了すると自動で打刻を実行します。
   The script waits up to 2 minutes for login to complete. Once the user authenticates, it will automatically perform the time entry.
3. スマートフォンでの承認（Google MFA）が必要な場合は、その操作も促してください。
   If smartphone approval (Google MFA) is required, prompt the user to approve it on their phone.

### Step 4 — 完了報告 / Report Completion

スクリプトの終了後、ユーザーに結果を日英バイリンガルで伝える。
After the script completes, report the result to the user in both Japanese and English.

- 成功例 / Success:
  「出勤の打刻が完了しました。」
  "Clock-in has been completed."
- エラー時 / On error:
  ログ出力をそのまま伝え、原因を説明する。
  Share the log output as-is and explain the cause.

## 初回セットアップ（一度だけ必要） / Initial Setup (One-Time Only)

セッションが未保存の場合は以下を実行してログイン情報を保存する：
If no session is saved, run the following to save login credentials:

**Mac/Linux:**
```bash
python3 python/scripts/automation/automate.py update-user-data
```
**Windows:**
```
python\scripts\automation\automate.bat update-user-data
```

Chrome が開くので、TeamSpirit に Google Workspace でログインしてから Chrome を閉じる。
Chrome will open — log in to TeamSpirit with Google Workspace, then close Chrome.

以降は自動でログイン済み状態で打刻が実行される。
Subsequent runs will execute with the saved login session automatically.

## 注意事項 / Notes

- **再認証 / Re-authentication**: 初回またはしばらく未使用の場合はセッションが切れており、Chromeで手動ログインが必要。スクリプトが「手動ログインが必要です」と表示したらユーザーに伝えて待機する / On first use or after inactivity, the session may have expired. If the script shows "Manual login required", inform the user and wait for them to complete login.
- **MFA / スマートフォン認証 / Smartphone Authentication**: Google認証でスマートフォン承認が必要な場合は、ユーザーに操作を促す / If smartphone approval is required for Google authentication, prompt the user to approve it.
- **二重打刻 / Duplicate Entry**: 打刻済みの場合はボタンがグレーアウトしたまま「既に打刻済みの可能性があります」と表示される / If already clocked in/out, the button stays grayed out and the script reports it may already be recorded.
- **ChromeUserData**: セッション情報は `python/scripts/automation/ChromeUserData/` に保存される / Session data is stored in `python/scripts/automation/ChromeUserData/`.

## 使用例 / Examples

- 「出勤打刻して」→ `automate.py clockin` (Mac) / `automate.bat clockin` (Windows)
  "Clock me in" → `automate.py clockin` (Mac) / `automate.bat clockin` (Windows)
- 「退勤して」→ `automate.py clockout` (Mac) / `automate.bat clockout` (Windows)
  "Clock me out" → `automate.py clockout` (Mac) / `automate.bat clockout` (Windows)
- 「今日退勤の打刻を忘れてた」→ `clockout` を実行する前に確認する
  "I forgot to clock out today" → Confirm with the user before running `clockout`
