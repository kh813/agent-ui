# agent-deck

`agent-deck` は、AIベースのコマンドラインツール（主に **Antigravity CLI (`agy`)**）をデスクトップ上で快適に操作するための、マルチAI CLIラッパーデスクトップアプリケーションです。

Tauri、Rust、および React を使用して構築されており、軽量でセキュア、そしてプレミアムなデザインのデスクトップインターフェースを提供します。

📖 **詳細ドキュメント**: このREADMEは概要のみです。より詳しい手順は以下を参照してください。
- [利用ガイド](docs/user_guide.md) — セットアップ・スキルの使い方・トラブルシューティング（エンドユーザー向け）
- [管理者ガイド](docs/admin_guide.md) — 配布・スキルカタログ運用・自己更新の仕組み・トラブルシューティング（管理者向け）

---

## 🌟 主な機能

* **リアルタイム PTY ストリーミング**
  * バックエンドで疑似ターミナル（PTY）を制御し、xterm.js を通じて高速かつスムーズにCLI出力を表示します。
  * **便利なキーボードショートカット**:
    * `Ctrl+Shift+C` (macOS: `Cmd+Shift+C`): ターミナル上の選択範囲をコピー
    * `Ctrl+Shift+V` (macOS: `Cmd+Shift+V`): クリップボードのテキストをターミナルへ貼り付け
    * `Ctrl+Shift+A` (macOS: `Cmd+Shift+A`): ターミナルのテキストを全選択
    * `Ctrl+C` (macOS: `Cmd+C`): 選択範囲がある場合はコピー、ない場合は実行中のプロセスに強制終了シグナル (SIGINT) を送信
* **対話型チャットコンソール**
  * 美しく使いやすいチャット型のインターフェースにより、CLIコマンドを入力せずに直感的なやり取りが可能です。
* **スキル（`skill`）フォルダの自動検出・リビルド**
  * 選択した作業ディレクトリ（CWD）内に `skill` フォルダがある場合、セッション開始前に自動でスキルのリビルド（`agy build`）をバックエンドで実行します。
* **作業ディレクトリ（CWD）の切り替え**
  * セッション開始前に、UIから直感的に作業ディレクトリを選択・変更できます。
* **リアルタイム・テーマ切り替え**
  * UI全体の配色およびターミナル背景色を瞬時に切り替え可能。
  * `Light (Default)`, `Dark`, `Solarized Light`, `Solarized Dark`, `Dracula`, `One Dark` の6種類のカラースキームを内蔵。
* **自動多言語対応 (Bilingual)**
  * OSのシステム言語設定を自動で判別し、日本語環境なら日本語、それ以外のロケール環境では英語表示に自動的に切り替わります。
* **Windowsバックグラウンド起動の最適化**
  * Windows環境において子プロセス（PowerShellやその他CLIコマンド）が起動する際、一瞬黒いコンソールウィンドウがポップアップ表示されるチラつきを抑え、完全にバックグラウンドで隠蔽された状態で実行します。
* **ポータブルZIP配布**
  * インストーラーによる配置ではなく、ダウンロードしたZIPを展開してすぐに実行できるポータブル設計。
* **スキルカタログ（組織内共有・自動配布）**
  * Google Drive 上の共有フォルダをスキルカタログとして利用し、チーム内でスキルを共有できます（下記参照）。

---

## 📦 スキルカタログと組織向け自動配布 / Skill Catalog & Org Auto-Distribution

`config.toml` の `[drive] catalog_folder_id` に Google Drive の共有フォルダを設定すると、そのフォルダがチームのスキルカタログになります。

