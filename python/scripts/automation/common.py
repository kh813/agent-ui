"""共通ユーティリティ: Chrome起動・ファイルリネーム"""

from __future__ import annotations
import os
import getpass
import platform
import shutil
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR.parents[2] / "python"))
from config import COMPANY_DOMAIN, USER_EMAIL, CONFIG_PATH  # noqa: E402

pf = platform.system()


def _detect_email_from_os() -> str:
    """OSログインユーザー名からメールアドレスを推定する。推定不能なら空文字を返す。"""
    try:
        login_user = getpass.getuser()
    except Exception:
        login_user = os.environ.get('USER') or os.environ.get('USERNAME', '')

    if not login_user:
        return ''

    # すでにメールアドレス形式
    if '@' in login_user:
        return login_user

    if pf == 'Windows':
        # GCPW: email の @ を _ に置換して最大20文字に切り詰めたユーザー名
        # ローカルパートは firstname.lastname 形式（ドットのみ、_ なし）なので
        # rfind('_') で @ だった位置を特定できる
        idx = login_user.rfind('_')
        if idx > 0:
            local = login_user[:idx]
            if '.' in local:
                return f"{local}@{COMPANY_DOMAIN}"
        return ''  # 判別不能 → 対話入力にフォールバック
    else:
        return f"{login_user}@{COMPANY_DOMAIN}"


def _save_email_to_config(email: str) -> None:
    """config.toml の [user] セクションに email を書き込む（tomlkit 不要）。"""
    import re
    text = CONFIG_PATH.read_text(encoding='utf-8')

    user_section_re = re.compile(r'^\[user\]', re.MULTILINE)
    email_line_re   = re.compile(r'^(# *)?email\s*=.*$', re.MULTILINE)

    if user_section_re.search(text):
        if email_line_re.search(text):
            text = email_line_re.sub(f'email = "{email}"', text, count=1)
        else:
            text = user_section_re.sub(f'[user]\nemail = "{email}"', text, count=1)
    else:
        text = text.rstrip() + f'\n\n[user]\nemail = "{email}"\n'

    CONFIG_PATH.write_text(text, encoding='utf-8')
    print(f"config.toml にメールアドレスを保存しました: {email}")


def get_email_account() -> str:
    """メールアドレスを返す。config.toml > OS自動検出 > 対話入力 の順で解決する。"""
    # 1. config.toml [user] email
    if USER_EMAIL:
        return USER_EMAIL

    # 2. OS ログインユーザーから自動検出
    email = _detect_email_from_os()
    if email:
        return email

    # 3. 対話的に入力して config.toml に保存
    print(f"メールアドレスを自動検出できませんでした。")
    email = input(f"メールアドレスを入力してください [{COMPANY_DOMAIN}]: ").strip()
    if not email:
        raise ValueError("メールアドレスが入力されませんでした")
    _save_email_to_config(email)
    return email


def _find_chrome_windows() -> str | None:
    """Windows 上で chrome.exe のパスを探す。見つかればパス文字列、なければ None。"""
    candidates = [
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
        os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe'),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path

    # Windowsレジストリから検索（インストール先が非標準な場合）
    try:
        import winreg
        reg_key = r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe'
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hive, reg_key) as key:
                    path = winreg.QueryValue(key, None)
                    if path and os.path.isfile(path):
                        return path
            except OSError:
                pass
    except ImportError:
        pass

    return None


def get_chrome_executable():
    """OSに応じたChromeの実行パスを返す。見つからなければ終了する。"""
    if pf == 'Windows':
        path = _find_chrome_windows()
        if path:
            return path
        print("Google Chrome が見つかりません")
        sys.exit(1)
    elif pf == 'Darwin':
        for app_dir in ('/Applications', os.path.expanduser('~/Applications')):
            app = os.path.join(app_dir, 'Google Chrome.app')
            if os.path.isdir(app):
                return os.path.join(app, 'Contents/MacOS/Google Chrome')
        print("Google Chrome が見つかりません (/Applications または ~/Applications を確認してください)")
        sys.exit(1)
    else:
        print("未対応のOSです")
        sys.exit(1)


