import time

from src import config
from src.core.logger import get_logger

logger = get_logger(__name__)

try:
    import pywinctl
except Exception as exc:                                                              
    pywinctl = None
    _PYWINCTL_IMPORT_ERROR = exc
else:
    _PYWINCTL_IMPORT_ERROR = None


def _get_windows(title_contains: str) -> list:
    if pywinctl is None:
        raise RuntimeError(f"pywinctl is unavailable: {_PYWINCTL_IMPORT_ERROR}")

    return pywinctl.getWindowsWithTitle(
        title_contains,
        condition=pywinctl.Re.CONTAINS,
        flags=pywinctl.Re.IGNORECASE,
    )


def _pick_best_window(windows: list, title_contains: str):
    if not windows:
        return None

    query = title_contains.lower()

    def score(win) -> tuple[int, int, int, int]:
        title = getattr(win, "title", "") or ""
        lowered = title.lower()
        exact = int(lowered == query)
        starts = int(lowered.startswith(query))
        active = int(bool(getattr(win, "isActive", False)))
        visible = int(bool(getattr(win, "isVisible", True)))
        return (exact, starts, active, visible)

    return max(windows, key=score)


def wait_for_window(title_contains: str, timeout: int | None = None) -> bool:
    if config.DRY_RUN:
        logger.info("[DRY_RUN] wait_for_window('%s') → True", title_contains)
        return True

    timeout = timeout or config.WINDOW_TIMEOUT
    deadline = time.time() + timeout

    while time.time() < deadline:
        windows = _get_windows(title_contains)
        if windows:
            logger.debug(
                "Found window matching '%s': %s",
                title_contains,
                _pick_best_window(windows, title_contains).title,
            )
            return True
        time.sleep(0.3)

    logger.warning("Window '%s' not found within %ds", title_contains, timeout)
    return False


def activate_window(title_contains: str) -> bool:
    if config.DRY_RUN:
        logger.info("[DRY_RUN] activate_window('%s') → True", title_contains)
        return True

    win = _pick_best_window(_get_windows(title_contains), title_contains)
    if not win:
        logger.warning("No window found matching '%s'", title_contains)
        return False

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

    win = _pick_best_window(_get_windows(title_contains), title_contains)
    if not win:
        return True                  

    try:
        win.close()
        logger.debug("Closed window: %s", win.title)
        return True
    except Exception as exc:
        logger.warning("Failed to close window '%s': %s", title_contains, exc)
        return False


def is_window_open(title_contains: str) -> bool:
    if config.DRY_RUN:
        return False

    windows = _get_windows(title_contains)
    return len(windows) > 0
