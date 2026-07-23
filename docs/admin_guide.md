# agent-deck 管理者ガイド / agent-deck Admin Guide

このドキュメントは、agent-deck の管理・開発・配布に携わる担当者向けの技術リファレンスです。
This document is a technical reference for administrators, developers, and anyone involved in managing, developing, or distributing agent-deck.

> Rewritten to describe the current architecture and kept in sync as it changes.

---

## 0. 全体アーキテクチャ / Overall Architecture

このディレクトリは**単一の作業ディレクトリ**で、二重の役割を持ちます：公開プロジェクト `kh813/agent-deck`（Tauri 製デスクトップアプリ）の Git 管理下の開発環境であり、同時に、組織固有の設定・秘匿情報・管理者向けドキュメントを保持するローカル環境でもあります。両者は同じファイルツリーに同居しますが、`.gitignore` によって完全に分離されています。

This directory serves a **dual role** in a single working tree: it's the Git-tracked development environment for the public `kh813/agent-deck` project (a Tauri desktop app), and at the same time the local home for an organization's own private config, secrets, and admin-facing documentation. Both live in the same file tree, kept fully separate via `.gitignore`.

| 区分 / Category | 公開範囲 / Visibility | 内容 / Contents |
|---|---|---|
| Git 管理下 / Git-tracked | 公開（GitHub） / Public | このリポジトリのソースコード一式。誰でも clone・fork でき、誰でも GitHub Releases から配布 ZIP を直接ダウンロードできる。**`docs/admin_guide.md`・`docs/user_guide.md` も、機密情報を含まない汎用的な技術リファレンス／利用ガイドとしてここに含まれる。** |
| `.gitignore` 対象 / Gitignored | 組織限定 / Org-private | `config.toml`・`client_secret_*.json` など、組織固有の値を含むファイル。個人の PC 上にのみ存在し、GitHub には一切アップロードされない。 |

**新規インストールの配布モデル / Distribution model for new installs:**

```
新規インストール（社員PC）/ New install (employee machine)
        ↓
1. kh813/agent-deck の GitHub Releases から ZIP を直接ダウンロード
   Download the ZIP directly from kh813/agent-deck's GitHub Releases
2. 組織向け config.toml を配置（このディレクトリの gitignore 対象ファイルが原本）
   Drop in an org-specific config.toml (this directory's gitignored copy is the source)
3. agent-deck.app / agent-deck.exe をダブルクリック
   Double-click agent-deck.app / agent-deck.exe
        ↓
preflight.sh/.bat が実行される
preflight.sh/.bat runs
        ↓
venv 構築 → skill-catalog sync（config.toml の catalog_folder_id から
組織固有スキルを Drive の _default/ フォルダから自動導入）→ スキルビルド
venv setup → skill-catalog sync (auto-pulls org-specific skills from Drive's
_default/ folder via config.toml's catalog_folder_id) → skills built
        ↓
以後の更新は self_update.py（GitHub Releases ベース）のみ
Ongoing updates are handled solely by self_update.py (GitHub Releases-based)
```

このモデルは、公開リポジトリのコードだけで完結します（実機で実証済み — 詳細は §7）。組織固有の作業（スキル著作、設定・秘匿情報の管理）は、以下の方法でこの単一ディレクトリの中に収まります：

This model is entirely self-contained using only the public repo's own code (verified end-to-end for real — see §7). Org-specific work (skill authoring, config/secret management) fits inside this same single directory via:

1. **組織固有スキルの著作** / **Org-specific skill authoring** — `python/skills-personal/<name>/` で直接著作し、`skill-catalog publish` で Drive の `_default/` に公開する（§2）。専用の別リポジトリは不要。
2. **設定・秘匿情報のバックアップ** / **Config/secret backup** — `config.toml`・`client_secret_*.json`・`docs/` は git 管理外だが、定期的に ZIP 化して組織の Google Drive にアップロードすることでバックアップする（§7c）。

---

## 1. ディレクトリ構成 / Directory Structure

Git 管理下のファイルと、`.gitignore` 対象の組織固有ファイルが同じツリーに同居します。

Git-tracked files and `.gitignore`d org-specific files share the same tree.

```
agent-deck/
├── ANTIGRAVITY.md               # agy 用プロジェクト指示
├── CLAUDE.md                    # Claude Code 向け開発ルール（release へのタグ付けは要許可、等）
├── README.md
├── config/
│   └── config.toml.template     # 設定テンプレート（実値は含まない、git 管理）
├── config.toml                  # ★実際の設定（git 除外）— 組織固有の値の原本
│                                 # The actual config (git-excluded) — source of org-specific values
├── client_secret_*.json         # OAuth クライアントシークレット（git 除外）
├── docs/
│   ├── admin_guide.md            # 本ドキュメント。機密情報を含まないため git 管理下（公開）
│   └── user_guide.md             # 利用者向けドキュメント。同じく git 管理下（公開）
│
├── agent-deck.app / agent-deck.exe   # ダブルクリックで起動。プロジェクトルート直下（自己更新で置き換わる）
├── preflight.sh / preflight.bat      # 起動前フック（pre_launch_command 経由で毎回実行）
├── agent_config.json                 # Tauri 設定（pre_launch_macos/windows 等）
├── messages/                         # preflight.bat が `type` で読む日英メッセージ（§10 参照）
│
├── python/
│   ├── scripts/setup/
│   │   ├── setup.py               # 統合エントリポイント（init/config/skills/trust）
│   │   ├── self_update.py         # 自己更新（GitHub Releases ベース）
│   │   └── skills_catalog.py      # スキルカタログ（Drive）管理
│   ├── scripts/automation/        # 共通ユーティリティ（chrome_utils.py 等）
│   ├── scripts/tools/             # upload_release.py・drive_upload.py 等の管理者用ユーティリティ
│   ├── skills/                    # 公開スキルのソース
│   └── skills-personal/           # ★組織固有スキル + カタログ同期スキルの著作場所（git 管理外、§2）
│
├── venv/                        # Python 仮想環境（自動生成）
├── .gemini/skills/               # インストール済みスキル（agy が読み込む）
└── src-tauri/                    # Tauri（Rust）ソース
```

★印は組織固有・git 除外のファイルです。他は公開リポジトリの一部として GitHub 管理下にあります。

★-marked entries are org-specific and git-excluded. Everything else is part of the public repo, tracked on GitHub.

---

## 2. スキルの仕組み / Skill System

Antigravity CLI (`agy`) は `.gemini/skills/<name>/SKILL.md` からスキルを読み込みます。各スキルは、特定のコマンドをエージェントがどう処理するかを記述した Markdown ファイルで、`/skill-name` のスラッシュコマンドで呼び出せます。

Antigravity CLI (`agy`) loads skills from `.gemini/skills/<name>/SKILL.md`. Each skill is a Markdown file instructing the agent how to handle a specific command, invocable via `/skill-name`.

### ビルドとインストールの流れ / Build & Install Flow

```
python/skills/**/<name>/SKILL.md          (公開 / public, 公開リポジトリ自身が同梱)
python/skills-personal/**/<name>/SKILL.md (個人 + カタログ同期分 / personal + catalog-synced)
        ↓  build-skills.sh (setup.py 経由)   — 両ルートをマージ
skills/<name>.skill   (ZIPアーカイブ / ZIP archive)
        ↓  setup.py install_skills()
.gemini/skills/<name>/SKILL.md   ← agy はここから読み込む / agy reads from here
```

