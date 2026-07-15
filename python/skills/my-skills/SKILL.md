---
name: my-skills
description: ローカルスキルの一覧・作成・更新・テスト・無効化・有効化・削除・リビルド。"my-skills list", "スキル一覧", "何ができる？", "スキルを作って", "スキルを作りたい", "自分用のスキルを作って", "新しいスキルを追加したい", "スキルを更新", "スキルを無効化", "スキルを有効化", "スキルをリビルド", "my-skills enable/disable/delete/rebuild" などで起動。Guide for creating a new personal skill also lives here (my-skills create). カタログへの共有・取り下げ・オーナー変更は `skill-catalog` スキルを使用してください。For sharing/unsharing a skill to the catalog or transferring ownership, use the `skill-catalog` skill instead.
---

# マイスキル管理 / My Skills

## 言語設定 / Language Policy
ユーザーへの全ての返答は日英バイリンガルで表示してください。日本語を先に表示し、改行の後に英語を続けてください。
Always respond to the user in both Japanese and English. Display Japanese first, then English on the next line.

## 概要 / Overview

ローカルスキルの作成・編集・削除を担います。カタログへの公開・取り下げ・オーナー変更は `skill-catalog` スキルの範囲です。
Manages creation, editing, and deletion of local skills. Publishing/unpublishing to the catalog and ownership transfer are handled by the `skill-catalog` skill.

| サブコマンド | 説明 |
|---|---|
| `my-skills list` | ローカルのスキル一覧を表示 |
| `my-skills create <name>` | 新しいスキルを対話的に作成 |
| `my-skills update <name>` | 既存スキルを AI 対話で更新 |
| `my-skills test <name>` | スキルの動作を dry-run で検証 |
| `my-skills disable <name>` | スキルを一時無効化（`enable` で復元可能） |
| `my-skills enable <name>` | 無効化したスキルを再有効化 |
| `my-skills delete <name>` | スキルを完全削除（復元不可、カタログ分も選択可） |
| `my-skills rebuild` | 全スキルをリビルド・再インストール |

カタログへの登録・取り下げ・オーナー変更は `skill-catalog share` / `skill-catalog unshare` / `skill-catalog change-owner` を参照してください。
For catalog publish/unpublish/ownership transfer, see `skill-catalog share` / `skill-catalog unshare` / `skill-catalog change-owner`.

新規スキルの保存先: `python/skills-personal/<name>/SKILL.md`（自分専用・git管理外）
New skills are saved to: `python/skills-personal/<name>/SKILL.md` (personal, not tracked by git)