def get_user_data_dir():
    """ChromeUserDataディレクトリのパスを返す。存在しなければ作成する。"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    user_data_dir = os.path.join(script_dir, 'ChromeUserData')
    os.makedirs(user_data_dir, exist_ok=True)
    return user_data_dir


def _get_system_chrome_dir():
    """システムChromeのユーザーデータディレクトリを返す"""
    if pf == 'Darwin':
        return os.path.expanduser('~/Library/Application Support/Google/Chrome')
    elif pf == 'Windows':
        return os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\User Data')
    return None


def sync_from_system_chrome(quiet: bool = False) -> bool:
    """システムChromeのCookiesをChromeUserDataにコピーする（ベストエフォート）。

    Chromeが開いていても動作する。Cookiesのコピーに成功したらTrueを返す。
    """
    src_root = _get_system_chrome_dir()
    if not src_root or not os.path.exists(src_root):
        return False

    dst_root = get_user_data_dir()
    dst_default = os.path.join(dst_root, 'Default')
    os.makedirs(dst_default, exist_ok=True)

    targets = [
        # Local State はコピーしない（OS固有の暗号化設定が含まれ上書きすると壊れる）
        (os.path.join(src_root, 'Default', 'Cookies'),    os.path.join(dst_default, 'Cookies')),
        (os.path.join(src_root, 'Default', 'Login Data'), os.path.join(dst_default, 'Login Data')),
    ]

    copied_cookies = False
    for src, dst in targets:
        if not os.path.exists(src):
            continue
        try:
            shutil.copy2(src, dst)
            for ext in ('-wal', '-shm', '-journal'):
                src_ext = src + ext
                if os.path.exists(src_ext):
                    try:
                        shutil.copy2(src_ext, dst + ext)
                    except Exception:
                        pass
            if os.path.basename(src) == 'Cookies':
                copied_cookies = True
        except Exception as e:
            if not quiet:
                print(f"[警告] {os.path.basename(src)} のコピーをスキップしました: {e}")

    return copied_cookies


def get_chrome_context(p, lang='ja-JP', headless=False):
    """専用 ChromeUserData で Chrome を起動して context と page を返す。

    headless=True を指定すると Chrome ウィンドウを表示せず実行する。
    セッションは update-user-data で保存されたものを使用する。
    """
    args = [
        f'--lang={lang}',
        '--disable-blink-features=AutomationControlled',
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-infobars',
    ]
    if headless:
        # Chrome 112+ new headless mode: UA does not include "HeadlessChrome",
        # preventing Google from detecting and blocking the headless browser.
        # Must set headless=False here and control via the flag instead.
        args.append('--headless=new')

    context = p.chromium.launch_persistent_context(
        get_user_data_dir(),
        headless=False,
        executable_path=get_chrome_executable(),
        args=args,
        # --use-mock-keychain は除外しない（Playwright デフォルトの mock keychain を使用）。
        # update-user-data も同じ mock keychain でクッキーを書き込むため、両者で
        # 暗号化鍵が一致し、セッションクッキーが正しく読み書きできる。
        ignore_default_args=['--enable-automation'],
    )
    page = context.pages[0] if context.pages else context.new_page()
    return context, page


def rename_download(download, new_filename):
    """ダウンロードファイルをDownloadsフォルダに指定名で保存する"""
    if pf == 'Windows':
        base_dir = os.path.join('C:\\Users', getpass.getuser(), 'Downloads')
    elif pf == 'Darwin':
        base_dir = os.path.join('/Users', getpass.getuser(), 'Downloads')
    else:
        base_dir = ''

    if base_dir:
        newpath = os.path.join(base_dir, new_filename)
        if os.path.exists(newpath):
            try:
                os.remove(newpath)
                print(f"古いファイルを削除しました: {newpath}")
            except Exception as e:
                print(f"ファイルの削除に失敗しました ({newpath}): {e}")
        download.save_as(newpath)
        print(f"保存しました: {newpath}")


def get_tmp_dir():
    """スクリーンショット等の一時ファイル保存先を返す。存在しなければ作成する。"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    tmp_dir = os.path.normpath(os.path.join(script_dir, '..', '..', 'tmp', 'dryrun'))
    os.makedirs(tmp_dir, exist_ok=True)
    return tmp_dir


def save_screenshot(page, name: str) -> str:
    """スクリーンショットを tmp/dryrun/<name>.png に保存してパスを返す"""
    path = os.path.join(get_tmp_dir(), f"{name}.png")
    page.screenshot(path=path, full_page=False)
    print(f"[DRY-RUN] スクリーンショット: {path}")
    return path


def find_in_frames(page, selector: str):
    """全フレームを横断してセレクタに一致する要素を探す。(frame, element) を返す。"""
    for frame in page.frames:
        try:
            el = frame.query_selector(selector)
            if el:
                return frame, el
        except Exception:
            pass
    return None, None


def check_element(page, selector: str, label: str) -> bool:
    """
    全フレームを横断してセレクタが存在するか確認する。
    disabled 状態も区別して報告する。
    """
    frame, el = find_in_frames(page, selector)
    if el is None:
        print(f"[DRY-RUN] ✗ {label} ({selector}) — 見つかりません")
        return False
    try:
        is_disabled = frame.evaluate("el => el.disabled", el)
    except Exception:
        is_disabled = False
    if is_disabled:
        print(f"[DRY-RUN] ✓ {label} ({selector}) — 検出OK（グレーアウト: 既に打刻済み）")
    else:
        print(f"[DRY-RUN] ✓ {label} ({selector}) — 検出OK（クリック可能）")
    return True


def open_downloads_folder():
    """Downloadsフォルダをファイルマネージャーで開く"""
    if pf == 'Windows':
        subprocess.Popen(
            ['explorer', os.path.join('C:\\Users', getpass.getuser(), 'Downloads')],
            shell=True
        )
    elif pf == 'Darwin':
        subprocess.call(["open", os.path.join('/Users', getpass.getuser(), 'Downloads')])
