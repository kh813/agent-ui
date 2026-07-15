"""Chrome ブラウザ操作ユーティリティ

ページ遷移・ログイン・テキスト抽出・保存など、Web からの情報収集に必要な
共通操作をまとめたモジュール。Chrome の起動は common.get_chrome_context() を使う。

【関数一覧】
  ナビゲーション : open_url, open_new_tab, wait_until_authenticated
  ログイン       : fill_credentials, handle_google_signin, handle_microsoft_signin
  操作           : scroll_to_bottom, select_option, dismiss_popup
  データ取得     : get_text, get_texts, get_attribute, get_table,
                   get_structured_list, get_links
  保存           : save_csv, save_json, save_text, save_page_html, save_page_text,
                   expect_and_save_download
  キャプチャ     : screenshot, save_pdf  ※ save_pdf は headless=True が必要

使用例:
    from common import get_chrome_context
    from chrome_utils import open_url, handle_google_signin, wait_until_authenticated, get_table, save_csv
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        context, page = get_chrome_context(p)
        open_url(page, "https://example.com/login")
        page.click("#google-signin-btn")           # サイト固有のトリガーだけ run.py に書く
        handle_google_signin(page, email, password)
        wait_until_authenticated(page, ["example.com/dashboard"])
        rows = get_table(page, "table.data")
        save_csv(rows, "result.csv")
"""

from __future__ import annotations
import csv
import getpass
import json
import platform
from pathlib import Path

pf = platform.system()


def _downloads_dir() -> Path:
    if pf == "Windows":
        return Path("C:\\Users") / getpass.getuser() / "Downloads"
    elif pf == "Darwin":
        return Path("/Users") / getpass.getuser() / "Downloads"
    else:
        return Path.home() / "Downloads"


# ------------------------------------------------------------------
# ナビゲーション
# ------------------------------------------------------------------

def open_url(page, url: str, wait_until: str = "domcontentloaded") -> None:
    """現在のページを url に遷移する。"""
    page.goto(url, wait_until=wait_until)


def open_new_tab(context, url: str):
    """新しいタブで url を開き、Page オブジェクトを返す。"""
    page = context.new_page()
    page.goto(url, wait_until="domcontentloaded")
    return page


def wait_until_authenticated(page, domains: list[str], timeout: int = 120, interval: int = 2) -> None:
    """URL が domains のいずれかを含むまで待機する。

    SAML リダイレクト・MFA の手動操作待ちに使う。
    認証トリガー（ボタンクリック等）はこの関数を呼ぶ前に済ませておく。
    timeout 秒以内に認証されなければ TimeoutError を送出する。

    使用例:
        page.click("#sso-login-button")
        print("Google 認証が必要な場合は操作してください...")
        wait_until_authenticated(page, ["app.example.com", "dashboard.example.com"])
        print("ログイン確認")
    """
    elapsed = 0
    while elapsed < timeout:
        if any(d in page.url for d in domains):
            return
        page.wait_for_timeout(interval * 1000)
        elapsed += interval
    raise TimeoutError(f"認証タイムアウト ({timeout}秒): {page.url}")


# ------------------------------------------------------------------
# ログイン
# ------------------------------------------------------------------

def fill_credentials(page, email_selector: str, password_selector: str,
                     submit_selector: str, email: str, password: str) -> None:
    """ID/Password フォームに入力してサブミットする。

    セレクターはサイトごとに異なるため、呼び出し側 (run.py) で指定する。
    サブミット後の認証完了待ちは wait_until_authenticated() で行う。
    """
    page.fill(email_selector, email)
    page.fill(password_selector, password)
    page.click(submit_selector)


def handle_google_signin(page, email: str, password: str) -> None:
    """Google のサインインページ (accounts.google.com) でメール・パスワードを入力する。

    Chrome セッション引き継ぎ済みでスキップされる場合は何もしない。
    MFA (push 通知・ハードウェアキー等) は自動操作できないため、
    この関数の後に wait_until_authenticated() で手動操作を待つこと。
    """
    try:
        page.wait_for_selector("input[type='email']", timeout=4000)
        page.fill("input[type='email']", email)
        page.click("#identifierNext")
        page.wait_for_timeout(1000)
    except Exception:
        return  # メール入力不要（セッション有効 or すでにパスワードステップ）

    try:
        page.wait_for_selector("input[type='password']", timeout=6000)
        page.fill("input[type='password']", password)
        page.click("#passwordNext")
    except Exception:
        pass  # パスワード入力不要（パスキー等にリダイレクト）


