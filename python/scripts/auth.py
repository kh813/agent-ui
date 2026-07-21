"""Shared OAuth helper: opens Chrome for the Google consent screen."""
import platform
import subprocess
import sys
import webbrowser

# Windows pipe (agy.exe's pty etc.) makes stdout fall back to CP932/CP1252,
# crashing outright (UnicodeEncodeError) on this file's Japanese text and
# em-dash. Confirmed for real: run_auth_flow's own print crashed, and then
# the caller's exception-handler print (which embeds that exception's own
# message) crashed a second time for the same reason.
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        pass

try:
    from scripts.logger import get_logger as _get_logger
except ImportError:
    import logging
    def _get_logger(name):
        return logging.getLogger(f"agent_ui.{name}")

_log = _get_logger("auth")


def run_auth_flow(flow, port=0, login_hint=None, timeout_seconds=None):
    """Run OAuth local server and open Chrome for the consent screen.

    timeout_seconds: passed through to run_local_server. Set this when the
    caller must never block forever (e.g. skills_catalog.py's launch-time
    sync, which runs inside the non-interactive preflight — if the user
    closes the browser without authorizing, the local server would
    otherwise wait for a callback that never comes and hang the whole
    session start). On timeout run_local_server raises, which callers
    treat as "skipped this launch, retry next time".
    """
    _log.info("OAuth flow starting login_hint=%s", login_hint or "(none)")
    print("  Chrome が開きます。会社のGoogleアカウントでログインしてください。")
    print("  Chrome will open — log in with your company Google account.")

    pf = platform.system()

    class _Chrome:
        def open(self, url, new=0, autoraise=True):
            try:
                if pf == "Darwin":
                    subprocess.Popen(["open", "-a", "Google Chrome", url])
                elif pf == "Windows":
                    # shell=True with bare URL causes cmd.exe to split on '&' in OAuth URLs.
                    # Use PowerShell Start-Process to pass the URL as a single argument.
                    subprocess.Popen(
                        ["powershell", "-NoProfile", "-Command",
                         f"Start-Process 'chrome' -ArgumentList '{url}'"],
                        shell=False,
                    )
                else:
                    subprocess.Popen(["google-chrome", url])
            except Exception:
                webbrowser.open(url)
            return True

    # Temporarily replace webbrowser.get so run_local_server always uses Chrome.
    # Passing a browser instance directly to run_local_server breaks on Python 3.9
    # because webbrowser.get() expects a string, not an instance.
    _orig_get = webbrowser.get
    webbrowser.get = lambda *_a, **_kw: _Chrome()
    kwargs = {"port": port, "open_browser": True}
    if login_hint:
        kwargs["login_hint"] = login_hint
    if timeout_seconds is not None:
        kwargs["timeout_seconds"] = timeout_seconds
    try:
        creds = flow.run_local_server(**kwargs)
        _log.info("OAuth flow completed successfully")
        return creds
    except Exception as e:
        _log.error("OAuth flow failed: %s", e, exc_info=True)
        raise
    finally:
        webbrowser.get = _orig_get
