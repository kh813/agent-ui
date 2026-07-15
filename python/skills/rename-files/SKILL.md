---
name: rename-files
description: Bulk-renames files in the files/ folder. Supports sequential numbering, date prefix, string replacement, and regex. Always previews changes before executing. / files/フォルダのファイルを一括リネームします。連番付与・日付プレフィックス・文字列置換・正規表現に対応。実行前に必ずプレビューを表示します。
---

# ファイル一括リネームスキル / Rename Files Skill

## 言語設定 / Language Policy
ユーザーへの全ての返答は日英バイリンガルで表示してください。日本語を先に表示し、改行の後に英語を続けてください。
Always respond to the user in both Japanese and English. Display Japanese first, then English on the next line.

## 概要 / Overview
`files/` フォルダにあるファイルを一括リネームします。リネームの方法を対話的に確認し、実行前にプレビューを表示してから変更を適用します。

Bulk-renames files in the `files/` folder. Confirms the rename method interactively, shows a preview before applying changes.

## ワークフロー / Workflow

### Step 1 — files/ の内容を確認する / Check files/ contents

```bash
find files/ -maxdepth 1 -not -name ".*" -type f | sort
```

出力が空の場合は「`files/` フォルダにリネームしたいファイルを入れてください。」と伝えて**終了**する。
If empty: "Please place files to rename in the `files/` folder." and **stop**.

ファイルが見つかった場合は一覧を表示する。
If files are found, display the list.

### Step 2 — リネーム方法を確認する / Choose rename mode

ユーザーのメッセージからリネーム方法が読み取れる場合はそれを使う。読み取れない場合は以下を提示する。
If the user's message implies a rename method, use it. Otherwise, present options:

```
どのようにリネームしますか？ / How would you like to rename the files?

1. 連番付与     report_001.pdf, report_002.pdf, ...
   Sequential numbering

2. 日付プレフィックス   20260514_report.pdf, ...
   Date prefix

3. 文字列置換   "draft" → "final" など / e.g. "draft" → "final"
   String replacement

4. 正規表現     パターンに一致する部分を置換 / Replace parts matching a pattern
   Regex replacement
```

### Step 3 — モード別のパラメータを確認する / Gather mode parameters

#### モード 1: 連番付与 / Sequential

以下を確認する。
Ask:
- 「ファイル名のベースは何にしますか？（例: `report`）省略すると元のファイル名に連番を付けます。」
  "What base name to use? (e.g., `report`) Leave blank to append numbers to the original names."
- 「番号は何番から始めますか？（デフォルト: 1）」
  "Starting number? (default: 1)"
- 「並び順は？（名前順 / 更新日順）」
  "Sort order? (by name / by date)"

コマンド例 / Command example:
```bash
# ベース名あり: report_001.pdf, report_002.pdf, ...
python3 python/scripts/tools/rename_files.py --sequential --prefix report --dry-run

# 元の名前に連番: filename_001.pdf, filename_002.pdf, ...
python3 python/scripts/tools/rename_files.py --sequential --dry-run

# 更新日順に連番
python3 python/scripts/tools/rename_files.py --sequential --sort date --dry-run

# 開始番号を指定
python3 python/scripts/tools/rename_files.py --sequential --prefix report --start 10 --dry-run
```

#### モード 2: 日付プレフィックス / Date prefix

以下を確認する。
Ask:
- 「日付はファイルの更新日を使いますか、それとも今日の日付を使いますか？」
  "Use the file's modification date, or today's date?"
- 「日付フォーマットは？（例: `20260514`（デフォルト）/ `2026-05-14` / `2026_05_14`）」
  "Date format? (e.g., `20260514` (default) / `2026-05-14` / `2026_05_14`)"