def handle_microsoft_signin(page, email: str, password: str) -> None:
    """Microsoft のサインインページ (login.microsoftonline.com) でメール・パスワードを入力する。

    Chrome セッション引き継ぎ済みでスキップされる場合は何もしない。
    MFA (Authenticator 等) は自動操作できないため、
    この関数の後に wait_until_authenticated() で手動操作を待つこと。
    """
    try:
        page.wait_for_selector("input[type='email']", timeout=4000)
        page.fill("input[type='email']", email)
        page.click("#idSIButton9")
        page.wait_for_timeout(1000)
    except Exception:
        return  # メール入力不要

    try:
        page.wait_for_selector("input[type='password']", timeout=6000)
        page.fill("input[type='password']", password)
        page.click("#idSIButton9")
    except Exception:
        pass  # パスワード入力不要


# ------------------------------------------------------------------
# 操作
# ------------------------------------------------------------------

def scroll_to_bottom(page, pause_ms: int = 1000, max_scrolls: int = 10) -> None:
    """ページ最下部までスクロールする（無限スクロール・遅延読み込み対応）。

    スクロールしてもページ高さが変わらなくなるか max_scrolls 回に達したら停止する。
    """
    prev_height = -1
    for _ in range(max_scrolls):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(pause_ms)
        curr_height = page.evaluate("document.body.scrollHeight")
        if curr_height == prev_height:
            break
        prev_height = curr_height


def select_option(page, selector: str, value: str) -> None:
    """<select> 要素で value または表示テキストに一致するオプションを選択する。

    カスタムドロップダウン（div 実装等）には使えない。
    """
    page.select_option(selector, value)


def dismiss_popup(page, selectors: list[str] | None = None) -> int:
    """ポップアップ・クッキー同意バナーを閉じる。閉じたボタン数を返す。

    selectors を省略するとよくある「同意」「閉じる」ボタンを自動検索する。
    カスタム selectors を渡すと優先して使う。
    """
    default_selectors = [
        "button:has-text('同意する')", "button:has-text('同意')",
        "button:has-text('Accept All')", "button:has-text('Accept')",
        "button:has-text('Allow All')", "button:has-text('Allow')",
        "button:has-text('OK')",
        "button:has-text('閉じる')", "button:has-text('Close')",
        "[aria-label='Close']", "[aria-label='閉じる']",
        "[data-dismiss='modal']",
    ]
    dismissed = 0
    for sel in (selectors or default_selectors):
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                dismissed += 1
                page.wait_for_timeout(400)
        except Exception:
            pass
    return dismissed


# ------------------------------------------------------------------
# データ取得
# ------------------------------------------------------------------

def get_text(page, selector: str, timeout: int = 10_000) -> str:
    """selector に一致する最初の要素のテキストを返す。見つからなければ空文字。"""
    try:
        page.wait_for_selector(selector, timeout=timeout)
        el = page.query_selector(selector)
        return el.inner_text().strip() if el else ""
    except Exception:
        return ""


def get_texts(page, selector: str, limit: int = 0) -> list[str]:
    """selector に一致する要素のテキストをリストで返す。limit で最大件数を指定できる。"""
    elements = page.query_selector_all(selector)
    if limit:
        elements = elements[:limit]
    return [el.inner_text().strip() for el in elements]


def get_attribute(page, selector: str, attr: str, timeout: int = 10_000) -> str:
    """selector に一致する最初の要素の属性値を返す。見つからなければ空文字。"""
    try:
        page.wait_for_selector(selector, timeout=timeout)
        el = page.query_selector(selector)
        return (el.get_attribute(attr) or "") if el else ""
    except Exception:
        return ""


def get_table(page, selector: str = "table") -> list[dict]:
    """HTML テーブルを辞書リストとして返す。ヘッダー行をキーに使う。

    複数テーブルが一致する場合は最初のテーブルを対象にする。
    ヘッダーが空のセルは "col_N" として扱う。
    """
    return page.evaluate(
        """(selector) => {
            const table = document.querySelector(selector);
            if (!table) return [];
            const rows = Array.from(table.querySelectorAll("tr"));
            if (rows.length === 0) return [];
            const headers = Array.from(rows[0].querySelectorAll("th, td"))
                .map((cell, i) => cell.innerText.trim() || `col_${i}`);
            return rows.slice(1).map(row => {
                const cells = Array.from(row.querySelectorAll("td, th"));
                const obj = {};
                headers.forEach((h, i) => {
                    obj[h] = cells[i] ? cells[i].innerText.trim() : "";
                });
                return obj;
            });
        }""",
        selector,
    ) or []


