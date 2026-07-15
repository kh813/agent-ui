---
name: convert-to-markdown
description: Converts files in files/ to Markdown (PDF, Word, Excel, PowerPoint, HTML, etc.). Use when asked to convert, read, extract or analyze documents. / files/フォルダのファイルをMarkdownに変換します。PDF・Word・Excel・PowerPointなどの変換・読み取り・分析を求められたときに使用してください。
---

# ファイル変換スキル / Markitdown Skill

## 言語設定 / Language Policy
ユーザーへの全ての返答は日英バイリンガルで表示してください。日本語を先に表示し、改行の後に英語を続けてください。
Always respond to the user in both Japanese and English. Display Japanese first, then English on the next line.

## 概要 / Overview
`files/` フォルダに置かれたファイルを [Markitdown](https://github.com/microsoft/markitdown) を使って Markdown 形式に変換します。変換後の `.md` ファイルは元のファイルと同じ場所（または指定ディレクトリ）に保存されます。

Converts files in the `files/` folder to Markdown using [Markitdown](https://github.com/microsoft/markitdown). Converted `.md` files are saved alongside the originals (or in a specified directory).

## 対応フォーマット / Supported Formats

| フォーマット / Format | 拡張子 / Extension |
|---|---|
| PDF | `.pdf` |
| Word | `.docx`, `.doc` |
| Excel | `.xlsx`, `.xls`, `.csv` |
| PowerPoint | `.pptx`, `.ppt` |
| HTML | `.html`, `.htm` |
| テキスト / Text | `.txt`, `.rtf`, `.xml`, `.json` |
| 電子書籍 / eBook | `.epub` |
| ZIP | `.zip`（内部ファイルを再帰変換 / recursively converts supported files inside） |
| 画像 / Image ※ | `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp` |
| 音声 / Audio ※ | `.mp3`, `.wav`, `.m4a` |

※ 画像・音声はメタデータのみ。テキスト認識・書き起こしには追加のAzure/OpenAI設定が必要です。
※ Images/audio extract metadata only. Text recognition or transcription requires additional Azure/OpenAI setup.

## ワークフロー / Workflow

### Step 1 — files/ フォルダを確認する / Check the files/ folder

```bash
find files/ -maxdepth 1 -not -name ".*" -type f
```

- 出力が空の場合：「`files/` フォルダに変換したいファイルを入れてください。」と伝えて**終了**する。
  If empty: "Please place files to convert in the `files/` folder." and **stop**.
- ファイルがあれば一覧を示し、変換方針をユーザーに確認する。

### Step 2 — 変換を実行する / Run the conversion

**全ファイルを変換 / Convert all files:**

```bash
# Mac/Linux
python3 python/scripts/tools/markitdown_convert.py --all

# Windows
python python\scripts\tools\markitdown_convert.py --all
```

**特定ファイルを変換 / Convert specific files:**

```bash
# Mac/Linux
python3 python/scripts/tools/markitdown_convert.py files/report.pdf files/budget.xlsx

# Windows
python python\scripts\tools\markitdown_convert.py files\report.pdf files\budget.xlsx
```

**出力先を指定する場合 / With custom output directory:**

```bash
python3 python/scripts/tools/markitdown_convert.py --all --output-dir files/converted
```

初回実行時は markitdown が自動インストールされます（数秒かかります）。
On first run, markitdown is installed automatically (a few seconds).

### Step 3 — 変換結果を確認する / Check results

スクリプト出力で各ファイルの成否（✓ / ✗）を確認する。
Check each file's result (✓ success / ✗ failure) from the script output.

### Step 4 — 内容を読み込む（必要な場合）/ Read converted content (if needed)

ユーザーがドキュメントの内容について質問している場合は、変換後の `.md` ファイルを読み込んで回答する。
If the user asks about document contents, read the converted `.md` files to answer.

```bash
find files/ -name "*.md" -not -name ".*"
```

## dry-run（変換前の確認）/ Dry-run (preview before converting)

```bash
python3 python/scripts/tools/markitdown_convert.py --all --dry-run
```

## 注意事項 / Notes

- **既存の `.md` ファイルは上書きされます** / **Existing `.md` files will be overwritten**
- **`.md` ファイル自体は変換対象外**（再変換しない）/ **`.md` files themselves are skipped**
- **隠しファイルはスキップ**（`.gitkeep` 等）/ **Hidden files are skipped** (e.g., `.gitkeep`)
- **画像・音声はメタデータのみ**：OCR・書き起こしには追加設定が必要 / **Images/audio: metadata only.** OCR/transcription needs additional setup

## 使用例 / Examples

- 「このPDFを読んで」→ `files/` にPDFがあれば変換して内容を報告
  "Read this PDF" → Convert PDF in `files/` and report content
- 「files フォルダのファイルをMarkdownに変換して」→ `--all` で全ファイルを変換
  "Convert files in the files folder to Markdown" → Convert all with `--all`
- 「budget.xlsx の内容を教えて」→ `files/budget.xlsx` を変換してシートの内容を分析
  "Tell me the contents of budget.xlsx" → Convert and analyze `files/budget.xlsx`
- 「変換後のファイルを全部読んで要約して」→ 変換後に `.md` ファイルを読み込んで要約
  "Read and summarize all converted files" → Convert then read `.md` files and summarize
