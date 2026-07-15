---
name: upload-to-drive
description: Uploads specified files or folders from files/ to a Google Drive folder. Asks which items to upload if not specified, asks for destination each time, and confirms before overwriting. / files/フォルダの指定ファイル・フォルダをGoogle Driveにアップロードします。対象未指定時は対話的に確認し、アップロード先をその都度尋ね、上書き前に確認します。
---

# Google Drive アップロードスキル / Upload to Drive Skill

## 言語設定 / Language Policy
ユーザーへの全ての返答は日英バイリンガルで表示してください。日本語を先に表示し、改行の後に英語を続けてください。
Always respond to the user in both Japanese and English. Display Japanese first, then English on the next line.

## 概要 / Overview
`files/` フォルダにある特定のファイルまたはフォルダを Google Drive の指定フォルダにアップロードします。対象が指定されていない場合は対話的に確認します。アップロード先はその都度確認します。Drive 上に同名ファイルが存在する場合は、上書きするかどうかをユーザーに確認してから実行します。

Uploads specific files or folders from the `files/` folder to a specified Google Drive folder. If no targets are specified, asks interactively. The destination is confirmed each time. If a file with the same name already exists on Drive, the user is asked whether to overwrite before proceeding.

## ワークフロー / Workflow

### Step 1 — files/ の内容を確認する / Check files/ contents

```bash
find files/ -maxdepth 2 -not -name ".*" \( -type f -o -type d \) | sort
```

出力が空の場合（`.gitkeep` のみの場合を含む）は「`files/` フォルダにアップロードしたいファイルまたはフォルダを入れてください。」と伝えて**終了**する。
If empty (including only `.gitkeep`): "Please place files or folders to upload in the `files/` folder." and **stop**.

### Step 2 — アップロード対象を確認する / Confirm upload targets

ユーザーのメッセージでアップロード対象（ファイル名・フォルダ名）が指定されている場合はそれを使う。
If the user's message specifies which files or folders to upload, use those.

指定がない場合は、Step 1 の一覧を見せて対話的に確認する。
If not specified, show the list from Step 1 and ask:

`ask_user` ツールで対象を入力してもらう。
Use the `ask_user` tool:

```json
{
  "questions": [
    {
      "header": "Upload Target",
      "question": "`files/` フォルダには以下のアイテムがあります。どれをアップロードしますか？（複数指定・フォルダ丸ごとも可能）\n[一覧 / list]\n\nWhich items would you like to upload? (Multiple items and full folders are supported.)",
      "type": "text",
      "placeholder": "e.g., report.pdf, data/"
    }
  ]
}
```

### Step 3 — アップロード先フォルダを尋ねる / Ask for destination folder

ユーザーに以下を確認する。
Ask the user:

`ask_user` ツールで宛先を入力してもらう。
Use the `ask_user` tool:

```json
{
  "questions": [
    {
      "header": "Drive Folder",
      "question": "どの Google Drive フォルダにアップロードしますか？フォルダの URL または ID を教えてください。\nWhich Google Drive folder should I upload to? Please share the folder URL or ID.",
      "type": "text",
      "placeholder": "https://drive.google.com/drive/folders/..."
    }
  ]
}
```

- **URL 例 / URL example**: `https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz`
  → フォルダ ID は URL 末尾の英数字 / The folder ID is the alphanumeric string at the end
- **ID 例 / ID example**: `1AbCdEfGhIjKlMnOpQrStUvWxYz`

URL が渡された場合は `/folders/` 以降の文字列をフォルダ ID として使用する。
If a URL is given, extract the folder ID from the part after `/folders/`.

### Step 4 — dry-run で内容を確認する / Preview with dry-run

```bash
# Mac/Linux
python3 python/scripts/tools/drive_upload.py <PATH1> [PATH2 ...] --dry-run --folder <FOLDER_ID>

# Windows
python python\scripts\tools\drive_upload.py <PATH1> [PATH2 ...] --dry-run --folder <FOLDER_ID>
```

出力結果をユーザーに見せて確認を取る。
Show the output to the user and confirm before proceeding.

