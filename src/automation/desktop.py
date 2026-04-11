import time

import pyautogui

from src import config
from src.core.logger import get_logger

logger = get_logger(__name__)

# Safety: prevent pyautogui from throwing if mouse hits screen edge
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05


def double_click(x: int, y: int) -> None:
    """Double-click at screen coordinates."""
    if config.DRY_RUN:
        logger.info("[DRY_RUN] double_click(%d, %d)", x, y)
        return
    logger.debug("Double-clicking at (%d, %d)", x, y)
    pyautogui.doubleClick(x, y)


def click(x: int, y: int) -> None:
    """Single click at screen coordinates."""
    if config.DRY_RUN:
        logger.info("[DRY_RUN] click(%d, %d)", x, y)
        return
    logger.debug("Clicking at (%d, %d)", x, y)
    pyautogui.click(x, y)


def type_text(text: str, interval: float | None = None) -> None:
    """Type text with realistic keystroke interval.

    Uses pyautogui.write for ASCII text, falls back to
    pyperclip + Ctrl+V for unicode content.
    """
    if config.DRY_RUN:
        logger.info("[DRY_RUN] type_text(%d chars)", len(text))
        return

    interval = interval or config.TYPING_INTERVAL

    try:
        pyautogui.write(text, interval=interval)
    except Exception:
        # Fallback for non-ASCII or special chars: use clipboard paste
        import pyperclip
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.2)


def hotkey(*keys: str) -> None:
    """Press a keyboard shortcut."""
    if config.DRY_RUN:
        logger.info("[DRY_RUN] hotkey(%s)", "+".join(keys))
        return
    logger.debug("Hotkey: %s", "+".join(keys))
    pyautogui.hotkey(*keys)


def press(key: str) -> None:
    """Press a single key."""
    if config.DRY_RUN:
        logger.info("[DRY_RUN] press(%s)", key)
        return
    pyautogui.press(key)
