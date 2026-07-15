---
name: skill-catalog
description: 共有スキルカタログの操作。カタログ一覧・詳細・インポート・登録（共有）・取り下げ・オーナー変更。"skill-catalog list", "カタログを見たい", "スキルをインポート", "このスキルをカタログに登録して", "カタログから取り下げたい", "オーナーを変更して", "skill-catalog import/info/share/unshare/change-owner" などで起動。 / Browse, import, publish, unpublish, and transfer ownership of skills in the shared catalog.
---

# スキルカタログ / Skill Catalog

## 言語設定 / Language Policy
ユーザーへの全ての返答は日英バイリンガルで表示してください。日本語を先に表示し、改行の後に英語を続けてください。
Always respond to the user in both Japanese and English. Display Japanese first, then English on the next line.

## 概要 / Overview

グループ内で共有された SKILL.md を Google Drive のカタログから参照・取得し、自分のローカルスキルの登録・取り下げ・オーナー変更も行います。ローカルスキル自体の作成・編集・削除は `my-skills` スキルを使用してください。
Browse and retrieve skills shared within the group from the Google Drive catalog, and publish/unpublish your own local skills or transfer ownership. For creating, editing, or deleting the local skill itself, use the `my-skills` skill.

| サブコマンド | 説明 |
|---|---|
| `skill-catalog list` | カタログのスキル一覧を表示（キャッシュ利用） |
| `skill-catalog info <name>` | スキルの詳細を表示 |
| `skill-catalog import <name>` | スキルをインポート＆インストール |
| `skill-catalog update-index` | カタログインデックスをDriveから再取得（管理者用） |
| `skill-catalog share <name>` | ローカルスキルをカタログに登録・更新 |
| `skill-catalog unshare <name>` | カタログからスキルを取り下げ（ローカルは残す） |
| `skill-catalog change-owner <name>` | スキルのオーナーを変更 |

カタログの構成: `<owner>/<skill-name>.md`（例: `user.name/downloads.md`）

**OS別コマンド / OS-specific commands:** 以下のコマンドはすべて Mac/Linux 表記です。Windows では `python3` → `python`、パス区切りの `/` → `\` に読み替えて実行してください。
All commands below are written for Mac/Linux. On Windows, replace `python3` with `python` and forward slashes (`/`) with backslashes (`\`).

---

## 引数なし（ヘルプ表示）/ No Arguments — Show Help

ユーザーが `/skill-catalog` または「skill-catalog」とだけ入力してサブコマンドを指定しなかった場合、以下の形式でヘルプを表示してください。
If the user types `/skill-catalog` or "skill-catalog" without specifying a subcommand, display help in the following format:

```
スキルカタログ / Skill Catalog

使い方 / Usage:
  skill-catalog list                    スキル一覧を表示（キャッシュ） / List skills (cached)
  skill-catalog info <name>             スキルの詳細を表示 / Show skill details
  skill-catalog import <name>           スキルをインポート / Import a skill
  skill-catalog share <name>            カタログに登録・更新 / Publish or update in the catalog
  skill-catalog unshare <name>          カタログから取り下げ / Remove from the catalog
  skill-catalog change-owner <name>     オーナーを変更 / Transfer ownership

例 / Examples:
  skill-catalog list
  skill-catalog info downloads
  skill-catalog import user.name/downloads
  skill-catalog share my-automation
