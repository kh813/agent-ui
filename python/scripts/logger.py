"""Centralized file logger with size-based rotation.

Log file: <project-root>/tmp/logs/agent-ui.log
Rotation: 10 MB per file, 1 backup (total max ~20 MB).
"""
import logging
import logging.handlers
import platform
import sys
from pathlib import Path

_LOG_DIR  = Path(__file__).resolve().parents[2] / "tmp" / "logs"
_LOG_FILE = _LOG_DIR / "agent-ui.log"
_MAX_BYTES    = 10 * 1024 * 1024  # 10 MB
_BACKUP_COUNT = 1                  # agent-ui.log + agent-ui.log.1


def get_logger(name: str) -> logging.Logger:
    """Return a named logger that writes to the rotating log file."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"agent_ui.{name}")
    if not logger.handlers:
        handler = logging.handlers.RotatingFileHandler(
            str(_LOG_FILE), maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    return logger


def log_startup(logger: logging.Logger) -> None:
    """Log OS and Python version at script entry."""
    logger.info("--- startup os=%s python=%s ---",
                platform.system(), sys.version.split()[0])