- `✓` : 新規アップロード / New file
- `⚠` : Drive に同名ファイルあり（上書き対象）/ Same name exists on Drive (will overwrite)
- `📁` : 新規フォルダ（Drive 上に存在しない）/ New folder (does not exist on Drive)
- `📂` : 既存フォルダ（Drive 上に存在する）/ Existing folder (already on Drive)

### Step 5 — 競合がある場合はユーザーに確認する / Confirm conflict handling

dry-run の出力に `⚠`（競合）が含まれる場合は、ユーザーに確認する。
If the dry-run output contains `⚠` (conflicts), ask the user:

`ask_user` ツールで選択してもらう。
Use the `ask_user` tool:

```json
{
  "questions": [
    {
      "header": "Conflict",
      "question": "以下のファイルはすでに Drive に存在します。どうしますか？\nThe following files already exist on Drive. What would you like to do?\n・[競合ファイル一覧 / list of conflicting files]",
      "type": "choice",
      "options": [
        { "label": "上書き / Overwrite", "description": "既存ファイルを上書きしてアップロード (--overwrite)" },
        { "label": "スキップ / Skip", "description": "既存ファイルはスキップ、新規ファイルのみアップロード (--skip)" },
        { "label": "キャンセル / Cancel", "description": "アップロードを中止する" }
      ]
    }
  ]
}
```

ユーザーが「キャンセル」を選んだ場合はそこで**終了**する。
If the user chooses Cancel, **stop**.

### Step 6 — アップロードを実行する / Execute upload

競合なし、または Step 5 でユーザーが選択した場合：
If no conflicts, or after user choice in Step 5:

```bash
# 競合なし / No conflicts
python3 python/scripts/tools/drive_upload.py <PATH1> [PATH2 ...] --folder <FOLDER_ID>

# 上書き / Overwrite
python3 python/scripts/tools/drive_upload.py <PATH1> [PATH2 ...] --overwrite --folder <FOLDER_ID>

# スキップ / Skip existing
python3 python/scripts/tools/drive_upload.py <PATH1> [PATH2 ...] --skip --folder <FOLDER_ID>
```

### Step 7 — 完了を報告する / Report completion

アップロード結果をユーザーに伝える。
Report the upload results to the user.

```
「X 件のファイルを [フォルダ名] にアップロードしました。」
"X file(s) uploaded to [folder name]."
```

## フォルダのアップロード / Folder upload

フォルダを指定すると、Drive 上に同名フォルダを作成（または既存フォルダを使用）して中身を再帰的にアップロードします。サブフォルダも自動で作成されます。

When a folder is specified, a folder with the same name is created on Drive (or an existing one is used), and its contents are uploaded recursively. Subfolders are created automatically.

```bash
# フォルダをまるごとアップロード / Upload entire folder
python3 python/scripts/tools/drive_upload.py files/reports --folder <FOLDER_ID>

# ファイルとフォルダを混在指定 / Mix of files and folders
python3 python/scripts/tools/drive_upload.py files/report.pdf files/data --folder <FOLDER_ID>
```

## 注意事項 / Notes

- **認証**: 初回実行時はブラウザが開き、Googleアカウントへのログインが必要です。以降はトークンが再利用されます。 / **Auth**: On first run, a browser opens for Google login. The token is reused afterwards.
- **隠しファイルはスキップ**: `.gitkeep`, `.DS_Store` などは対象外です。 / **Hidden files skipped**: Files like `.gitkeep`, `.DS_Store` are excluded.
- **パスは files/ 配下を指定**: アップロードするファイル・フォルダは `files/` フォルダ内のパスを指定してください。 / **Paths under files/**: Specify paths within the `files/` folder.

## 使用例 / Examples

- 「files の report.pdf を Drive にアップロードして」→ Step 2 でファイル確定、Step 3 から実行
  "Upload files/report.pdf to Drive" → Confirm file in Step 2, run from Step 3
- 「files の data フォルダを Drive にアップロードして」→ フォルダ再帰アップロード
  "Upload files/data folder to Drive" → Recursive folder upload
- 「files のファイルを Drive にアップロードして」（対象未指定）→ Step 2 で一覧を見せて確認
  "Upload files to Drive" (no target specified) → Show list in Step 2 and confirm
