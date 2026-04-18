from __future__ import annotations

import re
import time

import psutil

from src import config
from src.automation.control import execution_gate
from src.automation.desktop import get_bot, get_cursor_position, move_cursor, wait_ms
from src.core.logger import get_logger

logger = get_logger(__name__)
_PYWINAUTO_BACKENDS = ("uia", "win32")
_NON_NOTEPAD_HOST_PROCESSES = {
    "code.exe",
    "windowsterminal.exe",
    "powershell.exe",
    "cmd.exe",
    "conhost.exe",
}

try:
    from pywinauto import Desktop
except Exception as exc:                                                  
    Desktop = None
    _PYWINAUTO_IMPORT_ERROR = exc
else:
    _PYWINAUTO_IMPORT_ERROR = None


def _timeout_ms(timeout: int | float | None) -> int:
    seconds = config.WINDOW_TIMEOUT if timeout is None else timeout
    return max(int(seconds * 1000), 250)


def _title_re(title_contains: str | tuple[str, ...]) -> str:
    if isinstance(title_contains, str):
        return f".*{re.escape(title_contains)}.*"
    return f".*({'|'.join(re.escape(t) for t in title_contains)}).*"


def _window_label(window) -> str:
    if hasattr(window, "window_text"):
        try:
            return window.window_text()
        except Exception:
            pass

    title = getattr(window, "title", None)
    if isinstance(title, str) and title:
        return title

    return "<unknown>"


def _window_object(window):
    if hasattr(window, "wrapper_object"):
        try:
            return window.wrapper_object()
        except Exception:
            return window
    return window


def _is_terminal_notification_window(title: str, process_name: str) -> bool:
    normalized_title = title.lower()

    if "command completed with exit code" in normalized_title:
        return True

    if "terminal output:" in normalized_title:
        return True

    if "terminal" in normalized_title and "notification" in normalized_title:
        return True

    if process_name in _NON_NOTEPAD_HOST_PROCESSES and "terminal" in normalized_title:
        return True

    return False


def _is_minimized(window) -> bool:
    for attr_name in ("is_minimized", "isMinimized"):
        attr = getattr(window, attr_name, None)
        if callable(attr):
            try:
                return bool(attr())
            except Exception:
                continue
        if attr is not None:
            return bool(attr)
    return False


def _find_window_with_botcity(title_contains: str | tuple[str, ...], timeout_ms: int):
    bot = get_bot()
    selector = {"title_re": _title_re(title_contains)}
    last_error = None

    for backend in _botcity_backends():
        try:
            bot.connect_to_app(backend=backend, timeout=timeout_ms, **selector)
            window = bot.find_app_window(waiting_time=timeout_ms, **selector)
            if window is not None:
                return window
        except Exception as exc:                                               
            last_error = exc

    raise LookupError(
        f"BotCity could not resolve window '{title_contains}': {last_error}"
    ) from last_error


def _find_window_with_pywinauto(title_contains: str | tuple[str, ...], timeout_ms: int):
    if Desktop is None:
        raise LookupError(f"pywinauto is unavailable: {_PYWINAUTO_IMPORT_ERROR}")

    title_re = _title_re(title_contains)
    timeout_seconds = timeout_ms / 1000
    last_error = None

    raw_tokens = (
        (title_contains.lower(),)
        if isinstance(title_contains, str)
        else tuple(token.lower() for token in title_contains)
    )
    searching_notepad_window = any(
        token in {"notepad", "المفكرة", "untitled"}
        for token in raw_tokens
    )

    def _process_name_for_window(window) -> str:
        try:
            pid = int(window.process_id())
            return psutil.Process(pid).name().lower()
        except Exception:
            return ""

    def _class_name_for_window(window) -> str:
        try:
            return str(window.class_name() or "").lower()
        except Exception:
            return ""

    def _choose_candidate(candidates):
        if not candidates:
            return None

        best_candidate = None
        best_score = -10_000

        for candidate in candidates:
            window = _window_object(candidate)
            title = _window_label(window).lower()
            class_name = _class_name_for_window(window)
            process_name = _process_name_for_window(window)

            if _is_terminal_notification_window(title, process_name):
                continue

            if (
                searching_notepad_window
                and process_name in _NON_NOTEPAD_HOST_PROCESSES
                and class_name != "notepad"
            ):
                                                                                                               
                continue

                                                                                       
            if "hook window class" in class_name:
                continue

            try:
                visible = bool(window.is_visible()) if hasattr(window, "is_visible") else True
            except Exception:
                visible = True

            score = 0
            if visible:
                score += 5
            if not _is_minimized(window):
                score += 3

            if process_name == "notepad.exe":
                score += 50

            if class_name == "notepad":
                score += 40
            elif class_name in {"#32770", "cabinetwclass"}:
                score += 20
            elif class_name.endswith("popupwindow"):
                score -= 30

            for token in raw_tokens:
                if token and token in title:
                    score += 2 if token == "untitled" else 12

            if "notepad" in title or "المفكرة" in title:
                score += 25

            if score > best_score:
                best_score = score
                best_candidate = candidate

        return best_candidate

    for pywinauto_backend in _PYWINAUTO_BACKENDS:
        deadline = time.monotonic() + timeout_seconds
        desktop = Desktop(backend=pywinauto_backend)
        try:
            while time.monotonic() < deadline:
                try:
                    window = desktop.window(title_re=title_re)
                    window.wait("exists enabled visible ready", timeout=0.25)
                    return window
                except Exception as exc:                                               
                    last_error = exc

                try:
                    candidates = desktop.windows(
                        title_re=title_re,
                        top_level_only=True,
                        visible_only=False,
                        enabled_only=False,
                    )
                    selected = _choose_candidate(candidates)
                    if selected is not None:
                        return selected
                except Exception as exc:                                               
                    last_error = exc

                time.sleep(0.1)
        except Exception as exc:                                               
            last_error = exc

    raise LookupError(
        f"pywinauto could not resolve window '{title_contains}': {last_error}"
    ) from last_error


