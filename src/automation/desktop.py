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
    "alt": 0x12,
    "ctrl": 0x11,
    "d": 0x44,
    "m": 0x4D,
    "shift": 0x10,
    "win": 0x5B,
}

if TYPE_CHECKING:
    from botcity.core import DesktopBot

_bot: Any | None = None


def _desktop_bot_class():
    try:
        from botcity.core import DesktopBot
    except Exception as exc:                                                
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
        ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
    for vk_code in reversed(vk_codes):
        ctypes.windll.user32.keybd_event(vk_code, 0, _KEYEVENTF_KEYUP, 0)


def wait_ms(milliseconds: int) -> None:
    if milliseconds <= 0:
        return
    execution_gate.wait_if_paused()
    get_bot().wait(milliseconds)


def double_click(x: int, y: int) -> None:
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
    if config.DRY_RUN:
        logger.info("[DRY_RUN] click(%d, %d)", x, y)
        return

    execution_gate.wait_if_paused()
    logger.debug("Clicking at (%d, %d)", x, y)
    get_bot().click_at(x, y)


def type_text(text: str, interval: float | None = None) -> None:
    if config.DRY_RUN:
        logger.info("[DRY_RUN] type_text(%d chars)", len(text))
        return

    bot = get_bot()
    interval_ms = int((interval or config.TYPING_INTERVAL) * 1000)

    if text.isascii():
        chunk_size = 32
        for offset in range(0, len(text), chunk_size):
            execution_gate.wait_if_paused()
            bot.type_key(text[offset:offset + chunk_size], interval=interval_ms)
        return

    execution_gate.wait_if_paused()
    bot.paste(text)


def hotkey(*keys: str) -> None:
    if config.DRY_RUN:
        logger.info("[DRY_RUN] hotkey(%s)", "+".join(keys))
        return

    execution_gate.wait_if_paused()
    logger.debug("Hotkey: %s", "+".join(keys))
    if any(key.lower() == "win" for key in keys):
        _send_system_hotkey(*keys)
        return
    get_bot().type_keys(list(keys))


def press(key: str) -> None:
    if config.DRY_RUN:
        logger.info("[DRY_RUN] press(%s)", key)
        return

    execution_gate.wait_if_paused()
    get_bot().type_keys([key])


def show_desktop() -> None:
    if config.DRY_RUN:
        logger.info("[DRY_RUN] show_desktop()")
        return

    combo = ("win", "m") if sys.platform == "win32" else ("win", "d")
    hotkey(*combo)
    wait_ms(int(config.SETTLE_DELAY * 1000))
