---
name: file-organizer
description: Interactively organizes files placed in the files/ folder. Asks the user how they want to sort (by type, date, keyword, or custom rules), then moves files accordingly. / files/フォルダに置いたファイルを対話形式で整理します。種類・日付・キーワード・カスタムルールなど、ユーザーの指示通りにファイルを仕分けします。
---

# ファイル整理スキル / File Organizer Skill

## 言語設定 / Language Policy
ユーザーへの全ての返答は日英バイリンガルで表示してください。日本語を先に表示し、改行の後に英語を続けてください。
Always respond to the user in both Japanese and English. Display Japanese first, then English on the next line.

## 概要 / Overview
`files/` フォルダに置かれたファイルを、ユーザーとの対話を通じて整理します。どのように分類したいかを確認してから、サブフォルダを作成してファイルを移動します。
Organizes files placed in the `files/` folder through interactive dialogue. Confirms how the user wants to categorize files, then creates subfolders and moves files accordingly.

## ワークフロー / Workflow

### Step 1 — files/ フォルダの確認 / Check the files/ folder

ドットファイルを除いた整理対象ファイルを確認する。OS に応じてコマンドを使い分ける。
Check for files to organize, excluding dotfiles. Use the appropriate command for the OS.

**Mac/Linux:**
```bash
find files/ -maxdepth 1 -not -name ".*" -type f
```

**Windows (PowerShell):**
```powershell
Get-ChildItem -Path files -File | Where-Object { $_.Name -notlike ".*" } | Select-Object -ExpandProperty Name
```

- `files/` フォルダが存在しない場合は作成してユーザーに伝える。 / If the `files/` folder doesn't exist, create it and inform the user.
- 上記コマンドの出力が空の場合（ドットファイルのみ、またはフォルダが空）は「整理するファイルがありません。`files/` フォルダにファイルを入れてから実行してください。」と伝えて**終了する**。 / If the command returns no output (only dotfiles, or folder is empty), say "There are no files to organize. Please place files in the `files/` folder and try again." and **stop**.
- ファイルがある場合は一覧を表示してユーザーに確認させる。 / If files are found, list them for the user to review.

### Step 2 — 整理方法を聞く / Ask how to organize

ファイル一覧を表示した後、以下の選択肢を提示する。
After showing the file list, present the following options.

```
どのように整理しますか？ / How would you like to organize these files?

1. 種類別（拡張子ごとにフォルダ分け）
   By file type (folder per extension)
2. 日付別（更新日の年月ごとにフォルダ分け）
   By date (folder per year/month based on modification date)
3. キーワード別（ファイル名に含まれるキーワードでフォルダ分け）
   By keyword (folder per keyword found in filenames)
4. カスタム（どのファイルをどのフォルダに入れるか個別に指定）
   Custom (specify individually which files go where)
```

ユーザーの返答が曖昧な場合は追加で質問して、整理方法を明確にしてから実行する。
If the user's answer is ambiguous, ask follow-up questions to clarify before proceeding.

### Step 3 — 整理プランを提示する / Show the organization plan

実際にファイルを移動する前に、プランを箇条書きで見せる。例：
Before moving any files, show the plan as a bullet list. Example:

```
整理プラン / Organization Plan:
・files/PDF/      ← report.pdf, invoice.pdf
・files/Excel/    ← budget.xlsx, data.xlsx
・files/Word/     ← minutes.docx
```

「この内容で整理しますか？（はい / いいえ）」と確認を取る。
Ask: "Shall I proceed with this plan? (Yes / No)"

「いいえ」の場合はStep 2に戻って整理方法を再確認する。
If "No", return to Step 2 and re-confirm the organization method.

### Step 4 — ファイルを移動する / Move files

ユーザーが承認したら、プラン通りにサブフォルダを作成してファイルを移動する。
Once approved, create subfolders and move files as planned.

フォルダの作成とファイルの移動は **1ファイルずつ** 実行する（複数ファイルをまとめて移動しない）。
Create folders and move files **one file at a time** — do not batch multiple files in a single command.

**Mac/Linux:**
```bash
mkdir -p "files/<フォルダ名>"
mv "files/<ファイル名>" "files/<フォルダ名>/"
```

**Windows (PowerShell):**
```powershell
New-Item -ItemType Directory -Force -Path "files\<フォルダ名>"
Move-Item -Path "files\<ファイル名>" -Destination "files\<フォルダ名>\"
```

移動済みファイルの数と行き先を都度報告する。
Report the number of files moved and their destinations as you go.

### Step 5 — 完了報告 / Report completion

整理が完了したら以下の形式で報告する。
Report in the following format when done.

```
整理完了しました。/ Organization complete.

・files/PDF/      2ファイル / 2 files
・files/Excel/    2ファイル / 2 files
・files/Word/     1ファイル / 1 file

計 5ファイルを整理しました。/ 5 files organized in total.
```