```

表示後、「どのサブコマンドを使いますか？」と聞いてください。
After displaying, ask: "どのサブコマンドを使いますか？ / Which subcommand would you like to use?"

---

## skill-catalog list

ローカルのキャッシュ（`python/skills/skill-catalog/catalog-index.md`）からスキル一覧を表示します。キャッシュがない場合は初回のみ Drive をスキャンして作成します。
Displays the skill list from the local cache. On the first run (no cache), it scans Drive to build the index.

```bash
python3 python/scripts/setup/skills_catalog.py list
```

他の人が新しくスキルを登録した場合など、最新の情報を取得したいときは `skill-catalog update-index` を実行してください。
To fetch the latest list when others have added skills, run `skill-catalog update-index`.

---

## skill-catalog update-index

Drive をフルスキャンしてローカルのインデックスを最新化します。
Scans Drive and refreshes the local catalog index.

```bash
python3 python/scripts/setup/skills_catalog.py update-index
```

---

## skill-catalog info <name>

`<name>` は `skill-name` または `owner/skill-name` 形式を受け付けます。
Accepts both `skill-name` and `owner/skill-name` formats.

```bash
python3 python/scripts/setup/skills_catalog.py info <name>
```

終了コード `2` の場合、同名スキルが複数あります。出力の候補一覧をユーザーに見せ、`owner/name` 形式で選んでもらい再実行してください。
If exit code is `2`, multiple skills match — show the candidates and ask the user to re-specify using `owner/name` form.

---

## skill-catalog import <name>

`<name>` は `skill-name` または `owner/skill-name` 形式を受け付けます。
複数マッチ時は `skill-catalog info` と同様に選択を促してください。

同名のスキルがローカルに既に存在する場合は、上書き確認を取ってから進めてください。
If a skill with the same name already exists locally, ask for confirmation before overwriting.

```bash
python3 python/scripts/setup/skills_catalog.py download <name>
python3 python/scripts/setup/setup.py skills rebuild
```

リビルド完了後、ユーザーに `/skills reload` を実行するよう案内してください。
After rebuild, prompt the user to run `/skills reload` in Gemini CLI.

---

## skill-catalog share <name>

ローカルスキルをスキルカタログに登録（または更新）します。
`<name>` が省略された場合は一覧から選ばせます。
Registers (or updates) a local skill in the Skill Catalog.

**キャンセル / Cancel:** Drive アップロード未完了なら復元不要。frontmatter を更新済みの場合は元の内容に戻す。
If cancelled before the Drive upload completes, no restore is needed. If frontmatter was already updated, revert it.

```bash
python3 python/scripts/setup/skills_catalog.py upload <name>
```

初回は OAuth ブラウザ認証が必要です。ブラウザが開いたら会社の Google アカウントでログインしてください。
On first run, OAuth browser authentication is required.

完了後、アップロード先（`owner/skill-name`）をユーザーに伝えてください。
After completion, report the upload destination (`owner/skill-name`) to the user.

---

## skill-catalog unshare <name>

ライブラリからスキルを削除します。**ローカルのスキルは削除されません。**
自分がオーナーのスキルのみ実行できます。`<name>` が省略された場合は一覧から選ばせます。
Removes the skill from the catalog only. The local skill is NOT deleted.
Only the current owner can unshare.

確認を取ってから実行します：
Ask for confirmation before running:

```
「<name>」をライブラリから削除します。ローカルのスキルは残ります。よろしいですか？（はい / いいえ）
Remove "<name>" from the catalog. The local skill will remain. Proceed? (Yes / No)
```

```bash
python3 python/scripts/setup/skills_catalog.py delete <name>
```

---

## skill-catalog change-owner <name>

自分がオーナーのスキルのオーナーを別の社員に移します。
`<name>` が省略された場合は一覧から選ばせます。
Transfers ownership of a skill you own to another employee.

### Step 1 — 新オーナーのメールアドレスを確認

変更先のメールアドレスをユーザーに確認します。会社のメールアドレスであることを確認してください。
Ask for the new owner's email address.

### Step 2 — 実行

```bash
python3 python/scripts/setup/skills_catalog.py change-owner <name> <new_email>
```

成功すると Drive 上で `old_owner/<name>.md` → `new_owner/<name>.md` に移動します。
On success, the file moves from `old_owner/<name>.md` to `new_owner/<name>.md` on Drive.

---

## エラー対応 / Error Handling

| 終了コード | 意味 | 対応 |
|---|---|---|
| `0` | 成功 | 結果をユーザーに伝える |
| `1` | エラー | 出力メッセージをそのままユーザーに伝える |
| `2` | 複数マッチ | 候補一覧を表示し `owner/name` 形式で再指定を促す |
