from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src import config

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | pid=%(process)d | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
MAX_LOG_BYTES = 1_048_576
BACKUP_COUNT = 3

_HANDLER_MARKER = "_desktop_automation_handler"
_configured = False


def _mark_handler(handler: logging.Handler) -> logging.Handler:
    setattr(handler, _HANDLER_MARKER, True)
    return handler


def _remove_existing_handlers(root: logging.Logger) -> None:
    for handler in list(root.handlers):
        if getattr(handler, _HANDLER_MARKER, False):
            root.removeHandler(handler)
            handler.close()


def _build_console_handler(level: int) -> logging.Handler:
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    return _mark_handler(console)


def _build_file_handler(level: int, log_file: Path) -> logging.Handler:
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    return _mark_handler(file_handler)


def setup_logging(level: str | None = None, *, force: bool = False) -> None:
    """Initialize console + rotating file logging. Safe to call multiple times."""
    global _configured
    if _configured and not force:
        return

    log_level = getattr(logging, (level or config.LOG_LEVEL).upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(log_level)

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
        except Exception:
            pass

    _remove_existing_handlers(root)

    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = config.LOGS_DIR / "automation.log"

    root.addHandler(_build_console_handler(log_level))
    root.addHandler(_build_file_handler(log_level, log_file))

    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
