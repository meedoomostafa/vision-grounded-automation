from __future__ import annotations

import ctypes
import sys
from typing import TYPE_CHECKING, Any

from src import config
from src.automation.control import execution_gate
from src.core.logger import get_logger

logger = get_logger(__name__)
_KEYEVENTF_KEYUP = 0x0002
_VK_BY_NAME = {
    "alt": 0xA4,
    "ctrl": 0xA2,
    "shift": 0xA0,
    "win": 0x5B,
    "enter": 0x0D,
    "esc": 0x1B,
    "a": 0x41,
    "c": 0x43,
    "d": 0x44,
    "f4": 0x73,
    "m": 0x4D,
    "n": 0x4E,
    "s": 0x53,
    "v": 0x56,
    "y": 0x59,
}

if TYPE_CHECKING:
    from botcity.core import DesktopBot

_bot: Any | None = None


def _desktop_bot_class():
    try:
        from botcity.core import DesktopBot
    except Exception as exc:  # pragma: no cover - depends on local GUI deps
        raise RuntimeError("BotCity DesktopBot is unavailable") from exc

    return DesktopBot


def get_bot() -> DesktopBot:
    global _bot
    if _bot is None:
        _bot = _desktop_bot_class()()
    return _bot


def _send_system_hotkey(*keys: str) -> None:
    normalized = [key.lower() for key in keys]
    vk_codes = [_VK_BY_NAME.get(key) for key in normalized]
    if any(vk is None for vk in vk_codes):
        raise ValueError(f"Unsupported system hotkey: {keys}")

    for vk_code in vk_codes:
        scan_code = ctypes.windll.user32.MapVirtualKeyA(vk_code, 0)
        ctypes.windll.user32.keybd_event(vk_code, scan_code, 0, 0)
    
    import time
    time.sleep(0.02)
    
    for vk_code in reversed(vk_codes):
        scan_code = ctypes.windll.user32.MapVirtualKeyA(vk_code, 0)
        ctypes.windll.user32.keybd_event(vk_code, scan_code, _KEYEVENTF_KEYUP, 0)


def wait_ms(milliseconds: int) -> None:
    if milliseconds <= 0:
        return
    execution_gate.wait_if_paused()
    get_bot().wait(milliseconds)


def double_click(x: int, y: int) -> None:
    """Double-click at screen coordinates using BotCity."""
    if config.DRY_RUN:
        logger.info("[DRY_RUN] double_click(%d, %d)", x, y)
        return

    execution_gate.wait_if_paused()
    bot = get_bot()
    logger.debug("Double-clicking at (%d, %d)", x, y)
    bot.click_at(x, y)
    bot.wait(80)
    bot.click_at(x, y)


def click(x: int, y: int) -> None:
    """Single click at screen coordinates using BotCity."""
    if config.DRY_RUN:
        logger.info("[DRY_RUN] click(%d, %d)", x, y)
        return

    execution_gate.wait_if_paused()
    logger.debug("Clicking at (%d, %d)", x, y)
    get_bot().click_at(x, y)


def type_text(text: str, interval: float | None = None) -> None:
    """Type text using clipboard paste to avoid keyboard layout issues."""
    if config.DRY_RUN:
        logger.info("[DRY_RUN] type_text(%d chars)", len(text))
        return

    execution_gate.wait_if_paused()
    import pyperclip
    pyperclip.copy(text)
    wait_ms(50)
    _send_system_hotkey("ctrl", "v")


def hotkey(*keys: str) -> None:
    """Press a keyboard shortcut using System Hotkeys."""
    if config.DRY_RUN:
        logger.info("[DRY_RUN] hotkey(%s)", "+".join(keys))
        return

    execution_gate.wait_if_paused()
    logger.debug("Hotkey: %s", "+".join(keys))
    _send_system_hotkey(*keys)


def press(key: str) -> None:
    """Press a single key using System Hotkeys."""
    if config.DRY_RUN:
        logger.info("[DRY_RUN] press(%s)", key)
        return

    execution_gate.wait_if_paused()
    _send_system_hotkey(key)

def show_desktop() -> None:
    """Navigate to the desktop so icons are visible before grounding."""
    if config.DRY_RUN:
        logger.info("[DRY_RUN] show_desktop()")
        return

    combo = ("win", "m") if sys.platform == "win32" else ("win", "d")
    hotkey(*combo)
    wait_ms(int(config.SETTLE_DELAY * 1000))
