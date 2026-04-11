import sys
import time

# ---------------------------------------------------------------------------
# Workaround: python-xlib 0.33 ships a randr extension that calls
# Display.extension_add_subevent() and Display.extension_add_error(),
# but neither method was included in the 0.33 release (fixed on upstream
# master, unreleased).  Monkey-patch them before any X11-dependent import
# (pyautogui/mouseinfo) triggers Display.__init__ → randr.init().
# See: https://github.com/python-xlib/python-xlib/issues/262
# ---------------------------------------------------------------------------
if sys.platform == "linux":
    from Xlib.display import Display as _XDisplay

    if not hasattr(_XDisplay, "extension_add_subevent"):

        def _extension_add_subevent(self, code, subcode, evt, name=None):
            newevt = type(evt.__name__, evt.__bases__, evt.__dict__.copy())
            newevt._code = code
            self.display.add_extension_event(code, newevt, subcode)
            if name is None:
                name = evt.__name__
            setattr(self.extension_event, name, (code, subcode))

        _XDisplay.extension_add_subevent = _extension_add_subevent

    if not hasattr(_XDisplay, "extension_add_error"):

        def _extension_add_error(self, code, err):
            self.display.add_extension_error(code, err)

        _XDisplay.extension_add_error = _extension_add_error

try:
    import pyautogui
except Exception as exc:  # pragma: no cover - exercised in Linux DRY_RUN environments
    pyautogui = None
    _PYAUTOGUI_IMPORT_ERROR = exc
else:
    _PYAUTOGUI_IMPORT_ERROR = None

from src import config
from src.core.logger import get_logger

logger = get_logger(__name__)

# Safety: prevent pyautogui from throwing if mouse hits screen edge
if pyautogui is not None:
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05


def _require_pyautogui():
    if pyautogui is None:
        raise RuntimeError(f"pyautogui is unavailable: {_PYAUTOGUI_IMPORT_ERROR}")
    return pyautogui


def double_click(x: int, y: int) -> None:
    """Double-click at screen coordinates."""
    if config.DRY_RUN:
        logger.info("[DRY_RUN] double_click(%d, %d)", x, y)
        return
    gui = _require_pyautogui()
    logger.debug("Double-clicking at (%d, %d)", x, y)
    gui.doubleClick(x, y)


def click(x: int, y: int) -> None:
    """Single click at screen coordinates."""
    if config.DRY_RUN:
        logger.info("[DRY_RUN] click(%d, %d)", x, y)
        return
    gui = _require_pyautogui()
    logger.debug("Clicking at (%d, %d)", x, y)
    gui.click(x, y)


def type_text(text: str, interval: float | None = None) -> None:
    """Type text with realistic keystroke interval.

    Uses pyautogui.write for ASCII text, falls back to
    pyperclip + Ctrl+V for unicode content.
    """
    if config.DRY_RUN:
        logger.info("[DRY_RUN] type_text(%d chars)", len(text))
        return

    interval = interval or config.TYPING_INTERVAL
    gui = _require_pyautogui()

    try:
        gui.write(text, interval=interval)
    except Exception:
        # Fallback for non-ASCII or special chars: use clipboard paste
        import pyperclip
        pyperclip.copy(text)
        gui.hotkey("ctrl", "v")
        time.sleep(0.2)


def hotkey(*keys: str) -> None:
    """Press a keyboard shortcut."""
    if config.DRY_RUN:
        logger.info("[DRY_RUN] hotkey(%s)", "+".join(keys))
        return
    gui = _require_pyautogui()
    logger.debug("Hotkey: %s", "+".join(keys))
    gui.hotkey(*keys)


def press(key: str) -> None:
    """Press a single key."""
    if config.DRY_RUN:
        logger.info("[DRY_RUN] press(%s)", key)
        return
    gui = _require_pyautogui()
    gui.press(key)


def show_desktop() -> None:
    """Navigate to the desktop so icons are visible before grounding.

    On Windows, ``Win+M`` is deterministic because it minimizes all windows
    without toggling them back on the next call the way ``Win+D`` can.
    """
    if config.DRY_RUN:
        logger.info("[DRY_RUN] show_desktop()")
        return

    gui = _require_pyautogui()
    if sys.platform == "win32":
        gui.hotkey("win", "m")
    else:
        gui.hotkey("win", "d")

    time.sleep(config.SETTLE_DELAY)