def _find_window(title_contains: str | tuple[str, ...], timeout_ms: int):
    try:
        return _find_window_with_pywinauto(title_contains, timeout_ms)
    except LookupError as pywinauto_error:
        logger.debug(
            "pywinauto window lookup failed for '%s': %s",
            title_contains,
            pywinauto_error,
        )

    try:
        return _find_window_with_botcity(title_contains, timeout_ms)
    except LookupError as botcity_error:
        logger.debug(
            "BotCity window lookup failed for '%s': %s",
            title_contains,
            botcity_error,
        )
        raise


def _botcity_backends():
    try:
        from botcity.core import Backend
    except Exception as exc:
        raise LookupError(f"BotCity backend import failed: {exc}") from exc

    return (
        Backend.UIA,
        Backend.WIN_32,
    )


def wait_for_window(title_contains: str | tuple[str, ...], timeout: int | float | None = None) -> bool:
    if config.DRY_RUN:
        logger.info("[DRY_RUN] wait_for_window('%s') -> True", title_contains)
        return True

    timeout_ms = _timeout_ms(timeout)
    execution_gate.wait_if_paused()
    try:
        window = _find_window(title_contains, timeout_ms)
    except LookupError:
        logger.warning("Window '%s' not found within %dms", title_contains, timeout_ms)
        return False

    logger.debug(
        "Found window matching '%s': %s",
        title_contains,
        _window_label(window),
    )
    return True


def activate_window(title_contains: str | tuple[str, ...], timeout: int | float | None = None) -> bool:
    if config.DRY_RUN:
        logger.info("[DRY_RUN] activate_window('%s') -> True", title_contains)
        return True

    try:
        execution_gate.wait_if_paused()
        window = _window_object(_find_window(title_contains, _timeout_ms(timeout)))
    except LookupError as exc:
        logger.warning("No window found matching '%s': %s", title_contains, exc)
        return False

    try:
        if _is_minimized(window):
            window.restore()
            wait_ms(150)

        import contextlib
        from pywinauto import mouse
        
        @contextlib.contextmanager
        def _prevent_mouse_jump():
            original_move = mouse.move
            mouse.move = lambda *args, **kwargs: None
            try:
                yield
            finally:
                mouse.move = original_move

        if hasattr(window, "set_focus"):
            original_pos = get_cursor_position(allow_bot_fallback=False)
            with _prevent_mouse_jump():
                window.set_focus()
            if original_pos is not None:
                move_cursor(*original_pos)
        elif hasattr(window, "activate"):
            original_pos = get_cursor_position(allow_bot_fallback=False)
            with _prevent_mouse_jump():
                window.activate()
            if original_pos is not None:
                move_cursor(*original_pos)
        else:
            raise AttributeError("window does not support focus activation")

        logger.debug("Activated window: %s", _window_label(window))
        return True
    except Exception as exc:
        logger.warning("Failed to activate window '%s': %s", title_contains, exc)
        return False


def close_window(title_contains: str | tuple[str, ...], timeout: int | float | None = None) -> bool:
    if config.DRY_RUN:
        logger.info("[DRY_RUN] close_window('%s') -> True", title_contains)
        return True

    try:
        execution_gate.wait_if_paused()
        window = _window_object(_find_window(title_contains, _timeout_ms(timeout)))
    except LookupError:
        return True

    try:
        window.close()
        logger.debug("Closed window: %s", _window_label(window))
        return True
    except Exception as exc:
        logger.warning("Failed to close window '%s': %s", title_contains, exc)
        return False


def is_window_open(title_contains: str | tuple[str, ...]) -> bool:
    if config.DRY_RUN:
        return False

    execution_gate.wait_if_paused()
    try:
        _find_window(title_contains, 250)
    except LookupError:
        return False

    return True