**OS別コマンド / OS-specific commands:** 以下のコマンドはすべて Mac/Linux 表記です。Windows では `python3` → `python`、パス区切りの `/` → `\` に読み替えて実行してください。
All commands below are written for Mac/Linux. On Windows, replace `python3` with `python` and forward slashes (`/`) with backslashes (`\`).

---

## 引数なし（ヘルプ表示）/ No Arguments — Show Help

ユーザーが `/my-skills` または「my-skills」とだけ入力してサブコマンドを指定しなかった場合、冒頭のサブコマンド表の内容をそのままヘルプとして表示し、「どのサブコマンドを使いますか？」と聞いてください。
If the user types `/my-skills` or "my-skills" without specifying a subcommand, display the subcommand table from the top of this file as-is, then ask: "どのサブコマンドを使いますか？ / Which subcommand would you like to use?"

---

## 共通ルール / Common Rules

**スキルの検索順序**（update / test / disable / delete で `<name>` を探す際）：以下の2ルートを順に検索し、各ルート内では有効状態→`disabled/`の順に探します。
1. `python/skills/`（同梱）
2. `python/skills-personal/`（自分専用）

**Search order for `<name>`** (used by update / test / disable / delete): search the two roots in this order, checking each root's top level before its `disabled/` subfolder.
1. `python/skills/` (bundled)
2. `python/skills-personal/` (personal)

**リビルドを伴うサブコマンド完了後**（disable / enable / create / update / delete / rebuild）：ユーザーに `/skills reload`（Gemini CLI）の実行を案内してください。list / test は対象外です。
**After any subcommand that rebuilds skills** (disable / enable / create / update / delete / rebuild): prompt the user to run `/skills reload` in Gemini CLI. Not needed for list / test.

## キャンセル・ロールバック / Cancel & Rollback

操作中にユーザーが「キャンセル」「中止」「やっぱりやめる」などと言った場合：
If the user says "cancel", "stop", "中止", or similar during an operation:

- **create** — ファイルを書き込む前に確認を取るため、確認前ならファイル削除不要。書き込み済みの場合は作成したディレクトリごと削除する。
- **update** — 書き込み前にバックアップを作成する。中断時はバックアップから復元し、バックアップを削除する。
- **disable** — 実行前に確認を取るため、確認前なら何もしない。
- **enable** — 実行前に確認を取るため、確認前なら何もしない。
- **delete** — 削除前に確認を取るため、確認前なら何もしない。

---

## my-skills list

ローカルにインストールされているスキルを3つのカテゴリに分けて一覧表示します。
Lists all locally installed skills grouped into three categories.

| カテゴリ | 内容 |
|---|---|
| `Common` | 全員共通の組み込みスキル |
| `My skill` | 自分が作成・オーナーのスキル |
| `<owner>` | カタログからインポートした他オーナーのスキル |

```bash
python3 python/scripts/setup/skills_catalog.py list-local
```

---

## my-skills disable <name>

スキルを一時無効化します（そのスキルが属するルート配下の `disabled/` に退避）。`my-skills enable` でいつでも復元できます。
`<name>` が省略された場合は有効スキル一覧から選ばせます。
Temporarily disables a skill by moving it to the `disabled/` subfolder under whichever root it lives in. Can be restored at any time with `my-skills enable`.

確認を取ってから実行します：
Ask for confirmation before running:

```
「<name>」を無効化します。あとで「my-skills enable <name>」で再有効化できます。よろしいですか？（はい / いいえ）
Disable "<name>"? You can re-enable it later with "my-skills enable <name>". Proceed? (Yes / No)
```

```bash
python3 python/scripts/setup/setup.py skills disable <name>
```

---

## my-skills enable <name>

無効化されたスキルを再有効化します（`disabled/` からそのルートの直下に戻します）。
`<name>` が省略された場合は無効スキルの一覧を表示して選ばせます。
Re-enables a disabled skill by moving it from `disabled/` back to the top level of its root.

`<name>` が省略された場合は以下で無効スキル一覧を確認します：
If `<name>` is omitted, list disabled skills first:

```bash
python3 python/scripts/setup/setup.py skills list
```

出力の「Disabled skills」欄から選んでもらい、以下を実行します：
Ask the user to choose from the "Disabled skills" section, then run:

```bash
python3 python/scripts/setup/setup.py skills enable <name>
```

---

## my-skills create <name>

新しい SKILL.md を対話的に作成します。`<name>` が省略された場合はヒアリング中に確認します。
Creates a new SKILL.md through conversation. If `<name>` is omitted, ask during the interview.

### Step 1 — やりたいことを聞く

技術的な質問は避け、まず以下のように話しかけます。一度に聞くのはこの1問だけ：
Avoid technical questions. Start with just this one open-ended question:

```
どんなことを自動化・お願いしたいですか？
「毎朝スケジュールをまとめてほしい」「ファイルを整理してほしい」のように、
気軽に教えてください。
```

ユーザーの回答をもとに、以下を AI が整理・提案します（ユーザーへの質問は最小限に）：
Based on the reply, the AI proposes the following without burdening the user with technical questions:

- **スキル名** — 英小文字・ハイフン区切り（例: `daily-summary`）。`python/skills/`・`python/skills-personal/` のいずれにも同名フォルダがないか確認する（ビルド時にマージされるため、どのルートでも重複は不可）。
- **説明・起動キーワード** — どんな言葉で動くか（例: 「スケジュールまとめて」「daily summary」）
- **手順** — 実行する流れ
- **使用例** — 具体的な発話と対応する動作

不明点があれば追加で質問してよいが、一度に 1〜2 問まで。質問攻めにしない。
Ask follow-up questions only if needed — limit to 1–2 at a time. Never interrogate.

### Step 2 — SKILL.md の生成

収集した情報をもとに以下のフォーマットで SKILL.md を生成します：

```markdown
---
name: <skill-name>
description: <日英両方の説明とトリガーキーワード>
---