`python/skills-personal/` には2種類のものが混在します：ユーザーが `my-skills create` で作った個人スキルと、**skill-catalog の `_default/` フォルダから自動同期された会社スキル**（`skills_catalog.py sync` が書き込む、`.catalog-sync-manifest` で管理）。

`python/skills-personal/` holds two kinds of content: skills a user created via `my-skills create`, and **company skills auto-synced from the skill-catalog's `_default/` folder** (written by `skills_catalog.py sync`, tracked via `.catalog-sync-manifest`).

### 組織固有スキルの著作フロー / Org-Specific Skill Authoring Flow

```
python/skills-personal/<name>/SKILL.md（+ scripts/ 同梱、自己完結）で直接著作
Author directly in python/skills-personal/<name>/SKILL.md (+ bundled scripts/, self-contained)
        ↓  このディレクトリの agent-deck.app/.exe で動作確認
           Test locally against this directory's own agent-deck.app/.exe
        ↓  問題なければ Drive カタログへ公開 / once verified, publish to the Drive catalog
python3 python/scripts/setup/skills_catalog.py publish <skill_name>
        ↓
Drive の <owner>/_default/ フォルダに配置される
        ↓  全社員が起動のたびに自動同期（skills_catalog.py sync）
Auto-synced to every employee's install on every launch
```

組織固有スキルは、依存スクリプト（共通ユーティリティ等）を**スキルディレクトリ自身に同梱**する自己完結型で著作してください。`python/scripts/automation/common.py`・`automate.py` は、新しいスキルを著作する際の参考実装として使えますが、公開後のスキル自体は実行時にこれらをインポートしない（自分のディレクトリ内のコピーを使う）のが望ましい設計です。

Author org-specific skills as self-contained, bundling their dependency scripts (shared utilities, etc.) **inside the skill directory itself**. `python/scripts/automation/common.py`/`automate.py` are useful as reference implementations when authoring a new skill, but a published skill ideally doesn't import them at runtime (it uses its own bundled copy instead).

### スキル名の競合に注意 / Watch for Skill Name Conflicts

`.gemini/skills/` 以下に同じ `name` を持つ SKILL.md が複数存在すると、agy が起動時に競合警告を出します。`setup.py skills rebuild` は、プロジェクトの `.gemini/skills/` にインストールした後、`~/.gemini/skills/` にある同名スキルを自動削除するため、ホームレベルとプロジェクトレベルの二重インストールによる競合は解消されます。

If multiple SKILL.md files under `.gemini/skills/` share the same `name`, agy warns of a conflict on startup. `setup.py skills rebuild` automatically removes any matching skill from `~/.gemini/skills/` after installing to the project's `.gemini/skills/`, eliminating home-vs-project duplicate conflicts.

名前衝突ポリシー / Name-conflict policy: `python/skills/`（公開・同梱）が `python/skills-personal/`（カタログ同期分含む）より優先されます。会社スキルは同梱スキルと同名を付けない運用としています。
Public, bundled skills (`python/skills/`) win over `python/skills-personal/` (including catalog-synced ones). Operationally, company skills avoid reusing a bundled skill's name.

---

## 3. setup.py サブコマンドリファレンス / setup.py Subcommand Reference

**`python/scripts/setup/setup.py`**（公開リポジトリ側、以下すべてこれを指す）がメンテナンス操作の統合エントリポイントです。

**`python/scripts/setup/setup.py`** (in the public repo — every reference below is to this file) is the unified entry point for maintenance operations.

```bash
python3 python/scripts/setup/setup.py [init|config [clear-email]|trust|skills [list|rebuild|enable <name>|disable <name>]]
# Windows では python3 を python に読み替え / On Windows, replace python3 with python
```

### 起動時のフロー（preflight.sh/.bat 経由）/ Launch Flow (via preflight.sh/.bat)

```
agent-deck.app / agent-deck.exe をダブルクリック / Double-click
        ↓  Tauri の pre_launch_command として実行 / Run as Tauri's pre_launch_command
preflight.sh / preflight.bat
        ↓
1. python3 setup.py config          — メール・OAuth 設定確認（非対話。未設定なら次回に持ち越し）
                                       Config check (non-interactive; unset fields are just deferred)
2. venv/ が無ければ python3 setup.py init   — 初回のみ。venv 作成・スキルビルド・ポリシー導入
                                       First run only: venv, skill build, policy install
3. python3 setup.py skills rebuild   — 常に実行。カタログ同期 → ビルド → 再インストール
                                       Always runs: catalog sync → build → reinstall
4. 認証チェック（sentinel ファイル）  / Auth check (sentinel file)
        ↓
agy を起動 / Launch agy
```

**`init`** は以下を順に実行します（`setup_config()` → `setup_venv()` → `build_skills()` → `install_skills()` → `install_gemini_policies()` → `trust_project_folder()` → `setup_files_folder()`）。venv の有無で初回セットアップ済みかを判定するため、`venv/` は配布 ZIP に含まれません。

**`init`** runs, in order: `setup_config()` → `setup_venv()` → `build_skills()` → `install_skills()` → `install_gemini_policies()` → `trust_project_folder()` → `setup_files_folder()`. The presence of `venv/` is how the launcher decides whether first-run setup is already done, so it's excluded from the distribution ZIP.

#### agy (Antigravity CLI) のインストール先 / Where agy actually installs

初回起動時、`agy` がまだ検出されない場合はオンボーディング画面から手動インストール（ボタンクリック1つ）できます（自動・無操作でのインストールではありません）。実際のインストール先は **プロジェクトフォルダの外、ユーザーのホームディレクトリ配下** です — Mac: `~/.local/bin/agy`、Windows: `%LOCALAPPDATA%\agy\bin\agy.exe`（いずれも管理者権限は不要）。

On first launch, if `agy` isn't detected yet, it can be installed manually via a single button click on the onboarding screen (not a zero-click automatic install). It actually installs **outside the project folder, under the user's home directory** — macOS: `~/.local/bin/agy`; Windows: `%LOCALAPPDATA%\agy\bin\agy.exe` (neither requires admin/elevation).

**この場所を勝手に変えないこと。** `src-tauri/resources/install_commands.json` はこれら2つの実際のデフォルト設置場所を `detect_paths` に含めておく必要があります。過去に一度（2026-07-21）、`app/bin/` に誘導しようと `$BINDIR`（Mac）/ `$env:BINDIR`（Windows）環境変数を install コマンドに渡していましたが、Antigravity 公式インストーラー（`install.sh`/`install.ps1`）はどちらもこの環境変数を完全に無視し、`--dir`/`-d` フラグのみを読む仕様だったため、実際にはこの誘導は無効でした。結果として agy は上記のホームディレクトリにインストールされていたにもかかわらず、`detect_paths` にその場所が無かった（かつ GUI 起動アプリの `PATH` にも `~/.local/bin` が含まれない）ため、agent-deck 側は「未インストール」と誤検知し続けるというバグになっていました（`python/tests/test_install_commands.py::TestDetectPathsMatchWhereTheInstallerActuallyPutsIt` で再発防止テスト済み）。

**Do not silently move this location.** `src-tauri/resources/install_commands.json`'s `detect_paths` must keep listing both installers' real default locations. Once (2026-07-21), the install commands set a `$BINDIR`/`$env:BINDIR` env var trying to redirect installs into `app/bin/` — but the official Antigravity installers (`install.sh`/`install.ps1`) ignore that env var entirely (they only read a `--dir`/`-d` flag), so the redirect silently did nothing. agy kept landing at the home-directory default above, but since `detect_paths` didn't list it (and a GUI-launched app's inherited `PATH` doesn't include `~/.local/bin` either), agent-deck kept reporting it as not installed even after a successful install. Regression-guarded by `python/tests/test_install_commands.py::TestDetectPathsMatchWhereTheInstallerActuallyPutsIt`.

