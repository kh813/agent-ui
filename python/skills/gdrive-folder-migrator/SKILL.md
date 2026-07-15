---
name: gdrive-folder-migrator
description: Migrates a Google Drive folder to another location (e.g. a Shared Drive). Scans recursively, bulk-moves subfolders where possible, and resumes if interrupted. / Google Driveのフォルダを別の場所（共有ドライブなど）に移行します。再帰スキャン・サブフォルダ一括移動・中断再開に対応。
---

# gdrive-folder-migrator

Google Drive 上の指定フォルダを別の場所（共有ドライブなど）に移行します。
Migrates a Google Drive folder to another location (e.g. a Shared Drive).

**言語 / Language:** すべてのユーザー向けメッセージは **日本語を先に、次の行に英語** の順で出力すること。
All user-facing messages must follow the format: **Japanese first, English on the next line**.

**トリガー / Triggers:**
- "ドライブのフォルダを移動して"
- "Google Drive のフォルダを共有ドライブに移す"
- "gdrive migrate"
- "ファイルを移行して"

---

## 動作概要 / How it works

1. **スキャン**: 移動元フォルダを再帰的に走査し、移動対象の全ファイル・フォルダをリストアップ
   - `canMoveItemOutOfDrive=True` のサブフォルダは **一括移動** としてマークし、配下への再帰をスキップ（APIコール・トークン消費を大幅に削減）
2. **確認**: 件数を提示してユーザーに実行の確認を取る
3. **実行**: タスクを1件ずつ処理
   - **サブフォルダ（一括移動可能）**: フォルダごと `files.update` で移動（配下一式が1回のAPI呼び出しで完了）
   - **サブフォルダ（個別作成）**: 移動先に空フォルダを `files.create` で作成し、配下を個別に処理
   - **ファイル**: まず「移動」を試みる（`files.update`）。移動不可の場合はコピー → 元ファイルを削除
   - **ショートカット**: 移行不可のためゴミ箱へ移動
4. **結果報告**: 完了・失敗・ゴミ箱ファイルの一覧を表示

中断しても再実行で再開可能（完了済みタスクはスキップ）。

---

## Step 1 — 移動元 URL を取得する

移行元と移行先のフォルダ URL を順番に入力してもらいます。まず移行元から確認します。
We'll ask for the source and destination folder URLs one at a time. Starting with the source.

```json
{
  "questions": [
    {
      "header": "移動元フォルダ",
      "question": "移動元の Google Drive フォルダの URL を教えてください。\nPlease provide the URL of the source Google Drive folder.",
      "type": "text",
      "placeholder": "https://drive.google.com/drive/folders/..."
    }
  ]
}
```

---

## Step 2 — 移動先 URL を取得する

```json
{
  "questions": [
    {
      "header": "移動先フォルダ",
      "question": "移動先フォルダの URL を教えてください（共有ドライブ内のフォルダ URL など）。\nPlease provide the URL of the destination folder.",
      "type": "text",
      "placeholder": "https://drive.google.com/drive/folders/..."
    }
  ]
}
```

---

## Step 3 — スキャン（ファイル一覧の作成）

処理中です。しばらくお待ちください。 / Processing… Please wait.

```bash
python3 python/scripts/tools/drive_migrator.py scan "<SOURCE_URL>" "<DEST_URL>"
```

Windows の場合 / On Windows:
```bat
python python\scripts\tools\drive_migrator.py scan "<SOURCE_URL>" "<DEST_URL>"
```

スキャン結果（フォルダ数・ファイル数・ショートカット数）をユーザーに表示する。
Report the scan results (folder count, file count, shortcut count) to the user.

---

## Step 4 — 実行確認

スキャン結果を伝えたうえで、実行してよいか確認する。

```json
{
  "questions": [
    {
      "header": "実行確認",
      "question": "上記の内容で移行を実行しますか？\n（ショートカットはゴミ箱へ移動します。中断しても再実行で再開できます。）\nProceed with the migration?",
      "type": "yesno"
    }
  ]
}
```

「いいえ」の場合はキャンセルをユーザーに伝えて終了する。

---

## Step 5 — 実行

ファイル数が多い場合（目安: 1,000件超）、個々のファイル名をすべてコンテキストに取り込むとトークンを大量消費します。
そのため **出力はログファイルに書き出し**、モデルには末尾の要約だけ見せます。

処理中です。しばらくお待ちください。 / Processing… Please wait.

**Mac / Linux:**
```bash
python3 python/scripts/tools/drive_migrator.py execute > tmp/migration_log.txt 2>&1; echo "EXIT:$?"
```

**Windows:**
```bat
python python\scripts\tools\drive_migrator.py execute > tmp\migration_log.txt 2>&1 & echo EXIT:%ERRORLEVEL%
```

コマンド完了後、ログ末尾（要約部分）を取得してユーザーに報告する：

```bash
tail -40 tmp/migration_log.txt
```

Windows:
```bat
powershell -Command "Get-Content tmp\migration_log.txt -Tail 40"
```

---

## Step 6 — 結果報告

ログ末尾の出力をもとにユーザーに伝える。特に以下を明示する：

- ✅ 正常に移動・コピーされたファイル数
- ⚠️ コピーはできたが元ファイルを削除できなかったファイル（手動確認が必要）
- 🗑 ゴミ箱に移動したショートカット（Drive のゴミ箱から30日以内に復元可能）
- ✗ 失敗したファイルとその理由

---

## Step 7 — 中断・再開が必要な場合

`execute` を途中で止めても、再実行すると **完了済みタスクは自動スキップ**して続きから再開します。
スキャンのやり直しは不要です。

```bash
# 再開（ログを追記）
python3 python/scripts/tools/drive_migrator.py execute >> tmp/migration_log.txt 2>&1; echo "EXIT:$?"
```

現在の進捗を確認するだけなら：
```bash
python3 python/scripts/tools/drive_migrator.py status
```

---

## 注意事項 / Notes

- **タスクファイル**: `tmp/migration_tasks.json` に進捗が保存される。削除するとやり直しになる
- **ログファイル**: `tmp/migration_log.txt` に全ファイルの処理結果が記録される
- **ショートカット**: 移行不可のためゴミ箱に移動する。Drive のゴミ箱から30日以内に復元できる
- **コピー時の制限**: コピーはファイル内容のみ。バージョン履歴・コメントは引き継がれない
- **権限**: 移動先が共有ドライブの場合、ユーザーが「オーガナイザー」以上の権限を持っている必要がある
- **フォルダ一括移動**: `canMoveItemOutOfDrive=True` のサブフォルダは配下を再帰せず1回の API 呼び出しで移動する。配下に数万ファイルがあっても API コスト・トークン消費は変わらない
- **一括移動の失敗時**: execute 時に一括移動が失敗した場合、配下はスキャン済みでないため自動復帰は不可。scan をやり直すと `canMoveItemOutOfDrive=False` として再評価され、個別処理に切り替わる
- **トークン節約**: execute の出力は必ずログファイルへリダイレクトすること。数万ファイルをそのままコンテキストに流すと1日のトークン枠を超える可能性がある
