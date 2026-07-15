try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        raise ImportError(
            "tomllib (Python 3.11+) or tomli package required. Run: pip install tomli"
        )
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
_config_path = _root / "config.toml"

if not _config_path.exists():
    raise FileNotFoundError(
        f"config.toml not found at {_config_path}.\n"
        "Copy config/config.toml.template to config.toml and fill in your values."
    )

with open(_config_path, "rb") as _f:
    _cfg = tomllib.load(_f)

OAUTH_CLIENT_ID       = _cfg["oauth"]["client_id"]
OAUTH_CLIENT_SECRET   = _cfg["oauth"]["client_secret"]
# catalog_folder_id / catalog_url were previously named library_folder_id / library_url
_drive = _cfg["drive"]
CATALOG_FOLDER_ID = (_drive.get("catalog_folder_id") or _drive.get("library_folder_id", "")).strip()
CATALOG_URL       = (_drive.get("catalog_url")       or _drive.get("library_url", "")).strip()
CATALOG_FILE_ID   = (_drive.get("catalog_file_id")   or _drive.get("library_catalog_file_id", "")).strip()
# [company] is not declared in agent-ui's own config.toml.template — it's an
# optional overlay a wrapping project (e.g. agent-deck) supplies in its own
# config.toml. Defaults to empty so standalone agent-ui installs don't crash.
_company = _cfg.get("company", {})
COMPANY_DOMAIN        = _company.get("domain", "").strip()
PORTAL_URL            = _company.get("portal_url", "").strip()
SALESFORCE_URL        = _company.get("salesforce_url", "").strip()
PPTX_TEMPLATE_NAME    = _cfg["template"]["name"]
PPTX_TEMPLATE_URL     = _cfg["template"]["url"]
USER_EMAIL            = _cfg.get("user", {}).get("email", "").strip()
CHAT_WEBHOOK_URL      = _cfg.get("notifications", {}).get("chat_webhook_url", "").strip()
CONFIG_PATH           = _config_path