#### Windows の埋め込み Python (`app/python/` / `App\python\`) / Windows's embedded Python bootstrap

`agy` とは無関係の、**別の**組み込み Python です。Windows で `preflight.bat`（agent-deck 配布ラッパー側の起動前フック）が、システムに Python が全く無い場合に、自分自身が `install_agent_ui.py`/`sync_internal_skills.py`（純標準ライブラリのみのスクリプト）を実行するためだけに `app\python\python.exe` へ portable Python をダウンロードします。`python/scripts/setup/setup.bat`（本リポジトリ側）も、venv 構築用に**独立して**同名の場所（`App\python\`、大文字小文字はどちらでも Windows では同一パスを指す）をチェック・利用します。意図的に2つの別々の埋め込み Python 用意ロジックになっています（コメント参照: 一方を使い回すと、setup.bat の「システム Python かどうか」判定を誤らせるリスクがあるため）。

**既知の未解決事象（2026-07-22 報告）:** 初回セットアップを完了したはずのマシンで、2回目起動時に `app\python\python.exe` が見つからず、portable Python のダウンロードが再度走った事例が報告されています。両リポジトリのコードを調査した結果、`app/python` を削除・クリーンアップするコードはどこにも存在しません（`config/cleanup.txt`・`self_update.py`・`install_agent_ui.py`・`sync_internal_skills.py` を確認済み）。**PATH が通っていないことが原因ではありません** — このチェックは `if not exist "app\python\python.exe"` という相対パスの存在確認のみで、PATH は一切参照しません（意図的に PATH には追加しない設計 — setup.bat 側の「システム Python かどうか」の判定を混乱させないため。PATH を追加する対応は行わないこと）。最も可能性が高いのは**外部要因**（ウイルス対策ソフトが「展開直後にすぐ実行される未署名の exe」をリアルタイム保護で検疫・削除する、または会社の OneDrive 等クラウド同期フォルダがプレースホルダーとして退避する、など）です。再現した場合は、プロジェクトフォルダが OneDrive 等の同期対象になっていないか、`app\python\` 付近でウイルス対策ソフトの検疫ログが無いかを確認してください。

**This is unrelated to agy** — a separate embedded Python. On Windows, `preflight.bat` (the distribution wrapper's own pre-launch hook) downloads a portable Python to `app\python\python.exe` purely to run its own `install_agent_ui.py`/`sync_internal_skills.py` (pure-stdlib scripts) when no system Python exists at all. `python/scripts/setup/setup.bat` (this repo) **independently** checks/reuses the same location (`App\python\` — same path on Windows regardless of case) for building its own venv. This is deliberately two separate embedded-Python bootstraps (see code comments: sharing one risks confusing setup.bat's own system-vs-embedded Python detection).

**Known open issue (reported 2026-07-22):** on a machine that had already completed first-time setup once, the portable Python download ran again on a second launch — `app\python\python.exe` was apparently missing. A thorough code search across both repos found nothing that deletes or cleans up `app/python` (checked `config/cleanup.txt`, `self_update.py`, `install_agent_ui.py`, `sync_internal_skills.py`). **This is not a PATH problem** — the check is a plain relative-path existence check (`if not exist "app\python\python.exe"`), never PATH; it's deliberately kept off PATH (adding it would risk confusing setup.bat's own system-vs-embedded Python detection — do not add it to PATH). The most likely explanation is **external interference** — antivirus real-time protection quarantining a freshly-extracted, unsigned executable that's run immediately, or a cloud-sync folder (OneDrive etc.) evicting it as a placeholder. If this recurs, check whether the project folder is inside a synced cloud folder, and check for antivirus quarantine logs around `app\python\`.

### setup skills — スキル管理 / Skill Management

```bash
python3 python/scripts/setup/setup.py skills list
python3 python/scripts/setup/setup.py skills rebuild
python3 python/scripts/setup/setup.py skills enable  <skill_name>
python3 python/scripts/setup/setup.py skills disable <skill_name>
```

| サブコマンド / Subcommand | 動作 / Action |
|---|---|
| `skills list` | 有効（✓）・無効（✗）スキルを一覧表示 / List enabled/disabled skills |
| `skills rebuild` | `sync_catalog_skills()`（skill-catalog `_default/` を同期）→ `build_skills()` → `install_skills()` |
| `skills enable <name>` | `disabled/` から戻してリビルド / Move out of `disabled/` and rebuild |
| `skills disable <name>` | `disabled/` へ移動してリビルド / Move into `disabled/` and rebuild |

`sync_catalog_skills()` は `skills_catalog.py sync` を subprocess で呼びます。`config.toml` に `catalog_folder_id` が未設定・プレースホルダのままなら即 no-op で、OSS 利用者には一切影響しません。オフライン・認証拒否・タイムアウトいずれの場合も warn を出すだけで rebuild 自体は継続し、起動をブロックしません。

`sync_catalog_skills()` shells out to `skills_catalog.py sync`. It's an instant no-op if `config.toml`'s `catalog_folder_id` is unset/a placeholder — zero impact on OSS users. Offline, declined auth, or a timeout all just print a warning; the rebuild continues and never blocks launch.

### setup config — 設定確認・リセット / Configuration Check & Reset

```bash
# メール・OAuth クレデンシャルが未設定の場合に入力を求める（起動のたびに実行）
python3 python/scripts/setup/setup.py config