## 整理方法の詳細 / Organization Method Details

### 1. 種類別 / By file type

拡張子ごとに以下のフォルダ名を使う。拡張子が該当しない場合は`その他-Others`に入れる。
Use the following folder names per extension. Unknown extensions go into `その他-Others`.

| 拡張子 / Extension | フォルダ名 / Folder name |
|---|---|
| `.pdf` | `PDF` |
| `.xlsx`, `.xls`, `.csv` | `Excel` |
| `.docx`, `.doc` | `Word` |
| `.pptx`, `.ppt` | `PowerPoint` |
| `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp` | `画像-Images` |
| `.mp4`, `.mov`, `.avi` | `動画-Videos` |
| `.mp3`, `.wav`, `.m4a` | `音声-Audio` |
| `.zip`, `.tar.gz`, `.7z` | `アーカイブ-Archives` |
| その他 / Others | `その他-Others` |

> ⚠️ フォルダ名に `/` を含めない。Windows では `/` がパス区切り文字として扱われ、意図しない階層が作成される。代わりに `-` を使う。
> ⚠️ Do not include `/` in folder names. On Windows, `/` is treated as a path separator and will create unintended subdirectories. Use `-` instead.

### 2. 日付別 / By date

ファイルの更新日（`mtime`）を使って `YYYY-MM` 形式のフォルダを作成する。
Use the file's modification time (`mtime`) to create folders in `YYYY-MM` format.

**Mac:**
```bash
stat -f "%Sm" -t "%Y-%m" "files/<filename>"
```

**Linux:**
```bash
stat --format="%y" "files/<filename>" | cut -c1-7
```

**Windows (PowerShell):**
```powershell
(Get-Item "files\<filename>").LastWriteTime.ToString("yyyy-MM")
```

### 3. キーワード別 / By keyword

ユーザーにキーワードとフォルダ名のペアを聞く。例：
Ask the user for keyword-to-folder pairs. Example:

```
キーワード → フォルダ名 / Keyword → Folder name
請求書 / invoice → 請求書
報告書 / report  → 報告書
議事録 / minutes → 議事録
```

ファイル名にキーワードが含まれる場合（大文字小文字を区別しない）、そのフォルダに入れる。
If the filename contains a keyword (case-insensitive), place it in that folder.

複数キーワードにマッチする場合は最初にマッチしたルールを優先し、ユーザーに通知する。
If a file matches multiple keywords, apply the first matching rule and notify the user.

どのキーワードにもマッチしないファイルは `その他-Others` に入れることをユーザーに提案する。
For files matching no keywords, suggest placing them in `その他-Others`.

### 4. カスタム / Custom

ファイル名を一つずつ表示して、どのフォルダに移動するか聞く。既存サブフォルダがある場合はその候補も表示する。
Display each filename one at a time and ask which folder to move it to. Show existing subfolders as options.

## 注意事項 / Notes

- **上書き確認**: 移動先に同名ファイルが存在する場合は移動を止め、ユーザーに確認する。 / **Overwrite check**: If a file with the same name already exists at the destination, stop and ask the user.
- **隠しファイルはスキップ**: `.gitkeep` などドット始まりのファイルは整理対象に含めない。 / **Skip hidden files**: Exclude files starting with `.` (e.g., `.gitkeep`) from organization.
- **サブフォルダはスキップ**: `files/` 直下のファイルのみ対象。すでにサブフォルダに入っているファイルは整理しない。 / **Skip subfolders**: Only organize files directly in `files/`. Do not touch files already in subfolders.
- **1ファイルずつ移動**: 複数ファイルを1コマンドにまとめると失敗しやすい。ファイルごとに `Move-Item` / `mv` を実行する。 / **Move one file at a time**: Batching multiple files in one command is error-prone. Run `Move-Item` / `mv` per file.
- **フォルダ名に `/` を使わない**: Windows では `/` がパス区切り文字になる。 / **No `/` in folder names**: On Windows, `/` acts as a path separator.
- **元に戻す方法**: 整理前の状態はわからないため、必要に応じてユーザーに手動での確認を促す。 / **Undo**: The pre-organization state is not recorded, so prompt the user to verify manually if needed.

## 使用例 / Examples

- 「ファイルを整理して」→ `/file-organizer` を起動して対話開始
  "Organize my files" → Launch `/file-organizer` and start dialogue
- 「files フォルダを種類別に仕分けして」→ 確認後すぐに種類別整理を実行
  "Sort the files folder by type" → Confirm then execute type-based organization immediately
- 「請求書と報告書でフォルダを分けて」→ キーワード別整理として実行（「請求書」「報告書」をキーワードに使用）
  "Separate invoices and reports into folders" → Execute as keyword-based organization using "請求書" and "報告書" as keywords