> **前提条件（管理者が事前に1回だけ行うセットアップ）**: `catalog_folder_id` を設定するだけでは動作しません。事前に管理者が Google Cloud Console で（1）プロジェクトを作成し Drive API を有効化、（2）OAuth 2.0 クライアント ID（種類:「デスクトップアプリ」）を発行し、`config.toml` の `[oauth] client_id` / `client_secret` に設定しておく必要があります（テンプレート: `config/config.toml.template`）。この管理者セットアップが完了していれば、一般ユーザー側は追加の設定不要で、初回起動時にブラウザでの Google ログイン・同意のみ行います。詳細な手順・注意点（OAuth同意画面のテストユーザー制限など）は [管理者ガイド §6](docs/admin_guide.md#6-google-cloud-api-の設定--google-cloud-api-setup) を参照してください。

* **共有**: `skill-catalog share <name>` — 自分のスキルをカタログに登録（SKILL.md のみなら `.md`、スクリプト同梱なら `.zip` として自動選択）
* **取得**: `skill-catalog import <name>` — 他のメンバーのスキルを取り込み
* **自動配布**: 管理者が `skill-catalog publish <name>` でスキルを `_default/` フォルダに置くと、**カタログを設定した全端末の次回起動時に自動で導入・更新**されます（`_default/` から外せば自動で削除）。初回のみブラウザで Google 認可が必要です。
  * `_default/` フォルダの書き込み権限は Drive 側で管理者のみに絞ることを推奨します。

### 組織版としての再配布 / Shipping Your Org's Own Build

agent-deck は fork せずに「自組織版」を配布できるよう設計されています:

1. アプリ本体（`agent-deck.app` / `agent-deck.exe`）は**外側の名前を変えるだけ**でリブランドできます（例: `acme-console.app`）。メニューバーの「Settings」→「Check for agent-deck Updates...」から行う自己更新は、リブランド後の名前を維持したまま最新リリースへ更新します。
2. 組織固有のスキルやスクリプトは、スキルディレクトリに同梱して `publish` すればカタログ経由で全端末に配布されます — このリポジトリに手を入れる必要はありません。
3. 配布物は「GitHub Releases のビルド + 組織の値（`[oauth] client_id`/`client_secret` と `[drive] catalog_folder_id` を含む `config.toml`）」だけで完結します。

---

## ⚙️ UIカスタマイズ設定 (`agent_config.json`)

`agent-deck` は、組み込まれる親アプリケーションやプロジェクト環境に応じてUIの表示内容を柔軟にカスタマイズできます。

アプリの起動時、**作業ディレクトリ（CWD）** や **実行バイナリと同階層** の直下、またはそれぞれの場所に作成した **`config/` フォルダの内部**（例：`config/agent_config.json`）に設定ファイルを配置しておくことで、UIが自動的にその設定を読み込んで上書きします。

### 設定ファイルの構成例 (`agent_config.json`)

```json
{
  "app_name": "My Custom AI Console",
  "default_theme": "light",
  "font_family": "Menlo, Monaco, 'Courier New', monospace",
  "font_size": 13,
  "engines": [
    {
      "id": "agy",
      "name": "Antigravity",
      "command": "agy",
      "args": []
    }
  ]
}
```

### 📝 設定ファイルの記入例 (ユースケース別)

#### ① テーマとフォントをカスタマイズする例
デフォルトの Antigravity エージェントを使用しつつ、テーマを `Dracula`（ダーク系）に変更し、フォントサイズを大きくし、フォントファミリーに `Fira Code` を指定する例です。

```json
{
  "app_name": "Galaxy CLI Terminal",
  "default_theme": "dracula",
  "font_family": "'Fira Code', Consolas, monospace",
  "font_size": 15,
  "engines": [
    {
      "id": "agy",
      "name": "Antigravity",
      "command": "agy",
      "args": []
    }
  ]
}
```

#### ② 独自の自作CLIエージェントを組み込む例
`agent-deck` を独自のPythonエージェントや他のコマンドラインアシスタント（例: `my-custom-cli`）のGUIフロントエンドとして着せ替える例です。

```json
{
  "app_name": "My Project Assistant",
  "default_theme": "oneDark",
  "font_family": "SF Mono, Menlo, monospace",
  "font_size": 13,
  "engines": [
    {
      "id": "my-custom-agent",
      "name": "Project Agent",
      "command": "my-custom-cli",
      "args": ["chat", "--interactive"]
    }
  ]
}
```

#### ③ セッション開始前に親プロジェクト独自の準備処理を走らせる例
組み込み先のプロジェクトが、セッション開始前に独自のセットアップ・更新チェック・認証確認などを行いたい場合、`pre_launch_command` / `pre_launch_args` で任意のコマンドを指定できます。作業ディレクトリ（CWD）でこのコマンドが実行され、成功（終了コード0）した場合のみセッションが開始されます。

```json
{
  "app_name": "My Project Assistant",
  "engines": [
    { "id": "agy", "name": "Antigravity", "command": "agy", "args": [] }
  ],
  "pre_launch_command": "bash",
  "pre_launch_args": ["preflight.sh"],
  "pre_launch_required": true
}
```

`pre_launch_required` を `false` にすると、この処理が失敗してもセッションは開始されます（例: ネットワーク不通でも起動をブロックしたくないベストエフォートのバージョンチェックなど）。`pre_launch_command` が指定されていないプロジェクトでは、従来通り作業ディレクトリ直下の `skill` フォルダを自動検出してリビルドする挙動（5.7節）にフォールバックします。

OS ごとに異なるコマンドを実行したい場合は、`pre_launch_macos` / `pre_launch_windows`（`install`/`update`と同じ`{command, args}`形式）で上書きできます。指定した方のOSでは `pre_launch_command`/`pre_launch_args` より優先されます。

```json
{
  "app_name": "My Project Assistant",
  "engines": [
    { "id": "agy", "name": "Antigravity", "command": "agy", "args": [] }
  ],
  "pre_launch_macos":   { "command": "bash", "args": ["preflight.sh"] },
  "pre_launch_windows": { "command": "cmd",  "args": ["/c", "preflight.bat"] },
  "pre_launch_required": true
}
```

### 設定パラメータ項目

| キー名 | 型 | 説明 | デフォルト値 |
| :--- | :--- | :--- | :--- |
| `app_name` | `string` | ヘッダーに表示されるアプリケーション名。 | `"agent-deck Chat Console"` |
| `default_theme` | `string` | 初期起動時のカラーテーマ (`light`, `dark`, `solarizedLight`, `solarizedDark`, `dracula`, `oneDark`)。 | `"light"` |
| `font_family` | `string` | ターミナルで適用されるフォントファミリー。 | `"Menlo, Monaco, 'Courier New', monospace"` |
| `font_size` | `number` | ターミナルの文字サイズ (px)。 | `13` |
| `engines` | `array` | サイドバーに表示し、対話に使用するCLIエンジンのリスト。 | (上記構成例の通り、デフォルトは `agy`) |
| `pre_launch_command` | `string` | セッション開始前に作業ディレクトリ（CWD）で実行するコマンド。未指定なら`skill`フォルダ自動リビルド（5.7節）にフォールバック。 | (未指定) |
| `pre_launch_args` | `array` | `pre_launch_command`に渡す引数リスト。 | `[]` |
| `pre_launch_required` | `boolean` | `true`なら`pre_launch_command`失敗時にセッション開始を中断。`false`なら警告のみでセッションを開始。 | `true` |
| `pre_launch_macos` | `{command, args}` | macOSでのみ`pre_launch_command`/`pre_launch_args`を上書き。 | (未指定) |
| `pre_launch_windows` | `{command, args}` | Windowsでのみ`pre_launch_command`/`pre_launch_args`を上書き。 | (未指定) |

---

## 🚀 インストールと起動方法

### macOS (Apple Silicon 向け)
1. GitHubの Releases から `agent-deck-mac.zip` をダウンロードします。
2. ZIPを展開し、`agent-deck.app` を任意の場所に配置します。
3. 未署名アプリとしての macOS 隔離属性（quarantine）を解除する必要があります。方法は以下のどちらでも構いません。

   **方法A: ターミナルを使わず「システム設定」から許可する**

   ターミナルの操作に慣れていない方は、こちらの手順をお使いください。

   1. Finderで `agent-deck.app` をダブルクリックして、一度起動を試みます。
   2. 「"agent-deck.app"は、開発元を確認できないため開けません」といった警告ダイアログが表示されるので、「完了」（または「OK」）をクリックしていったん閉じます。
   3. 画面左上の Apple メニュー（りんごのマーク）をクリックし、「システム設定...」を開きます。
      * （macOS Monterey以前をお使いの場合は「システム環境設定」→「セキュリティとプライバシー」を開いてください）
   4. 左側のメニューから「プライバシーとセキュリティ」を選択します。
   5. 右側の画面を一番下までスクロールすると、「セキュリティ」の項目に「"agent-deck.app"は使用がブロックされました」という表示と、その横に「このまま開く」というボタンがあるので、それをクリックします。
   6. Macのログインパスワードの入力や Touch ID を求められた場合は入力・認証します。
   7. 再度 `agent-deck.app` をダブルクリックすると、もう一度確認ダイアログが表示されます。今度は「開く」ボタンがあるので、それをクリックすればアプリが起動します。

   ※ 一度この手順で許可すると、そのアプリについては次回以降ダイアログなしで起動できるようになります（ZIPを展開し直した場合は再度この手順が必要です）。

   **方法B: ターミナルを使う（慣れている方向け）**
   ```bash
   xattr -cr /path/to/agent-deck.app
   ```
4. アプリをダブルクリックして起動します。
5. 初回起動時に Antigravity CLI (`agy`) が見つからない場合、自動インストールを促すオンボーディング画面が表示されます。「Install Antigravity CLI」をクリックすると、アプリケーションと同階層の `./bin/` ディレクトリ配下に自動インストールされ、すぐに利用可能になります（ポータブル構成）。

💡 同階層に以下のシェルスクリプト（`.command`）ファイルを作成しておくと、次回からダブルクリックだけで起動できます。
```bash
#!/bin/bash
cd "$(dirname "$0")"
xattr -cr ./agent-deck.app
open ./agent-deck.app
```

### Windows
1. GitHubの Releases から `agent-deck-win.zip` をダウンロードします。
2. ZIPを展開し、中にある `agent-deck.exe` を実行します。
3. macOS と同様に、初回起動時に `agy` が検出されない場合は自動インストールが実行され、アプリと同階層の `./bin/` 配下にポータブルに配置されます。

---

## 🛠️ 開発者向けセットアップ

ローカル環境でのビルドおよび実行手順です。

### 前提条件
* [Rust](https://www.rust-lang.org/) (stable)
* [Node.js](https://nodejs.org/) (v20以上推奨)

### 手順

1. **依存関係のインストール**
   ```bash
   npm install
   ```

2. **開発サーバーの起動 (Live Reload)**
   ```bash
   npm run tauri dev
   ```

3. **ローカルでのプロダクションビルド**
   * **macOS (Apple Silicon)**
     ```bash
     npm run tauri build -- --target aarch64-apple-darwin
     ```
   * **Windows**
     ```bash
     npm run tauri build
     ```

---

## 📦 自動リリースビルド (CI/CD)

本プロジェクトは GitHub Actions による自動ビルドワークフローを統合しています。

1. プロジェクトバージョン（`package.json`, `Cargo.toml`, `tauri.conf.json`）を更新します。
2. バージョンタグ（例: `v0.0.2`）を作成して GitHub にプッシュします：
   ```bash
   git tag -a v0.0.2 -m "Release v0.0.2"
   git push origin v0.0.2
   ```
3. GitHub Actions 上で自動的にコンパイルが走り、バイナリが ZIP にパッケージングされて自動公開されます。

先にテスト版で動作確認してから本番公開したい場合は、タグ名に `v0.0.2-rc1` のようなプレリリース識別子を付けてください。GitHub 上で pre-release として公開され、既存インストールの自動アップデートには一切配信されません。詳細は [管理者ガイド「テスト→本番の昇格フロー」](docs/admin_guide.md#テスト本番の昇格フロー--test-then-promote-flow) を参照してください。
