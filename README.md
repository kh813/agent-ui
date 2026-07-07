# agent-ui

`agent-ui` は、AIベースのコマンドラインツール（主に **Antigravity CLI (`agy`)**）をデスクトップ上で快適に操作するための、マルチAI CLIラッパーデスクトップアプリケーションです。

Tauri、Rust、および React を使用して構築されており、軽量でセキュア、そしてプレミアムなデザインのデスクトップインターフェースを提供します。

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

---

## ⚙️ UIカスタマイズ設定 (`agent_config.json`)

`agent-ui` は、組み込まれる親アプリケーションやプロジェクト環境に応じてUIの表示内容を柔軟にカスタマイズできます。

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
`agent-ui` を独自のPythonエージェントや他のコマンドラインアシスタント（例: `my-custom-cli`）のGUIフロントエンドとして着せ替える例です。

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

### 設定パラメータ項目

| キー名 | 型 | 説明 | デフォルト値 |
| :--- | :--- | :--- | :--- |
| `app_name` | `string` | ヘッダーに表示されるアプリケーション名。 | `"agent-ui Chat Console"` |
| `default_theme` | `string` | 初期起動時のカラーテーマ (`light`, `dark`, `solarizedLight`, `solarizedDark`, `dracula`, `oneDark`)。 | `"light"` |
| `font_family` | `string` | ターミナルで適用されるフォントファミリー。 | `"Menlo, Monaco, 'Courier New', monospace"` |
| `font_size` | `number` | ターミナルの文字サイズ (px)。 | `13` |
| `engines` | `array` | サイドバーに表示し、対話に使用するCLIエンジンのリスト。 | (上記構成例の通り、デフォルトは `agy`) |

---

## 🚀 インストールと起動方法

### macOS (Apple Silicon 向け)
1. GitHubの Releases から `agent-ui-mac.zip` をダウンロードします。
2. ZIPを展開し、`agent-ui.app` を任意の場所に配置します。
3. 未署名アプリとしての macOS 隔離属性（quarantine）を解除するため、ターミナルで以下を実行します：
   ```bash
   xattr -cr /path/to/agent-ui.app
   ```
4. アプリをダブルクリックして起動します。

💡 同階層に以下のシェルスクリプト（`.command`）ファイルを作成しておくと、次回からダブルクリックだけで起動できます。
```bash
#!/bin/bash
cd "$(dirname "$0")"
xattr -cr ./agent-ui.app
open ./agent-ui.app
```

### Windows
1. GitHubの Releases から `agent-ui-win.zip` をダウンロードします。
2. ZIPを展開し、中にある `agent-ui.exe` を実行します。

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