# <スキルタイトル / Skill Title>

## 言語設定 / Language Policy
ユーザーへの全ての返答は日英バイリンガルで表示してください。日本語を先に表示し、改行の後に英語を続けてください。
Always respond to the user in both Japanese and English. Display Japanese first, then English on the next line.

## 概要 / Overview
<スキルの目的と概要>

## 手順 / Workflow
<ステップバイステップの手順>

## テスト / Test
<dry-runコマンド。テストが不要なスキルはこのセクションを省略する>

## 使用例 / Examples
<具体的な使用例>
```

### Step 3 — プレビューと確認

生成した SKILL.md をユーザーに見せて確認を取ります。
Show the generated SKILL.md and ask for confirmation.

修正があれば反映して再確認します。確認が取れた場合のみ Step 4 に進みます。
If changes are needed, revise and confirm again. Only proceed to Step 4 upon explicit confirmation.

### Step 4 — ファイルの書き込み

Write ツールを使って `python/skills-personal/<name>/SKILL.md` に保存します。
Use the Write tool to save to `python/skills-personal/<name>/SKILL.md`.

### Step 5 — リビルド

```bash
python3 python/scripts/setup/setup.py skills rebuild
```

---

## my-skills update <name>

既存スキルを AI 対話で更新します。`<name>` が省略された場合は一覧から選ばせます。
Updates an existing skill through AI conversation. If `<name>` is omitted, show a list and ask the user to choose.

### Step 1 — 現在の内容を表示

共通ルールの検索順序に従って `<name>/SKILL.md` を探して読み込み、ユーザーに見せます。以降のステップでは見つかったパスを `<found-path>` とします。
Following the Common Rules search order, find and read `<name>/SKILL.md` and show it to the user. Subsequent steps refer to the located path as `<found-path>`.

### Step 2 — 変更内容のヒアリング

「どこを変えたいですか？」と聞き、変更内容を確認します。
Ask "What would you like to change?" and gather requirements.

### Step 3 — 新しい内容の生成とプレビュー

変更後の SKILL.md を生成し、変更点のサマリーとともにユーザーに見せます。
Generate the updated SKILL.md and show a summary of changes.

確認が取れた場合のみ Step 4 に進みます。/ Only proceed to Step 4 upon confirmation.

### Step 4 — バックアップ→上書き

```bash
cp <found-path>/SKILL.md <found-path>/SKILL.md.bak
```

Write ツールで `<found-path>/SKILL.md` を上書き保存します。
Use the Write tool to overwrite.

キャンセルされた場合はバックアップから復元して削除します：
If cancelled, restore and delete the backup:
```bash
cp <found-path>/SKILL.md.bak <found-path>/SKILL.md
rm <found-path>/SKILL.md.bak
```

### Step 5 — リビルド

```bash
python3 python/scripts/setup/setup.py skills rebuild
```

完了後、バックアップファイルを削除してください。
After completion, delete the backup file.

---

## my-skills test <name>

スキルの SKILL.md に定義された `## テスト / Test` セクションのコマンドを実行して動作を検証します。
`<name>` が省略された場合は一覧から選ばせます。
Runs the commands in the `## テスト / Test` section of the skill's SKILL.md.
If `<name>` is omitted, show a list and ask the user to choose.

### Step 1 — テストセクションの読み込み

共通ルールの検索順序に従って `<name>/SKILL.md` を読み込み、`## テスト` または `## Test` セクションを探します。

- セクションが存在しない場合：「このスキルにはテストセクションが定義されていません。`my-skills update` でテストセクションを追加できます。」と伝える。
- セクションが存在する場合：Step 2 に進む。

### Step 2 — テストコマンドの実行

テストセクション内の bash コードブロックのコマンドを順番に実行します。
各コマンドは独立して実行し（前のコマンドの完了を待ってから次へ）、出力を記録します。

### Step 3 — 結果の報告

