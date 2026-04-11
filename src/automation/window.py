import time

import pywinctl

from src import config
from src.core.logger import get_logger

logger = get_logger(__name__)


def wait_for_window(title_contains: str, timeout: int | None = None) -> bool:
    if config.DRY_RUN:
        logger.info("[DRY_RUN] wait_for_window('%s') → True", title_contains)
        return True

    timeout = timeout or config.WINDOW_TIMEOUT
    deadline = time.time() + timeout
    search = title_contains.lower()

    while time.time() < deadline:
        windows = pywinctl.getWindowsWithTitle(title_contains)
        if windows:
            logger.debug("Found window matching '%s': %s", title_contains, windows[0].title)
            return True
        time.sleep(0.3)

    logger.warning("Window '%s' not found within %ds", title_contains, timeout)
    return False


def activate_window(title_contains: str) -> bool:
    if config.DRY_RUN:
        logger.info("[DRY_RUN] activate_window('%s') → True", title_contains)
        return True

    windows = pywinctl.getWindowsWithTitle(title_contains)
    if not windows:
        logger.warning("No window found matching '%s'", title_contains)
        return False

    win = windows[0]
    try:
        if hasattr(win, "isMinimized") and win.isMinimized:
            win.restore()
            time.sleep(0.3)
        win.activate()
        logger.debug("Activated window: %s", win.title)
        return True
    except Exception as exc:
        logger.warning("Failed to activate window '%s': %s", title_contains, exc)
        return False


def close_window(title_contains: str) -> bool:
    if config.DRY_RUN:
        logger.info("[DRY_RUN] close_window('%s') → True", title_contains)
        return True

    windows = pywinctl.getWindowsWithTitle(title_contains)
    if not windows:
        return True                  

    try:
        windows[0].close()
        logger.debug("Closed window: %s", windows[0].title)
        return True
    except Exception as exc:
        logger.warning("Failed to close window '%s': %s", title_contains, exc)
        return False


def is_window_open(title_contains: str) -> bool:
    if config.DRY_RUN:
        return False

    windows = pywinctl.getWindowsWithTitle(title_contains)
    return len(windows) > 0
