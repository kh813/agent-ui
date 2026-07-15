---
name: download-from-drive
description: Downloads a file or folder from Google Drive to the local files/ folder. Asks for the Drive URL, previews what will be downloaded, and confirms before overwriting existing files. / Google Driveのファイルまたはフォルダをローカルのfiles/フォルダにダウンロードします。URLを確認し、ダウンロード内容をプレビューして、既存ファイルの上書き前に確認します。
---

# Google Drive ダウンロードスキル / Download from Drive Skill

## 言語設定 / Language Policy
ユーザーへの全ての返答は日英バイリンガルで表示してください。日本語を先に表示し、改行の後に英語を続けてください。
Always respond to the user in both Japanese and English. Display Japanese first, then English on the next line.

## 概要 / Overview
Google Drive 上のファイルまたはフォルダを `files/` フォルダにダウンロードします。フォルダの場合はサブフォルダ構造を保持して再帰的にダウンロードします。Google ネイティブ形式（Docs / Sheets / Slides）はダウンロード非対応としてスキップします。

Downloads a file or folder from Google Drive to the `files/` folder. For folders, the subfolder structure is preserved recursively. Google-native formats (Docs, Sheets, Slides) are not supported and will be skipped.

## ワークフロー / Workflow

### Step 1 — Drive URL を確認する / Get the Drive URL

ユーザーのメッセージに URL が含まれている場合はそれを使う。含まれていない場合は聞く。
If the user's message includes a URL, use it. Otherwise, ask:

`ask_user` ツールで URL を入力してもらう。
Use the `ask_user` tool to request the URL:

```json
{
  "questions": [
    {
      "header": "Drive URL",
      "question": "ダウンロードしたいファイルまたはフォルダの Google Drive URL を教えてください。\nPlease share the Google Drive URL of the file or folder you'd like to download.",
      "type": "text",
      "placeholder": "https://drive.google.com/file/d/..."
    }
  ]
}
```

**対応 URL 形式 / Supported URL formats:**
- ファイル / File: `https://drive.google.com/file/d/FILE_ID/view`
- フォルダ / Folder: `https://drive.google.com/drive/folders/FOLDER_ID`

**非対応 URL（エラーになります）/ Unsupported URLs:**
- Google ドキュメント: `https://docs.google.com/document/...`
- Google スプレッドシート: `https://docs.google.com/spreadsheets/...`
- Google スライド: `https://docs.google.com/presentation/...`
  → これらは「Google ネイティブ形式のためダウンロードできません」と伝えて**終了**する。
  → Tell the user "Cannot download Google native formats" and **stop**.

### Step 2 — dry-run で内容を確認する / Preview with dry-run

```bash
# Mac/Linux
python3 python/scripts/tools/drive_download.py "URL" --dry-run

# Windows
python python\scripts\tools\drive_download.py "URL" --dry-run
```

出力結果をユーザーに見せて確認を取る。
Show the output to the user and confirm before proceeding.

出力マーカーの意味 / Output markers:
- `✓` : 新規ダウンロード / New file
- `⚠` : ローカルに同名ファイルあり（上書き対象）/ Same name exists locally (will overwrite)
- `⊘` : Google ネイティブ形式のためスキップ / Google native format — skipped

**フォルダのダウンロード先 / Folder download destination:**
`files/<フォルダ名>/` にフォルダ構造を再現してダウンロードされます。
Contents are downloaded to `files/<folder-name>/` with the folder structure preserved.

### Step 3 — 競合がある場合はユーザーに確認する / Confirm conflict handling

dry-run の出力に `⚠`（競合）が含まれる場合は、ユーザーに確認する。
If the dry-run output contains `⚠` (conflicts), ask the user:

`ask_user` ツールで選択してもらう。
Use the `ask_user` tool:

```json
{
  "questions": [
    {
      "header": "Conflict",
      "question": "以下のファイルはすでにローカルに存在します。どうしますか？\nThe following files already exist locally. What would you like to do?\n・[競合ファイル一覧 / list of conflicting files]",
      "type": "choice",
      "options": [
        { "label": "上書き / Overwrite", "description": "既存ファイルを上書きしてダウンロード (--overwrite)" },
        { "label": "スキップ / Skip", "description": "既存ファイルはスキップ、新規ファイルのみダウンロード (--skip)" },
        { "label": "キャンセル / Cancel", "description": "ダウンロードを中止する" }
      ]
    }
  ]
}
```

ユーザーが「キャンセル」を選んだ場合はそこで**終了**する。
If the user chooses Cancel, **stop**.

### Step 4 — ダウンロードを実行する / Execute download

競合なし、または Step 3 でユーザーが選択した場合：
If no conflicts, or after user choice in Step 3:

```bash
# 競合なし / No conflicts
python3 python/scripts/tools/drive_download.py "URL"

# 上書き / Overwrite
python3 python/scripts/tools/drive_download.py "URL" --overwrite

# スキップ / Skip existing
python3 python/scripts/tools/drive_download.py "URL" --skip
```

### Step 5 — 完了を報告する / Report completion

ダウンロード結果をユーザーに伝える。
Report the download results to the user.

```
「X 件のファイルを files/ にダウンロードしました。」
"X file(s) downloaded to files/."
```

Google ネイティブ形式がスキップされた場合はその旨も伝える。
If Google-native files were skipped, mention that as well.

## 注意事項 / Notes

- **認証**: 初回実行時はブラウザが開き、Googleアカウントへのログインが必要です。以降はトークンが再利用されます（`drive_upload` と共通）。 / **Auth**: On first run, a browser opens for Google login. The token is shared with the `upload-to-drive` skill.
- **Google ネイティブ形式非対応**: Docs / Sheets / Slides / Forms など Google 固有の形式はダウンロードできません。フォルダ内にこれらが含まれる場合は `⊘` でスキップされます。 / **Google native formats not supported**: Docs, Sheets, Slides, Forms, etc. cannot be downloaded. They are skipped with `⊘` when found in folders.
- **フォルダは再帰的にダウンロード**: サブフォルダも含めて構造を維持してダウンロードします。 / **Folders downloaded recursively**: Subfolder structure is preserved.
- **大きなフォルダ**: ファイル数が多い場合、一覧取得に時間がかかることがあります。 / **Large folders**: Scanning many files may take a moment.

## 使用例 / Examples

- 「この Drive のファイルをダウンロードして」 + URL → Step 2 から実行
  "Download this Drive file" + URL → Run from Step 2
- 「このフォルダを files に保存して」 + フォルダ URL → フォルダ構造ごとダウンロード
  "Save this folder to files/" + folder URL → Download with folder structure
