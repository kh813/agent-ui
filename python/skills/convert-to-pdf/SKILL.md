---
name: convert-to-pdf
description: Converts Word and Excel files to PDF on Windows using Microsoft Office COM automation (pywin32). Converts individual files or all supported files in a folder. Source files are kept as-is; PDFs are saved alongside them. / Word・ExcelをPDFに変換します（Windows専用・Microsoft Office COM使用）。ファイル単位またはフォルダ内の一括変換に対応。元ファイルはそのまま残し、PDFを同じ場所に保存します。
---

# PDF変換スキル / Convert to PDF Skill

## 言語設定 / Language Policy
ユーザーへの全ての返答は日英バイリンガルで表示してください。日本語を先に表示し、改行の後に英語を続けてください。
Always respond to the user in both Japanese and English. Display Japanese first, then English on the next line.

## 概要 / Overview
Word / Excel ファイルを PDF に変換します。Microsoft Office（Word / Excel）の COM 機能を使うため、**Windows 専用**です。外部ツールのインストールは不要で、すでにインストール済みの Microsoft Office を使って変換します。元ファイルはそのまま残し、変換後の PDF は元ファイルと同じフォルダに保存されます。

Converts Word / Excel files to PDF using Microsoft Office COM automation. **Windows only** — requires Microsoft Word and Excel installed. No additional tools needed. Source files are kept as-is; PDFs are saved in the same folder as the source.

**対応形式 / Supported formats:**
| 形式 / Format | 拡張子 / Extensions |
|---|---|
| Word | `.docx` `.doc` |
| Excel | `.xlsx` `.xls` |

PowerPoint (.pptx / .ppt) および他の形式は対応していません。
PowerPoint (.pptx / .ppt) and other formats are not supported.

## ワークフロー / Workflow

### Step 1 — 変換対象を確認する / Identify targets

ユーザーのメッセージから変換対象（ファイル・フォルダ）が読み取れる場合はそれを使う。
If the user's message specifies which files or folders to convert, use those.

指定がない場合は `files/` フォルダを確認する。
If not specified, check the `files/` folder:

```bat
python -c "import pathlib; files=sorted(p.name for p in pathlib.Path('files').iterdir() if p.is_file() and not p.name.startswith('.')); [print(f) for f in files]"
```

`files/` にファイルがない場合は「変換したいファイルを `files/` フォルダに入れてください。」と伝えて**終了**する。
If `files/` is empty: "Please place files to convert in the `files/` folder." and **stop**.

対応形式以外のファイルが含まれる場合は「変換できない形式のファイルが含まれています（例: .pptx は対象外です）。」と事前に伝える。
If unsupported formats are included, inform the user upfront (e.g., ".pptx is not supported").

ファイルが見つかった場合は一覧を表示し、どれを変換するか確認する（全部 or 一部）。
If files are found, list them and confirm which to convert (all or specific ones).

### Step 2 — dry-run でプレビューする / Preview with dry-run

```bat
python python\scripts\tools\convert_to_pdf.py <PATH1> [PATH2 ...] --dry-run
```

**PATH にはファイルまたはフォルダを指定できます。フォルダを指定した場合は直下の対応ファイルをすべて変換します。**
**PATH can be a file or a folder. For folders, all supported files directly inside are converted.**

出力の見方 / Reading the output:
- `✓` : 変換対象 / Will be converted
- `!` : 変換非対応の形式（スキップ）/ Unsupported format (skipped)
- `※ 既存PDFを上書き` : 同名PDFがすでに存在する / Existing PDF will be overwritten

プレビューをユーザーに見せて確認を取る。
Show the preview and confirm:

「この内容で変換しますか？（はい / いいえ）」
"Shall I proceed with these conversions? (Yes / No)"

### Step 3 — 変換を実行する / Execute conversion

```bat
python python\scripts\tools\convert_to_pdf.py <PATH1> [PATH2 ...]
```

変換中は Microsoft Word または Excel が一時的にバックグラウンドで起動します。変換が終わると自動的に終了します。
During conversion, Microsoft Word or Excel briefly launches in the background and closes automatically when done.

### Step 4 — 完了を報告する / Report completion

```
「X 件のファイルを PDF に変換しました。PDF は元ファイルと同じフォルダに保存されています。」
"X file(s) converted to PDF. PDFs are saved alongside the source files."
```

エラーがあった場合はファイル名とエラー内容を伝える。
If there were errors, report the filename and error message.

## エラーが出た場合 / Troubleshooting

| エラー / Error | 原因と対処 / Cause & Fix |
|---|---|
| `Microsoft Word が見つかりません` | Microsoft Word がインストールされていないか、ライセンスが無効です。 / Word not installed or license inactive. |
| `Microsoft Excel が見つかりません` | Microsoft Excel がインストールされていないか、ライセンスが無効です。 / Excel not installed or license inactive. |
| ファイルが開けない | 対象ファイルが Word / Excel で開かれている可能性があります。閉じてから再実行してください。 / File may be open in Word/Excel — close it and retry. |
| パスワード保護エラー | パスワードで保護されたファイルは変換できません。 / Password-protected files cannot be converted. |

## 使用例 / Examples

- 「files の report.docx を PDF にして」
  → `python python\scripts\tools\convert_to_pdf.py files\report.docx`

- 「files フォルダの中の Excel を全部 PDF にして」
  → `python python\scripts\tools\convert_to_pdf.py files\`
  （フォルダ内の .xlsx / .xls をすべて変換）

- 「この Word と Excel を PDF にして」（複数指定）
  → `python python\scripts\tools\convert_to_pdf.py files\report.docx files\budget.xlsx`

## 注意事項 / Notes

- **Windows 専用**: macOS / Linux では動作しません。 / **Windows only**: Does not work on macOS or Linux.
- **Microsoft Office 必須**: Word / Excel がインストールされ有効化されている必要があります。 / **Requires Microsoft Office**: Word and Excel must be installed and activated.
- **元ファイルは変更されません**: 変換後も元の .docx / .xlsx はそのまま残ります。 / **Source files unchanged**: Original files are never modified or deleted.
- **フォルダ指定は非再帰**: フォルダを指定した場合、サブフォルダ内のファイルは対象外です。 / **Folder scan is non-recursive**: Subfolders are not scanned.
- **パスワード保護ファイル非対応**: パスワードで保護されたファイルは変換できません。 / **No password-protected files**: Cannot convert password-protected files.