```
テスト結果 / Test Results — <name>
─────────────────────────────────────
✓ <コマンド1> — 成功 / Passed
✗ <コマンド2> — 失敗: <エラー内容> / Failed: <error>
```

`✗` があった場合はエラー出力をそのまま表示し、原因と対処法を案内します。

---

## my-skills delete <name>

スキルを**完全削除**します（復元不可）。一時的に使わないだけなら `my-skills disable` を使ってください。
`<name>` が省略された場合は一覧から選ばせます。
**Permanently deletes** the skill (cannot be undone). Use `my-skills disable` instead if you just want to hide it temporarily.

### Step 1 — スキルの場所とオーナーを確認

共通ルールの検索順序に従ってスキルファイルを探し、場所（`<found-path>`）と frontmatter の `email` を確認します。
Following the Common Rules search order, locate the skill file (`<found-path>`) and read the `email` field from its frontmatter.

スキルが見つからない場合はエラーを伝えます。
If not found, report an error.

次に現在のユーザーを取得します：
Then get the current user's email:
```bash
python3 python/scripts/setup/skills_catalog.py whoami
```

**判定結果と対応 / Decision logic:**

| 状態 | 対応 |
|---|---|
| `email` なし（デフォルトスキル）| ローカルのみ削除。Step 2A へ。 |
| `email` あり＋現在ユーザーと一致 | ローカルのみか、カタログも含めて削除か選ばせる。Step 2B へ。 |
| `email` あり＋別のオーナー | ローカルのみ削除。「カタログ上の `<owner>/<name>` は削除できません」と案内。Step 2A へ。 |

### Step 2A — ローカルのみ完全削除

**この操作は取り消せません。** 確認を取ってから実行します：
**This cannot be undone.** Ask for confirmation:

```
「<name>」を完全に削除します。この操作は取り消せません。よろしいですか？（はい / いいえ）
Permanently delete "<name>". This cannot be undone. Proceed? (Yes / No)
```

`<found-path>` のディレクトリを削除し、リビルドします：
Delete the `<found-path>` directory, then rebuild:

```bash
rm -rf <found-path>
python3 python/scripts/setup/setup.py skills rebuild
```

### Step 2B — 削除範囲の選択（オーナーのみ）

削除範囲を選ばせます：
Ask the user which scope to delete:

```
どちらを削除しますか？/ What would you like to delete?
  1. ローカルのみ / Local only
  2. ローカルとカタログの両方 / Both local and catalog
```

**1 を選んだ場合:** Step 2A と同じ手順。
**2 を選んだ場合:** 最終確認後、以下を順番に実行：

```bash
# カタログから削除
python3 python/scripts/setup/skills_catalog.py delete <name>
# ローカルから削除
rm -rf <found-path>
python3 python/scripts/setup/setup.py skills rebuild
```

---

## my-skills rebuild

SKILL.md を直接編集した後や、スキルが最新の状態になっていない場合に、全スキルをリビルドして再インストールします。
Rebuilds and reinstalls all skills. Use after directly editing SKILL.md files, or when installed skills seem out of date.

```bash
python3 python/scripts/setup/setup.py skills rebuild
```

---

## 使用例 / Examples

| ユーザーの発言 | 実行内容 |
|---|---|
| 「スキルの一覧を見せて」「何ができる？」 | `my-skills list` |
| 「スキルを作って」 | `my-skills create` — ヒアリング開始 |
| 「my-automationを更新して」 | `my-skills update my-automation` |
| 「my-automationのテストをして」 | `my-skills test my-automation` |
| 「my-automationを無効化して」「しばらく使わないので隠して」 | `my-skills disable my-automation` |
| 「my-automationを有効化して」「無効にしたスキルを戻して」 | `my-skills enable my-automation` |
| 「スキルを完全に削除して」 | `my-skills delete` — 完全削除（復元不可）・オーナー判定後に範囲を選択 |
| 「スキルをリビルドして」「スキルを最新にして」 | `my-skills rebuild` |
| 「このスキルをカタログに登録して」「カタログから取り下げたい」「オーナーを変更して」 | `skill-catalog` スキルを使用 / Use the `skill-catalog` skill |