コマンド例 / Command example:
```bash
# 更新日を使用（デフォルト）: 20260514_report.pdf
python3 python/scripts/tools/rename_files.py --date-prefix --dry-run

# 今日の日付を使用
python3 python/scripts/tools/rename_files.py --date-prefix --date-source today --dry-run

# フォーマット指定: 2026-05-14_report.pdf
python3 python/scripts/tools/rename_files.py --date-prefix --date-format "%Y-%m-%d" --dry-run
```

#### モード 3: 文字列置換 / String replacement

以下を確認する。
Ask:
- 「置換前の文字列は？」 / "String to replace?"
- 「置換後の文字列は？（削除する場合は空文字）」 / "Replacement string? (empty string to delete)"

コマンド例 / Command example:
```bash
# "draft" → "final"
python3 python/scripts/tools/rename_files.py --replace draft final --dry-run

# "_v1" を削除
python3 python/scripts/tools/rename_files.py --replace "_v1" "" --dry-run
```

#### モード 4: 正規表現 / Regex

以下を確認する。
Ask:
- 「正規表現パターンは？」 / "Regex pattern?"
- 「置換後の文字列は？（`\1`, `\2` でグループ参照可）」
  "Replacement string? (`\1`, `\2` for group references)"

コマンド例 / Command example:
```bash
# 末尾の "_old" を削除
python3 python/scripts/tools/rename_files.py --regex "_old$" "" --dry-run

# "2024" または "2025" を "2026" に置換
python3 python/scripts/tools/rename_files.py --regex "202[45]" "2026" --dry-run
```

### Step 4 — プレビューを表示して確認する / Preview and confirm

`--dry-run` で結果を表示してユーザーに確認を取る。
Run with `--dry-run`, show output, and confirm:

```
「この内容でリネームしますか？（はい / いいえ）」
"Shall I proceed with these renames? (Yes / No)"
```

- `✓` : リネームされるファイル / File will be renamed
- `-` : 変更なし / No change
- `✗` : 同名ファイルが存在するためスキップ / Skipped (target already exists)

「いいえ」の場合は Step 2 に戻る。
If "No", return to Step 2.

### Step 5 — リネームを実行する / Execute rename

`--dry-run` を外して実行する。
Run without `--dry-run`:

```bash
python3 python/scripts/tools/rename_files.py [同じ引数 / same args without --dry-run]
```

### Step 6 — 完了を報告する / Report completion

```
「X 件のファイルをリネームしました。」
"X file(s) renamed."
```

## 特定ファイルのみ対象にする / Target specific files

全ファイルではなく一部のみリネームする場合はファイルパスを指定する。
To rename only specific files, specify file paths:

```bash
python3 python/scripts/tools/rename_files.py files/report.pdf files/memo.docx --sequential --dry-run
```

## 注意事項 / Notes

- **隠しファイルはスキップ**: `.gitkeep`, `.DS_Store` などは対象外。 / **Hidden files skipped**: `.gitkeep`, `.DS_Store`, etc. are excluded.
- **同名ファイルは自動スキップ**: リネーム先に同名ファイルが存在する場合はスキップし、エラーにはならない。 / **Auto-skip on conflict**: If the target name already exists, the file is skipped (not overwritten).
- **元に戻す方法がない**: リネームは元に戻せません。プレビューで必ず確認してから実行してください。 / **Irreversible**: Renames cannot be undone. Always check the preview before executing.
- **拡張子は変更しない**: 全モードでファイルの拡張子は変更されません。 / **Extension unchanged**: File extensions are never modified by any mode.

## 使用例 / Examples

- 「files の写真に今日の日付を付けて」→ `--date-prefix --date-source today` で実行
  "Add today's date to photos in files/" → Run with `--date-prefix --date-source today`
- 「全部 report_001, report_002 という形にして」→ `--sequential --prefix report` で実行
  "Rename all to report_001, report_002, ..." → Run with `--sequential --prefix report`
- 「ファイル名の "draft" を "final" に変えて」→ `--replace draft final` で実行
  "Replace 'draft' with 'final' in filenames" → Run with `--replace draft final`
