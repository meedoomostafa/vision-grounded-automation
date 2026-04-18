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
    "f": 0x46,
    "f4": 0x73,
    "m": 0x4D,
    "n": 0x4E,
    "r": 0x52,
    "s": 0x53,
    "v": 0x56,
    "y": 0x59,
}

if TYPE_CHECKING:
    from botcity.core import DesktopBot

_bot: Any | None = None


class _CursorPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


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


def get_cursor_position(*, allow_bot_fallback: bool = True) -> tuple[int, int] | None:
    try:
        if sys.platform == "win32" and hasattr(ctypes, "windll"):
            point = _CursorPoint()
            if ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
                return (int(point.x), int(point.y))
    except Exception as exc:
        logger.debug("Unable to read cursor position via WinAPI: %s", exc)

    if not allow_bot_fallback:
        return None

    try:
        bot = get_bot()
        return int(bot.get_last_x()), int(bot.get_last_y())
    except Exception as exc:
        logger.debug("Unable to read cursor position from BotCity: %s", exc)
        return None


def move_cursor(x: int, y: int) -> None:
    if config.DRY_RUN:
        logger.info("[DRY_RUN] move_cursor(%d, %d)", x, y)
        return

    try:
        if sys.platform == "win32" and hasattr(ctypes, "windll"):
            if ctypes.windll.user32.SetCursorPos(int(x), int(y)):
                return
    except Exception as exc:
        logger.debug("Unable to move cursor via WinAPI: %s", exc)

    get_bot().mouse_move(int(x), int(y))


def _capture_cursor_position(_bot: DesktopBot) -> tuple[int, int] | None:
    return get_cursor_position(allow_bot_fallback=False)


def _restore_cursor_position(
    bot: DesktopBot,
    cursor_position: tuple[int, int] | None,
    *,
    reason: str,
) -> None:
    if cursor_position is None:
        return

    try:
        restore_x, restore_y = cursor_position
        move_cursor(restore_x, restore_y)
        logger.debug("Restored cursor to (%d, %d) after %s", restore_x, restore_y, reason)
    except Exception as exc:
        logger.warning("Failed to restore cursor position after %s: %s", reason, exc)


def double_click(x: int, y: int, *, restore_cursor: bool = False) -> None:
    if config.DRY_RUN:
        logger.info("[DRY_RUN] double_click(%d, %d)", x, y)
        return

    execution_gate.wait_if_paused()
    bot = get_bot()
    original_cursor = _capture_cursor_position(bot) if restore_cursor else None
    logger.debug("Double-clicking at (%d, %d)", x, y)
    try:
        bot.click_at(x, y)
        bot.wait(80)
        bot.click_at(x, y)
    finally:
        if restore_cursor:
            _restore_cursor_position(
                bot,
                original_cursor,
                reason=f"double_click({x}, {y})",
            )


def click(x: int, y: int, *, restore_cursor: bool = False) -> None:
    if config.DRY_RUN:
        logger.info("[DRY_RUN] click(%d, %d)", x, y)
        return

    execution_gate.wait_if_paused()
    bot = get_bot()
    original_cursor = _capture_cursor_position(bot) if restore_cursor else None
    logger.debug("Clicking at (%d, %d)", x, y)
    try:
        bot.click_at(x, y)
    finally:
        if restore_cursor:
            _restore_cursor_position(
                bot,
                original_cursor,
                reason=f"click({x}, {y})",
            )


def type_text(text: str, interval: float | None = None) -> None:
    if config.DRY_RUN:
        logger.info("[DRY_RUN] type_text(%d chars)", len(text))
        return

    execution_gate.wait_if_paused()
    import pyperclip
    pyperclip.copy(text)
    wait_ms(50)
    _send_system_hotkey("ctrl", "v")


def hotkey(*keys: str) -> None:
    if config.DRY_RUN:
        logger.info("[DRY_RUN] hotkey(%s)", "+".join(keys))
        return

    execution_gate.wait_if_paused()
    logger.debug("Hotkey: %s", "+".join(keys))
    _send_system_hotkey(*keys)


def press(key: str) -> None:
    if config.DRY_RUN:
        logger.info("[DRY_RUN] press(%s)", key)
        return

    execution_gate.wait_if_paused()
    _send_system_hotkey(key)

def show_desktop() -> None:
    if config.DRY_RUN:
        logger.info("[DRY_RUN] show_desktop()")
        return

    combo = ("win", "m") if sys.platform == "win32" else ("win", "d")
    hotkey(*combo)
    wait_ms(int(config.SETTLE_DELAY * 1000))


def list_desktop_icons() -> list[tuple[str, tuple[int, int, int, int]]]:
    if config.DRY_RUN:
        return []

    try:
        from pywinauto import Desktop

        progman = Desktop(backend="win32").window(class_name="Progman")
        listview = progman.child_window(class_name="SysListView32").wrapper_object()

        icons: list[tuple[str, tuple[int, int, int, int]]] = []
        item_count = int(listview.item_count())
        for index in range(item_count):
            item = listview.get_item(index)
            name = str(item.text() or "").strip()
            rect = item.rectangle()
            icons.append((name, (rect.left, rect.top, rect.right, rect.bottom)))

        return icons
    except Exception as exc:
        logger.debug("Desktop icon enumeration unavailable: %s", exc)
        return []


def desktop_icon_name_at(x: int, y: int) -> str | None:
    for icon_name, (left, top, right, bottom) in list_desktop_icons():
        if left <= x <= right and top <= y <= bottom:
            return icon_name or None
    return None