# メールアドレスをリセットして再入力を促す
python3 python/scripts/setup/setup.py config clear-email
```

`preflight.sh`/`.bat` は agy からstdinなしで呼ばれるため、`setup_config()` の `input()` 呼び出しは EOF を空文字列として扱う `_prompt()` ヘルパー経由です（未設定のまま次回に持ち越されるだけで、クラッシュしません）。

`preflight.sh`/`.bat` invoke this with no stdin attached, so `setup_config()`'s `input()` calls go through a `_prompt()` helper that treats EOF as an empty answer — the field just stays unset until the next run, no crash.

### スキルカタログ管理 / Skill Catalog Management

```bash
python3 python/scripts/setup/skills_catalog.py <command>
```

| コマンド / Command | 動作 / Action |
|---|---|
| `sync` | `_default/` フォルダを起動のたびに同期（manifest 方式、stale 削除あり）/ Auto-sync `_default/` on every launch |
| `publish <name>` | スキルを `_default/` に配置し、全端末へ自動配布対象にする / Publish a skill to `_default/` — auto-distributed to everyone |
| `list` / `list-local` | カタログ全体 / ローカル導入済みスキルの一覧 |
| `info <name>` / `download <name>` / `upload <name>` / `delete <name>` / `change-owner <name> <email>` | 個人カタログ（`_default/` 以外）向けの手動操作 |
| `whoami` | 現在の認証ユーザーを確認 |
| `update-index`（管理者用） | Drive をフルスキャンしてキャッシュを再作成 |

`_default/` のみが自動同期対象です。個人が公開した他のスキルは、従来どおり手動 `download` が必要です。Drive の `_default/` フォルダ自体の書き込み権限を管理者のみに制限することで、「誰が全社自動配布に載せられるか」を Drive の権限管理に委ねています。

Only `_default/` is auto-synced. Other individually-shared skills still require manual `download`. Restricting write access to the Drive `_default/` folder to admins is how "who can push to everyone automatically" is governed.

認証トークン / Auth token: `~/.gemini/agent_ui_library_token.json`（初回のみブラウザ認証）。

### アンインストール / Uninstall

Node.js・Python 環境はプロジェクトフォルダ内に収まっているため、agent-deck 本体は**プロジェクトフォルダを削除するだけでアンインストールできます**。ただし `agy` 自体は前節のとおりホームディレクトリ配下（`~/.local/bin/agy` / `%LOCALAPPDATA%\agy\bin\agy.exe`）にインストールされるため、これはプロジェクトフォルダの削除では消えません。

Node.js and Python are self-contained inside the project folder, so agent-deck itself can be uninstalled by **just deleting the project folder**. `agy` itself, however, installs under the user's home directory (`~/.local/bin/agy` / `%LOCALAPPDATA%\agy\bin\agy.exe`, per the previous section) and is NOT removed by deleting the project folder.

1. agy / agent-deck を終了する
2. プロジェクトフォルダを削除する
3. ポリシーファイルを削除する（`~/.gemini/policies/agent-deck.toml` — 旧バージョン由来の別名ファイルが残っていないかも確認）
4. （任意）`agy` 自体も削除する場合は `~/.local/bin/agy`（Mac）または `%LOCALAPPDATA%\agy\bin\agy.exe`（Windows）を削除する — 他の agent-deck インストールと共有される可能性があるため、通常はそのままで問題ありません

> `files/` フォルダはプロジェクト内にあるため、削除前に必要なデータをバックアップしてください。

---

## 4. 自己更新の流れ / Self-Update Flow

メニューバーの「**Settings**」→「**Check for agent-deck Updates...**」から、`kh813/agent-deck` の **GitHub Releases** を確認し、現在より新しいタグがあればダウンロード・置換します（Rust側の `check_self_update`/`get_self_update_command` コマンドが、公開リポジトリの `python/scripts/setup/self_update.py` を呼び出します）。**Google Drive は一切関与しません。**

チャットスキルとして提供されていた `/update` は廃止され、メニューからの操作に置き換わりました（スキル自体は既に自動で毎回同期される仕組みだったため、実質的に必要だったのはagent-deck本体の更新トリガーだけでした — §2参照）。

Selecting **Settings** → **Check for agent-deck Updates...** in the menu bar checks `kh813/agent-deck`'s **GitHub Releases** and downloads/replaces if a newer tag exists (the Rust-side `check_self_update`/`get_self_update_command` commands invoke the public repo's `python/scripts/setup/self_update.py`). **Google Drive is not involved at all.**

The `/update` chat skill has been retired in favor of this menu action (skills themselves were already auto-synced on every launch regardless — see §2 — so the only thing actually gated behind a skill was triggering agent-deck's own update).

```
Settings → Check for agent-deck Updates...（メニュー）
        ↓
python3 python/scripts/setup/self_update.py check --json   — 更新の有無だけ確認（ダウンロードしない）
        ↓ 更新が見つかりバナーの Update Now がクリックされたら / if found and "Update Now" is clicked in the resulting banner
python3 python/scripts/setup/self_update.py apply
        ↓
1. GitHub Releases API で最新タグ・アセット URL を取得
   Fetch the latest tag + asset URL via the GitHub Releases API
2. アセット（agent-deck-mac.zip / agent-deck-win.zip）をダウンロードし一時ディレクトリに展開
   Download the asset and extract to a temp dir
3. Mac: xattr でquarantine除去、実行ビット付与、ad-hoc 再署名
   Mac: strip quarantine, chmod +x, ad-hoc re-sign
4. 既存バンドル/exe を新しいものと差し替え
   Swap the existing bundle/exe for the new one
   — Windows: 実行中の exe を直接 unlink するとロックで失敗するため、
     まず <name>.exe.old へリネームしてパスを空けてから新 exe を配置
     （2026-07-19 修正。旧 install_agent_ui.py にも同じ問題があり同日修正済み）
     Windows: unlinking the running exe directly fails (locked); rename
     it aside to <name>.exe.old first, then move the new exe into the
     now-free path (fixed 2026-07-19; install_agent_ui.py had the
     identical bug, fixed the same day)
5. python/ 一式を同じ zip から再展開（skills-personal/ は保持）
   Refresh python/ from the same zip (skills-personal/ preserved)
6. .sh ファイルを LF に正規化
   Normalize .sh files to LF
7. マーカーファイル（<root>/<name>.version）に新タグを記録
   Write the new tag to the marker file (<root>/<name>.version)
