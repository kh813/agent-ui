---
name: daily-schedule
description: Google CalendarとGoogle Tasksから今日・今後の営業日の予定とタスクを取得して要約します。「今日の予定」「今日の残りタスク」「今週のスケジュール」「締め切り確認」「やることリスト」などと言われたときに使用してください。出勤・退勤・打刻（TeamSpirit）はこのスキルの範囲外です — attendance スキルを使用してください。Use when asked about today's schedule, remaining tasks, upcoming events, deadlines, or 今日の予定/残りタスク/スケジュール/締め切り/やること. Not for clock-in/clock-out (TeamSpirit attendance) — use the attendance skill for that.
---

# 今日のスケジュール確認 / Daily Schedule

## 言語設定 / Language Policy
ユーザーへの全ての返答は日英バイリンガルで表示してください。日本語を先に表示し、改行の後に英語を続けてください。
Always respond to the user in both Japanese and English. Display Japanese first, then English on the next line.

## 概要 / Overview

Google Calendarから今日と今後数営業日の予定を、Google Tasksから期限のあるタスクを取得し、わかりやすく整理して伝えます。「今日の残りタスク」「やること」といった質問もこのスキル1つで完結します — 出勤・退勤の打刻（TeamSpirit）は無関係なので実行しないでください。
Fetches today's and upcoming business-day events from Google Calendar, plus due tasks from Google Tasks, and summarizes them clearly. Questions like "remaining tasks today" or "what's left to do" are fully answered by this skill alone — do not run TeamSpirit clock-in/clock-out, which is unrelated.

## 手順 / Workflow

### Step 1 — スクリプトを実行する

```bash
python3 python/scripts/automation/automate.py calendar
```

今後5営業日まで確認したい場合：
```bash
python3 python/scripts/automation/automate.py calendar --days 5
```

### Step 2 — 初回認証（初回のみ）

スクリプトがブラウザを開くので、会社の Google アカウントでログインしてください。
認証後、トークンが `~/.gemini/seg_skills_calendar_token.json` に保存されます（次回以降は不要）。

### Step 3 — 結果を読み取って要約する

スクリプトの出力（各日の予定・締め切り一覧）をそのままユーザーに伝える。
加えて、以下の視点でコメントを添える：

- **今日集中すべきこと**: 時間が決まっている会議・タスク
- **今後の締め切り**: ⚠️ マークが付いたイベント
- **余裕のある日**: 予定が少なく作業時間を取れそうな日
- **準備が必要なもの**: 明日以降の大きな会議や提出物

## エラー対応

エラーが発生した場合、**`python/` 以下のソースコードを変更せずに**、エラー内容をそのままユーザーに報告してください。
If an error occurs, **do not modify any source files under `python/`** — report the error message to the user as-is.

| エラー | 対処 |
|--------|------|
| `venv not found` | `python3 python/scripts/setup/setup.py` を実行してセットアップ |
| ブラウザが開かない | スクリプトが出力する認証URLをブラウザで手動で開く |
| `Token has been expired` | `~/.gemini/seg_skills_calendar_token.json` を削除して再認証 |

## 使用例

- 「今日の予定を教えて」→ `automate.py calendar`
- 「今日の残りタスクを教えて」→ `automate.py calendar`（Google Tasksの期限あり項目も一緒に表示される）
- 「今週のスケジュール確認して」→ `automate.py calendar --days 5`
- 「今後の締め切りは？」→ `automate.py calendar --days 7` で締め切り一覧を確認