def get_structured_list(page, item_selector: str, fields: dict[str, str],
                         limit: int = 0) -> list[dict]:
    """繰り返し要素から構造化データを抽出する。

    fields のキーが出力のキー、値がサブセレクター。
    属性を取得したい場合は "サブセレクター@属性名" 形式で指定する。
    アイテム自身の属性は "@属性名" のみでよい。

    使用例（ニュース一覧の最新5件）:
        items = get_structured_list(page, "article.news-card", {
            "title":   "h2",
            "date":    "time",
            "url":     "a@href",
            "summary": "p.summary",
        }, limit=5)

    使用例（天気予報グリッドから特定地域を抽出）:
        forecasts = get_structured_list(page, ".forecast-row", {
            "region": ".region-name",
            "temp":   ".temperature",
            "sky":    ".condition",
            "id":     "@data-region-id",   # アイテム自身の属性
        })
        tokyo = next((r for r in forecasts if r["region"] == "東京"), None)
    """
    items = page.query_selector_all(item_selector)
    if limit:
        items = items[:limit]

    result = []
    for item in items:
        row = {}
        for key, spec in fields.items():
            if "@" in spec:
                child_sel, attr = spec.rsplit("@", 1)
                child_sel = child_sel.strip()
                el = item.query_selector(child_sel) if child_sel else item
                row[key] = (el.get_attribute(attr) or "") if el else ""
            else:
                el = item.query_selector(spec)
                row[key] = el.inner_text().strip() if el else ""
        result.append(row)
    return result


def get_links(page, selector: str = "a") -> list[str]:
    """selector に一致するすべての要素の href をリストで返す。空・#・javascript: は除外する。"""
    hrefs = []
    for el in page.query_selector_all(selector):
        href = el.get_attribute("href") or ""
        if href and href != "#" and not href.startswith("javascript:"):
            hrefs.append(href)
    return hrefs


# ------------------------------------------------------------------
# 保存
# ------------------------------------------------------------------

def save_csv(data: list[dict], filename: str) -> Path:
    """辞書リストを CSV として Downloads フォルダに保存する。保存先パスを返す。"""
    path = _downloads_dir() / filename
    if not data:
        print(f"[chrome_utils] データが空のため保存をスキップしました: {filename}")
        return path
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
    print(f"保存しました: {path}")
    return path


def save_json(data, filename: str) -> Path:
    """dict または list を JSON として Downloads フォルダに保存する。保存先パスを返す。"""
    path = _downloads_dir() / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"保存しました: {path}")
    return path


def save_text(text: str, filename: str) -> Path:
    """文字列をテキストファイルとして Downloads フォルダに保存する。保存先パスを返す。"""
    path = _downloads_dir() / filename
    path.write_text(text, encoding="utf-8")
    print(f"保存しました: {path}")
    return path


def save_page_html(page, filename: str) -> Path:
    """現在のページの HTML ソースを Downloads フォルダに保存する。保存先パスを返す。"""
    path = _downloads_dir() / filename
    path.write_text(page.content(), encoding="utf-8")
    print(f"保存しました: {path}")
    return path


def save_page_text(page, filename: str) -> Path:
    """現在のページの表示テキスト（body の innerText）を Downloads フォルダに保存する。"""
    return save_text(page.inner_text("body"), filename)


def expect_and_save_download(page, trigger_selector: str, filename: str) -> Path:
    """trigger_selector をクリックして発生するダウンロードを filename で保存する。保存先パスを返す。

    download.py で繰り返されていた with page.expect_download() パターンを統一する。
    """
    path = _downloads_dir() / filename
    if path.exists():
        path.unlink()
    with page.expect_download() as dl:
        page.click(trigger_selector)
    dl.value.save_as(str(path))
    print(f"保存しました: {path}")
    return path


# ------------------------------------------------------------------
# キャプチャ
# ------------------------------------------------------------------

def screenshot(page, filename: str, full_page: bool = True) -> Path:
    """現在のページのスクリーンショットを Downloads フォルダに保存する。保存先パスを返す。

    full_page=True（デフォルト）でスクロール全体を撮影する。
    ※ common.save_screenshot() はデバッグ用（tmp/dryrun/ 保存）。こちらはユーザー向け。
    """
    path = _downloads_dir() / filename
    page.screenshot(path=str(path), full_page=full_page)
    print(f"保存しました: {path}")
    return path


def save_pdf(page, filename: str) -> Path:
    """現在のページを PDF として Downloads フォルダに保存する。保存先パスを返す。

    Playwright の制約により headless モードでのみ動作する。
    get_chrome_context(p, headless=True) で起動したコンテキストで使うこと。
    """
    path = _downloads_dir() / filename
    try:
        page.pdf(path=str(path))
    except Exception as e:
        raise RuntimeError(
            f"PDF 生成に失敗しました（headless=True が必要です）: {e}"
        ) from e
    print(f"保存しました: {path}")
    return path