```

実行中のプロセス自体を書き換えるわけではないため、**適用後はウィンドウの再起動が必要**です。

This doesn't hot-swap the running process, so **a restart is required** to use the new version after applying an update.

**組織リブランド対応 / Organization rebrand support:** `self_update.py` はインストール済みバンドル/exe の実際の名前を検出して維持します（`agent-deck.*` 以外の名前、例えば `acme-console.app` でも動作）。リブランダー独自のマーカー（`app/<name>.version`）には一切書き込みません — 上書きすると、リブランダー側の固定ピンインストーラが「新しいタグが来た」と誤認して再インストール（ダウングレード）してしまうためです。

`self_update.py` detects and preserves whatever name the installed bundle/exe actually has (works even under a rebranded name like `acme-console.app`). It never writes to a rebrander's own marker (`app/<name>.version`) — doing so would make that rebrander's pinned installer think a new tag arrived and reinstall (downgrade) to its pin.

### 修復 / Repair

**毎回の起動そのものが自己修復的**です：

**Every normal launch is itself self-healing**:

- `preflight.sh`/`.bat` が毎回 `setup.py skills rebuild` を実行し、スキル欠損・破損を修復します。

手動での完全修復が必要な場合は、GitHub Releases の ZIP を既存フォルダの上に再展開し、一度起動すれば `preflight` が残りを自動修復します（`venv/`・`config.toml`・`files/` は ZIP に含まれないため保持されます）。

For a full manual repair, re-extract the GitHub Releases ZIP over the existing folder and launch once — preflight repairs the rest automatically (`venv/`, `config.toml`, `files/` aren't in the ZIP, so they're preserved).

### リリース手順 / Cutting a Release

このディレクトリ自身が `kh813/agent-deck` の開発環境なので、別リポジトリへの追従・ピン留めという概念はありません。通常の開発は `main` ブランチへのコミット・プッシュで進め、リリースは `vX.Y.Z` タグを打つことで `.github/workflows/release.yml` が自動的にビルド・署名・公開します（詳細は CLAUDE.md）。バージョン番号は `package.json`・`src-tauri/Cargo.toml`・`src-tauri/tauri.conf.json` の3箇所を揃えて更新してください。

Since this directory is itself the `kh813/agent-deck` development environment, there's no separate "track/pin to upstream" concept. Regular development proceeds via commits/pushes to `main`; a release is cut by pushing a `vX.Y.Z` tag, which `.github/workflows/release.yml` builds, signs, and publishes automatically (see CLAUDE.md). Keep version numbers in sync across `package.json`, `src-tauri/Cargo.toml`, and `src-tauri/tauri.conf.json`.

#### テスト→本番の昇格フロー / Test-Then-Promote Flow

先にテスト版を配って動作確認し、問題なければ本番へ、という流れが必要な場合は、タグ名にsemverのプレリリース識別子（ハイフン付き）を使ってください：

```bash
git tag -a v0.0.22-rc1 -m "Release candidate for v0.0.22"
git push origin v0.0.22-rc1
```

`release.yml` はタグが `vX.Y.Z-なにか` の形（例: `-rc1`・`-test1`・`-beta.2`）にマッチする場合、そのリリースを GitHub 上で **pre-release** としてマークします。`self_update.py` は GitHub の `/releases/latest` API だけを見ますが、これは仕様上「pre-releaseでもdraftでもない最新リリース」しか返しません。つまり pre-release は「Check for agent-deck Updates...」メニューにも既存インストールの自動チェックにも一切現れず、通常ユーザーへは配信されません。

**テストする側 / For testers:** GitHub の Releases ページから該当バージョンの ZIP を手動でダウンロードし、既存インストールの上に展開してください（§7a・修復手順と同じ要領）。

**本番への昇格 / Promoting to production:** 検証OKになったら、GitHub の当該リリースを編集し、「Set as a pre-release」のチェックを外して保存するだけです。**再ビルド・再タグは不要** — 検証したのと全く同じバイナリがそのまま本番配信されます。次にメニューから確認したユーザー・次回起動時に自動チェックしたユーザーへ、そのまま配信されます。

> タグ名がそのまま（例: `v0.0.22-rc1`）本番リリースとして残ることに違和感がある場合は、代わりに検証後もう一度クリーンな `vX.Y.Z` タグを打って再ビルドする運用でも構いません。ただしその場合は「テストしたバイナリ」と「実際に配信するバイナリ」が別物（同じソースからの再ビルド）になる点に注意してください。

```bash
# リリース一覧 / Release list
open https://github.com/kh813/agent-deck/releases
```

---

## 5. 設定ファイル / Configuration File

```bash
cp config/config.toml.template config.toml
# エディタで開いて組織固有の値を埋める
# Open in an editor and fill in your org-specific values
```

| セクション / Section | キー / Key | 説明 / Description |
|---|---|---|
| `[oauth]` | `client_id` / `client_secret` | GCP OAuth2 クレデンシャル |
| `[drive]` | `catalog_folder_id` / `catalog_url` / `catalog_file_id` | スキルカタログ（Drive）関連 |
| `[company]`（任意 / optional） | `domain` / `portal_url` / `salesforce_url` | 公開版のテンプレートには**宣言されていない**。組織向け `config.toml` がこのセクションを上乗せするオーバーレイという位置づけ |
| `[template]` | `name` / `url` | PPTX テンプレート |
| `[user]` | `email` | 省略時は OS ログイン名から自動判定（`[company].domain` が必要） |
| `[notifications]` | `chat_webhook_url` | Google Chat 通知（`notify-chat` スキルが設定を案内） |

`config/__init__.py` が `tomllib`（Python 3.11+ 標準）または `tomli`（バックポート）で `config.toml` を読み込みます。

---

## 6. Google Cloud API の設定 / Google Cloud API Setup

| API | 用途 / Purpose |
|-----|----------------|
| Google Drive API | スキルカタログの同期・公開（`skills_catalog.py`）/ Skill catalog sync & publish |
| Google Calendar API / Tasks API | `/daily-schedule` |

| スコープ / Scope | 用途 / Purpose | トークンファイル / Token file |
|-----------------|----------------|-------------------------------|
| `drive` (読み書き / read-write) | カタログ同期・公開・PPTXテンプレート取得・config/secretのバックアップ復元（`skills_catalog.py` / `drive_upload.py` / `drive_migrator.py` / `backup_config.py` / `restore_config.py`） | `~/.gemini/agent_ui_library_token.json` |
| `calendar.readonly` / `tasks.readonly` | カレンダー・タスク読み取り（`gcalendar.py`） | `~/.gemini/agent_ui_calendar_token.json` |

> 全ての `drive` フルスコープ利用箇所が同一のトークンファイルを共有するよう統一済みです（旧: `backup_config.py`/`restore_config.py` のみ `agent_deck_library_token.json` という別名を使っており、`skill-catalog` 等で認可済みでも別途ブラウザ認可が要求される不整合があったが解消済み）。

新しい Google API を追加する場合: (1) GCP コンソールで有効化 (2) 対応スクリプトの `SCOPES` に追加 (3) 既存トークンにスコープが無ければ次回実行時に自動で再認証されます。

> **OAuth 同意画面の公開ステータスに注意 / Watch the OAuth consent screen publishing status:** `drive`（フル読み書き）は Google 側で「制限付き（restricted）」スコープに分類されます。同意画面を「テスト」ステータスのまま運用する場合、テストユーザーとして個別登録したアカウントしか認可できず（上限100人）、かつ未検証アプリが発行するリフレッシュトークンは7日で失効し、期限が切れると全員が再認可を求められます。全社展開する場合は同意画面を「本番」に公開する（Google のアプリ検証が必要になることがある）か、少なくとも対象ユーザー全員をテストユーザーとして登録してください。

---

## 7. 配布・バックアップ手順 / Distribution & Backup

### 7a. 新規インストール / New Installs

新規に agent-deck を導入するメンバーの手順は、以下の3ステップのみです：

The procedure for a new team member is just three steps:

1. `kh813/agent-deck` の GitHub Releases から `agent-deck-mac.zip` / `agent-deck-win.zip` を直接ダウンロード
2. 組織向け `config.toml`（§5 の手順で作成したもの）をプロジェクトルートに配置
3. `agent-deck.app` / `agent-deck.exe` をダブルクリック

これで `preflight.sh`/`.bat` → venv 構築 → skill-catalog sync（組織固有スキル自動導入）→ スキルビルドまで、公開リポジトリのコードだけで完了します。ZIP は実行時生成ディレクトリ（`venv/`、`.gemini/skills/` 等）を含まないため、初回起動時に自動生成されます。

This completes venv setup → skill-catalog sync (auto-pulling org-specific skills) → skills built, using only the public repo's own code. The ZIP doesn't include runtime-generated directories (`venv/`, `.gemini/skills/`, etc.) — those are created automatically on first launch.

### 7b. 設定・秘匿情報のバックアップ / Config & Secret Backup

`config.toml`・`client_secret_*.json`・`docs/` は git 管理外のため、このディレクトリが失われると復元できません。`python/scripts/tools/backup_config.py` が、これらを ZIP 化して組織の Google Drive にアップロードします（既存ファイルを上書き更新）。

`config.toml`, `client_secret_*.json`, and `docs/` are all git-excluded — if this directory is ever lost, they can't be recovered from git. `python/scripts/tools/backup_config.py` zips these up and uploads them to the org's Google Drive (updating the existing file in place).

```bash
python3 python/scripts/tools/backup_config.py
```

アップロード先は `config.toml` の `[drive].config_backup_file_id` で指定します（§5・`config/config.toml.template` 参照）。設定・秘匿情報を変更したときは、このスクリプトを再実行してバックアップを最新化してください。

The upload target is set via `[drive].config_backup_file_id` in `config.toml` (see §5 and `config/config.toml.template`). Re-run this script whenever config/secrets change, to keep the backup current.

#### 復元 / Restore

`python/scripts/tools/restore_config.py` が対の復元スクリプトです。上書きされる既存ファイルは黙って消さず、`<ファイル名>.bak-<タイムスタンプ>` にリネームしてから展開します。

`python/scripts/tools/restore_config.py` is the counterpart restore script. Any existing file it would overwrite is renamed aside to `<name>.bak-<timestamp>` first, never silently clobbered.

**既に動く `config.toml` があるマシン（バックアップの再同期など）/ On a machine that already has a working config.toml (e.g. re-syncing the latest backup):**

```bash
python3 python/scripts/tools/restore_config.py
```

**まっさらな新規マシン（`config.toml` が無い）/ On a genuinely fresh machine (no config.toml yet):**

`config.toml` 自体が無いと、そこに書かれた OAuth クレデンシャルを使う Drive API 呼び出しができません（鶏と卵の関係）。まずブラウザで（既存の組織アカウントの Drive アクセス権のみで、OAuth 設定不要）ZIP を手動ダウンロードし、このスクリプトにパスを渡してください：

Without `config.toml` itself, there's no OAuth credential to call the Drive API with (a chicken-and-egg problem). Instead, download the ZIP manually via a browser first (using just the org account's existing Drive access — no OAuth setup needed), then point this script at it:

```bash
python3 python/scripts/tools/restore_config.py --zip ~/Downloads/agent-deck-config.zip
```

---

## 8. PPTXテンプレートの変更方法 / Changing the PPTX Template

PPTX テンプレートは配布 ZIP に含まれません。ユーザーが `/slide-generator` または `/slide-interviewer` を初めて実行したときに、各スキル同梱の `fetch_template.py` が Google Drive API（OAuth 認証）でダウンロードします。

The PPTX template isn't in the distribution ZIP. Each skill's bundled `fetch_template.py` downloads it via the Google Drive API (OAuth) on first run of `/slide-generator` or `/slide-interviewer`.

- `python/skills-personal/slide-generator/scripts/fetch_template.py` — テンプレートのダウンロード
- `python/skills-personal/slide-generator/scripts/generate_pptx.py` — PPTX 生成（テンプレート不在時に自動ダウンロード）

スライド関連スクリプトは slide-generator / slide-interviewer スキルに同梱され、skill-catalog の `_default/` から配信されます。

**テンプレート URL 変更時 / When the template URL changes:**

1. このディレクトリの `config.toml` の `[template]` を更新（§5・§7a）— 新規インストールはこのファイルから直接読みます
2. 既存ユーザーには、旧テンプレートファイルを手動削除するよう案内（ファイル名が変わらない場合は自動削除されない）:
   ```
   files/SEG_PPT_TEMPLATE.pptx を削除してから /slide-generator を実行してください。
   ```

**Drive でのテンプレート保存形式と容量制限:** ネイティブ PPTX ファイルなら容量制限なし。Google スライド形式のまま保存すると `exportSizeLimitExceeded`（約10MB）で失敗するため、10MB を超えるテンプレートは **ファイル → ダウンロード → Microsoft PowerPoint (.pptx)** で書き出し、Drive に通常ファイルとして（Google スライドに変換せず）再アップロードしてください。

---

## 9. 主要技術 / Key Technologies

| コンポーネント / Component | 技術 / Technology |
|---------------------------|-------------------|
| AIエージェント / AI Agent | Antigravity CLI (`agy`)（設定ディレクトリ名は歴史的経緯で `.gemini/` のまま） |
| デスクトップランチャー / Desktop launcher | Tauri（Rust）— `kh813/agent-deck` |
| スキル形式 / Skill format | Markdown (`SKILL.md`) を ZIP に格納（`.skill`） |
| スキルカタログ / Skill catalog | Google Drive（`_default/` フォルダの自動同期 + 個人カタログの手動 download/upload） |
| 自己更新 / Self-update | GitHub Releases API（`self_update.py`） |
| スライド生成 / Slide generation | Marp CLI + python-pptx |
| ブラウザ自動化 / Browser automation | Playwright（スクリプト）+ Playwright MCP（自然言語） |
| セットアップスクリプト / Setup scripting | Python 3（クロスプラットフォーム）、Windows は追加で Batch/PowerShell |

---

## 10. ファイルエンコーディングの制約 / File Encoding Constraints

### すべての .bat ファイル — Shift-JIS / CR+LF 必須

プロジェクト内の **すべての `.bat` ファイル** は **Shift-JIS（CP932）エンコーディング・CR+LF 改行** で保存しなければなりません。日本語版 Windows は BAT ファイルをシステムコードページ（CP932）で読み込むため、UTF-8 や LF のみの改行で保存すると文字化けや `set` コマンドの誤認識が発生します。

対象ファイル（現在存在するもの）/ Affected files (currently existing):
- `preflight.bat`（プロジェクトルート）
- `python/scripts/setup/build-skills.bat`
- `python/scripts/setup/setup.bat`
- `python/scripts/automation/automate.bat`

> ⚠️ macOS/Linux 上での編集・コミット・チェックアウトで、git の `core.autocrlf` により改行が LF に変換される場合があります。`.gitattributes` に `*.bat eol=crlf` を設定し、git が自動で維持するようにしています。

```bash
# 改行コードの確認（CRLF であること）
file preflight.bat
```

> **`preflight.bat` への `chcp` 追加は禁止（実インシデント）** — 文字化け対策として `chcp 65001` を追加したところ、Windows 実機で "... was unexpected at this time." という cmd.exe パーサエラーが発生し、スクリプトそのものが動かなくなった。原因はスクリプト内の生 UTF-8 バイト（日本語 echo）と、コードページ切り替えのタイミングが cmd.exe のパーサを混乱させたためと推定。**確定済みの安全な修正は Python 側（`setup.py`/`auth.py`/`skills_catalog.py` の `sys.stdout.reconfigure`）のみ** — `.bat` 側の `chcp` は再度追加しないこと（`python/tests/test_windows_utf8.py::TestPreflightBatDoesNotSetCodepage` がリグレッションガード）。同様に、`preflight.bat` の複数行括弧ブロック（`if (...) else (...)`）に `goto`/パイプを混在させるのも避けること — cmd.exe の解析を混乱させ、非ASCIIとは無関係の構文エラーを引き起こしたことがある（`TestPreflightBatHasNoMultilineParenBlocks` がガード）。

---

## 11. テストスイート / Test Suite

`python/tests/` にユニット・リグレッションテストを収録。配布物には含まれません。

```bash
pytest python/tests/ -v
cd src-tauri && cargo test --lib
```

| ファイル / File | 対象 / Target |
|---|---|
| `test_self_update.py` | `self_update.py`（atomic swap、マーカー検証、Windows ロック済み exe のリネーム退避、組織リブランド対応、等） |
| `test_windows_utf8.py` | Windows での UTF-8 stdout/stderr 再設定（CP932/CP1252 文字化け・クラッシュ対策）、全 `.bat` ファイルの ASCII+CRLF チェック、`preflight.bat` に `chcp`/複数行括弧ブロックが無いことのリグレッションガード、`release.yml` の zip 化ステップが `messages/` を含むことの検証 |
| `test_file_encoding_policy.py` | `python/scripts/**/*.py` を AST スキャンし、非ASCII文字列を `print()` しているファイルに Windows 用ガードが入っていることを検証 |
| `test_skill_build.py` | スキルのビルド・インストールフロー |
| `test_skills_catalog_sync.py` | `skills_catalog.py` のカタログ同期 |
| `test_config_notifications.py` | 設定・通知系 |
| `test_drive_download.py` / `test_drive_migrator.py` | Drive 連携 |
| `test_markitdown_convert.py` / `test_rename_files.py` | 各スキルのロジック |
| `test_agy_scheduler.py` / `test_agy_scheduled_prompt.py` / `test_automate_dispatch.py` / `test_gcalendar.py` / `test_notify_chat.py` | 自動化・通知系 |

Rust 側（`src-tauri/`）のテストは PTY・pre-launch コマンドなど、ランチャー本体の挙動をカバーします。

---

## 12. トラブルシューティング / Troubleshooting

### エラーログ / Error Log

**場所 / Location:** `tmp/logs/agent-deck.log`

10 MB を超えると `agent-deck.log.1` にバックアップしてから新しいファイルを作成します。問題発生時はこのファイルの提供を依頼してください（メールアドレスやファイルパスを含む場合があります）。

### スキルカタログインデックスの修復 / Repairing the Skill Catalog Index

```bash
python3 python/scripts/setup/skills_catalog.py update-index
```

Drive をフルスキャンしてインデックスを一から再作成します。

### カタログ共有ファイルの自動修復 / Self-Healing Catalog File

Drive 上の共有カタログファイル（`skill-catalog.md`）が誤って削除された場合、次回の `upload`/`delete`/`change-owner` 実行時に自動で再作成され、新しいファイル ID が `config.toml` の `catalog_file_id` に自動書き込みされます。表示されたメッセージに従い、`config/config.toml.template`（および §5b・§7a の社内配布用 `config.toml`）を新しい ID に手動更新してください。

### Windows で .exe が起動後すぐ消える / .exe disappears right after launch on Windows

2026-07-19 以前の既知バグ: `install_agent_ui.py`／`self_update.py` の双方が、実行中の exe を `unlink()` してから同じパスに新しい exe を作成しようとしていました。Windows は実行中の exe の delete/rename は許可しますが（OS ローダーが `FILE_SHARE_DELETE` で開くため）、同じパスへの再作成は最後のハンドルが閉じる（＝再起動する）までできません。両方とも「削除ではなくリネーム退避」方式に修正済みです。もし同様の症状（更新後にプロジェクトルートに exe が存在しない）を見つけたら、まずこのパターンを疑ってください。

Known bug (fixed 2026-07-19): both `install_agent_ui.py` and `self_update.py` used to `unlink()` the running exe, then try to create a new file at the same path. Windows allows deleting/renaming a running exe but won't let you recreate one at that exact path until the last handle closes (i.e. until restart). Both are now fixed to rename the old exe aside instead of deleting it. If you see the exe missing from the project root right after an update, suspect this pattern first.

---

## 13. ユーザー入力の設計 / Designing User Input in Skills

### `ask_user` ツールとは / What is the `ask_user` tool

Antigravity CLI に組み込まれた `ask_user` ツールを使うと、テキスト出力で質問するかわりに、スタイルされたダイアログでユーザーへの入力要求を表示できます。「Answer Questions」ヘッダー付きの明るいボックスが表示され、視認性が高く、Esc でキャンセルもできます。

The `ask_user` tool is built into Antigravity CLI. Instead of asking questions via plain text output, it displays a styled dialog box with an "Answer Questions" header, and allows canceling with Esc.

**ANTIGRAVITY.md のグローバルルール:** 「ユーザーへの入力要求は必ず `ask_user` ツールを使用すること」を記載。SKILL.md 側でも呼び出し例を明示することで、モデルが確実に従います。

### `ask_user` パラメーター詳細 / Parameter Reference

ツール名 / Tool name: **`ask_user`** ／ パラメーター: `questions`（配列、必須）— 1〜4件

| フィールド / Field | 型 / Type | 必須 / Required | 説明 / Description |
|---|---|---|---|
| `question` | string | ✓ | 質問本文（複数行可） |
| `header` | string | ✓ | タグとして表示される短いラベル（最大16文字） |
| `type` | string | — | 質問種別（省略時: `"choice"`） |
| `options` | array | `"choice"` のとき必須 | 2〜4択の選択肢 |
| `multiSelect` | boolean | — | `"choice"` で複数選択を許可 |
| `placeholder` | string | — | テキスト入力のヒント |

| `type` | 用途 / Use case |
|---|---|
| `"text"` | 自由記述 |
| `"choice"` | 2〜4択の選択 |
| `"yesno"` | Yes / No 確認 |

`options` の各オブジェクトは `label`（表示テキスト）と `description`（補足説明）を必須で持ちます。戻り値はモデルに JSON 文字列として返されます（`{"answers": {"0": "回答"}}`）。

#### 使用例 / Usage examples

**テキスト入力:**
```json
{"questions": [{"header": "Search Topic", "question": "検索キーワードを入力してください。\nEnter a search keyword.", "type": "text", "placeholder": "e.g., Expense reimbursement"}]}
```

**選択肢:**
```json
{"questions": [{"header": "Conflict", "question": "同名ファイルが存在します。どうしますか？", "type": "choice", "options": [{"label": "上書き", "description": "既存ファイルを上書きする"}, {"label": "スキップ", "description": "既存ファイルを保持する"}]}]}
```

**Yes/No 確認:**
```json
{"questions": [{"header": "Confirm", "question": "このまま実行しますか？", "type": "yesno"}]}
```

### 他の Agent AI で SKILL.md を実行する場合 / Running SKILL.md on Other Agent AIs

SKILL.md は Markdown 形式の指示書であるため、Antigravity CLI 以外のエージェント（Claude Code、GitHub Copilot Agent、OpenAI Codex 等）でも原則として読み込んで実行できます。ただし `ask_user` は Antigravity CLI 固有の組み込みツールのため、他のエージェントでは利用できません（テキスト出力→ユーザー返信、に自然に読み替えられることが多い）。

現時点で agent-deck のスキルは Antigravity CLI 専用として設計されており、クロスエージェント対応は行っていません。

---

## 14. セキュリティ設定 / Security Settings

agent-deck は **二層のセキュリティ** でエージェントの動作範囲を制限しています。

| 層 / Layer | 仕組み / Mechanism | 役割 / Role |
|---|---|---|
| 第1層（行動制約） | `ANTIGRAVITY.md` の記述 | モデルへのルールとして何を操作してよいか・悪いかを定義 |
| 第2層（技術的強制） | agy ポリシーファイル（TOML） | ツール呼び出し自体をランタイムでブロック。YOLO モードでも有効 |

### Google Workspace アカウントでの利用 / Using a Google Workspace Account

**現状（技術的な強制チェックはない）/ Current state (no technical enforcement):** agent-deck 自体は、サインインしたアカウントが会社ドメインかどうかを検証するコード（sentinel ファイル・`google_accounts.json` の確認など）を持ちません。`preflight.sh`/`.bat`・`setup.py`・Rust 側のいずれにもそのようなチェックは実装されていません。

「会社の Google Workspace アカウントを使うこと」は `ANTIGRAVITY.md` の **Authentication** セクションにモデルへの指示として記載されているのみです（プロンプトレベルの指示であり、技術的なブロックではありません）。サインイン自体は agy 自身の標準的な Google OAuth フローで、初回起動時にブラウザが自動で開きます。

個人アカウントでの利用を技術的に防ぎたい場合は、Google Workspace 管理コンソール側で当該 OAuth クライアントの利用をドメイン内ユーザーに制限するなど、agent-deck の外側で対応する必要があります。

**再認証を強制したい場合 / To force re-authentication:** agy 自身のトークンファイル（`~/.gemini/antigravity-cli/antigravity-oauth-token` 等、バージョンにより異なる場合があります）を削除してください。

### ANTIGRAVITY.md の行動制約 / ANTIGRAVITY.md Behavioral Constraints

`ANTIGRAVITY.md` の **File Access Policy** セクションで、`files/`・`tmp/`・OS標準フォルダ以外の操作、システムディレクトリ、認証情報・設定ドットファイル、アプリケーション設定フォルダへの書き込みを禁止しています。

### ポリシーファイル / Policy File

**インストール先:** `~/.gemini/policies/agent-deck.toml`（`setup.py init`/`skills rebuild` がコピー）。`priority` 値が大きいほど高優先で、deny ルールは YOLO モードの allow-all より高優先度に設定されています。

| priority | カテゴリ / Category | 動作 / Action |
|---|---|---|
| 250 | 外部ファイルシステム保護 | deny（YOLO を上書き） |
| 200 | `src/` 書き込み禁止 | deny（YOLO を上書き） |
| 100 | スキルアクティベーション・自動化コマンド | allow（確認省略） |

### 既知の制限 / Known Limitations

`list_directory`・`glob`・`grep_search` ツールはパスパターンによるブロック対象外のため、設定ファイルの探索は ANTIGRAVITY.md の行動制約のみに依存します。同様に `files/`・`tmp/` 以外への新規ファイル作成や、Windows のバックスラッシュパスも技術的にはブロックされないケースがあります。

---

## 15. MCP サーバー設定 / MCP Server Configuration

agy の `.gemini/settings.json` に `mcpServers` を登録することで、追加ツールを提供します。現在は Playwright MCP（ブラウザ自然言語操作）を設定しています。

```json
"mcpServers": {
  "playwright": {
    "command": "npx",
    "args": ["@playwright/mcp@latest", "--browser", "chrome"]
  }
}
```

`--browser chrome` はシステムインストール済みの Google Chrome を使用（Playwright 内蔵 Chromium ではない）。別の MCP サーバーを追加する場合は `mcpServers` オブジェクトにエントリを追記してください。

---

## 16. ブラウザ自動化スキルの開発 / Browser Automation Skill Development

### 設計方針 / Design Philosophy

ブラウザ自動化スキルは `SKILL.md`（AI への指示）と `run.py`（実行スクリプト、ユーザーが自然言語で呼び出したときに AI が生成・実行）で構成します。AI が `run.py` を生成する際の一貫性を確保するため、ブラウザ操作は共通ユーティリティ（`chrome_utils.py` 相当の関数群）を使います。

> **配置場所の注意 / Where these live now:** 既存の組織固有スキル（ask-portal・download-* 等）は依存関数を**スキルディレクトリ自身に同梱**する自己完結型です。`python/scripts/automation/common.py`/`chrome_utils.py`/`excel_utils.py` は、新しいスキルを著作する際の参考実装として使えますが、新規スキルは自分のディレクトリ内にこれらの必要な関数を同梱するのが標準です（§2）。

### 層の役割分担 / Layer Responsibilities

| ファイル / File | 役割 / Role | 変化頻度 / Change frequency |
|---|---|---|
| `chrome_utils.py` | ブラウザ操作の共通実装（ログイン待機・データ取得・保存） | 低 |
| `run.py` | サイト固有のトリガー操作（どのボタンを押すか） | 高 |
| `SKILL.md` | AI へのワークフロー指示 | 中 |

### `chrome_utils.py` 関数リファレンス / Function Reference

| グループ / Group | 関数 / Function | 説明 / Description |
|---|---|---|
| **ナビゲーション** | `open_url` / `open_new_tab` / `wait_until_authenticated` | URL 遷移・認証待機 |
| **ログイン** | `fill_credentials` / `handle_google_signin` / `handle_microsoft_signin` | 各種サインインの自動操作 |
| **操作** | `scroll_to_bottom` / `select_option` / `dismiss_popup` | スクロール・選択・ポップアップ処理 |
| **データ取得** | `get_text` / `get_texts` / `get_attribute` / `get_table` / `get_structured_list` / `get_links` | テキスト・属性・テーブル・構造化リストの抽出 |
| **保存** | `save_csv` / `save_json` / `save_text` / `save_page_html` / `save_page_text` / `expect_and_save_download` | Downloads への保存 |
| **キャプチャ** | `screenshot` / `save_pdf` | スクリーンショット・PDF 保存 |

`get_structured_list(page, item_selector, fields, limit)` が「繰り返し要素から構造化データを抽出する」ユースケースの主力関数です。フィールド指定は `"h2"`（テキスト）、`"a@href"`（属性）、`"@data-id"`（アイテム自身の属性）の3パターン。

### `run.py` の基本パターン / Basic run.py Pattern

```python
from common import get_chrome_context
from chrome_utils import open_url, get_structured_list, save_csv
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    context, page = get_chrome_context(p)
    open_url(page, "https://example.com/login")
    page.click("#google-signin-btn")  # サイト固有のトリガーのみ run.py に残す

    from chrome_utils import wait_until_authenticated
    wait_until_authenticated(page, ["example.com/dashboard"])
    data = get_structured_list(page, ".item", {"title": "h2", "url": "a@href"})
    save_csv(data, "result.csv")
```

`ANTIGRAVITY.md` の **Browser Automation Skills** セクションで、`run.py` 生成時は共通関数を使うよう明記しています。新しい関数を追加したら `ANTIGRAVITY.md` の関数テーブルも更新してください。

---

## 17. Excel 自動化スキルの開発 / Excel Automation Skill Development

### 設計思想 / Design Philosophy

AI が `run.py` を生成する際の一貫性を確保するため、Excel 操作はすべて `excel_utils.py` の関数を使います。

### `excel_utils.py` 関数リファレンス / Function Reference

| グループ | 関数 | 概要 |
|------|------|------|
| ファイル | `open_workbook` / `new_workbook` / `open_or_create` / `save_workbook` | ワークブックの開閉・保存 |
| シート | `get_sheet` / `get_or_create_sheet` / `list_sheets` | シート操作 |
| 読み取り | `read_all` / `read_column` / `find_row` / `get_last_row` | データ読み取り |
| 書き込み | `write_cell` / `append_row` / `append_rows` / `update_row` | データ書き込み |
| 集計 | `sum_column` / `count_column` / `filter_rows` / `aggregate` | 集計処理（`aggregate` は pandas ベース） |
| 変換 | `from_records` / `to_records` / `from_csv` | 辞書リスト・CSV との相互変換 |

### `aggregate` の使用例 / Usage Example

```python
from excel_utils import open_workbook, get_sheet, aggregate

wb = open_workbook("~/Downloads/sales.xlsx")
sheet = get_sheet(wb, "売上データ")
result = aggregate(sheet, "部署", {"売上": "sum", "案件数": "count"})
```

### chrome_utils との連携パターン / Integration with chrome_utils

```python
from common import get_chrome_context
from chrome_utils import open_url, get_structured_list
from excel_utils import open_or_create, get_or_create_sheet, append_rows, save_workbook
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    context, page = get_chrome_context(p)
    open_url(page, "https://example.com/data")
    records = get_structured_list(page, "tr.data-row", {"date": "td.date", "item": "td.item", "value": "td.value"})

wb = open_or_create("~/Downloads/data.xlsx")
sheet = get_or_create_sheet(wb, "取得データ")
append_rows(sheet, records)
save_workbook(wb, "~/Downloads/data.xlsx")
```

`ANTIGRAVITY.md` の **Excel Automation Skills** セクションに使用ルールを明記。新しい関数を追加したら関数テーブルも更新してください。
