from __future__ import annotations

import re
import os
import subprocess
import time
from pathlib import Path

from src import config
from src.automation.control import execution_gate
from src.automation.desktop import (
    get_cursor_position,
    hotkey,
    move_cursor,
    press,
    type_text,
    wait_ms,
)
from src.automation.window import (
    activate_window,
    close_window,
    is_window_open,
    wait_for_window,
)
from src.core.exceptions import WindowNotFoundError
from src.core.logger import get_logger

logger = get_logger(__name__)

TITLE_NOTEPAD = ("Notepad", "المفكرة", "Untitled")
TITLE_SAVE = ("Save", "حفظ")
TITLE_CONFIRM = ("Confirm", "تأكيد")
TITLE_RUN = ("Run", "تشغيل")


def _gate_checkpoint() -> None:
    execution_gate.wait_if_paused()


def _title_re(title_contains: str | tuple[str, ...]) -> str:
    if isinstance(title_contains, str):
        return f".*{re.escape(title_contains)}.*"
    return f".*({'|'.join(re.escape(t) for t in title_contains)}).*"


def _fill_save_path_with_pywinauto(absolute_path: str) -> bool:
    try:
        from pywinauto import Desktop
    except Exception as exc:
        logger.debug("pywinauto unavailable for save dialog fill: %s", exc)
        return False

    title_re = _title_re(TITLE_SAVE)
    last_error: Exception | None = None

    for backend in ("uia", "win32"):
        try:
            dialog = Desktop(backend=backend).window(title_re=title_re)
            dialog.wait("exists enabled visible ready", timeout=0.5)

            if backend == "uia":
                edits = dialog.descendants(control_type="Edit")
            else:
                edits = dialog.children(class_name="Edit")

            if not edits:
                continue

                                                                                          
            target = max(edits, key=lambda ctrl: ctrl.rectangle().top)
            target = target.wrapper_object() if hasattr(target, "wrapper_object") else target

            if hasattr(target, "set_focus"):
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

                original_pos = get_cursor_position(allow_bot_fallback=False)
                with _prevent_mouse_jump():
                    target.set_focus()
                if original_pos is not None:
                    move_cursor(*original_pos)

            if hasattr(target, "set_edit_text"):
                target.set_edit_text(absolute_path)
            elif hasattr(target, "type_keys"):
                target.type_keys("^a{BACKSPACE}")
                target.type_keys(absolute_path, with_spaces=True, set_foreground=True)
            else:
                continue

                logger.debug("Filled save path via pywinauto (%s backend)", backend)
                return True
        except Exception as exc:
            last_error = exc

    if last_error is not None:
        logger.debug("pywinauto save path fill failed: %s", last_error)
    return False


def _fill_save_path_with_keyboard(absolute_path: str) -> None:
    hotkey("ctrl", "a")
    wait_ms(80)
    type_text(absolute_path, interval=0.01)
    wait_ms(120)


def _submit_save_path(absolute_path: str) -> None:
    if not _fill_save_path_with_pywinauto(absolute_path):
        _fill_save_path_with_keyboard(absolute_path)

    press("enter")
    wait_ms(250)


def _submit_save_via_directory_navigation(file_path: Path) -> None:
    output_dir = str(file_path.parent.resolve())
    file_name = file_path.name

                                                                                 
    hotkey("alt", "d")
    wait_ms(120)
    type_text(output_dir, interval=0.01)
    wait_ms(120)
    press("enter")
    wait_ms(350)

    _fill_save_path_with_keyboard(file_name)
    press("enter")
    wait_ms(250)

def _wait_for_saved_file(
    file_path: Path,
    previous_mtime_ns: int | None,
    previous_size: int | None,
) -> bool:
    deadline = time.monotonic() + config.SAVE_DIALOG_TIMEOUT

    while time.monotonic() < deadline:
        execution_gate.wait_if_paused()
        if file_path.exists():
            current_mtime_ns = file_path.stat().st_mtime_ns
            current_size = file_path.stat().st_size
            if (
                previous_mtime_ns is None
                or current_mtime_ns != previous_mtime_ns
                or current_size != previous_size
            ):
                    return True

        wait_ms(200)

    return False


def ensure_output_directory() -> None:
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Output directory ready: %s", config.OUTPUT_DIR)


def write_post(post: dict) -> None:
                                                                                                   
    if not config.DRY_RUN:
        _gate_checkpoint()
        hotkey("ctrl", "n")
        wait_ms(200)

    title = post.get("title", "Untitled")
    body = post.get("body", "")
    content = f"Title: {title}\n\n{body}"

    logger.info("Typing post %s (%d characters)", post.get("id", "?"), len(content))
    _gate_checkpoint()
    type_text(content)


def launch_notepad_process() -> bool:
    if config.DRY_RUN:
        logger.info("[DRY_RUN] launch_notepad_process() -> True")
        return True

    from src.automation.desktop import hotkey, press, type_text, wait_ms
    try:
        logger.info("Executing Win+R launch override for exact determinism")

        _gate_checkpoint()
        hotkey("win", "r")
        time.sleep(0.5)

        if not wait_for_window(TITLE_RUN, timeout=3):
            logger.warning("Run dialog not detected after Win+R; retrying once")
            _gate_checkpoint()
            hotkey("win", "r")
            time.sleep(0.5)
            if not wait_for_window(TITLE_RUN, timeout=3):
                logger.error("Run dialog did not appear; aborting Win+R fallback")
                return False

        if not activate_window(TITLE_RUN, timeout=2):
            logger.error("Run dialog appeared but could not be focused")
            return False

        _gate_checkpoint()
        type_text("notepad.exe")
        wait_ms(200)

        _gate_checkpoint()
        press("enter")
    except Exception as exc:
        logger.error("Win+R Notepad launch failed: %s", exc)
        return False

    return wait_for_window(TITLE_NOTEPAD, timeout=config.WINDOW_TIMEOUT)


def save_post(post_id: int) -> None:
    file_path = config.OUTPUT_DIR / f"post_{post_id}.txt"
    absolute_path = str(file_path.resolve())

    if config.DRY_RUN:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(
            f"DRY_RUN placeholder for post {post_id}\n",
            encoding="utf-8",
        )
        logger.info("[DRY_RUN] Simulated save for post_%d at %s", post_id, absolute_path)
        return

    previous_mtime_ns = file_path.stat().st_mtime_ns if file_path.exists() else None
    previous_size = file_path.stat().st_size if file_path.exists() else None

    logger.info("Saving post_%d to %s", post_id, absolute_path)

    _gate_checkpoint()
    hotkey("ctrl", "s")
    if not wait_for_window(TITLE_SAVE, timeout=config.SAVE_DIALOG_TIMEOUT):
        logger.warning("Save dialog not detected, trying Ctrl+Shift+S")
        _gate_checkpoint()
        hotkey("ctrl", "shift", "s")
        if not wait_for_window(TITLE_SAVE, timeout=config.SAVE_DIALOG_TIMEOUT):
            logger.warning("Save dialog still not detected, trying Alt+F then A")
            _gate_checkpoint()
            hotkey("alt", "f")
            wait_ms(120)
            _gate_checkpoint()
            press("a")
            if not wait_for_window(TITLE_SAVE, timeout=config.SAVE_DIALOG_TIMEOUT):
                raise WindowNotFoundError("Save As dialog did not appear")

    if not activate_window(TITLE_SAVE, timeout=config.SAVE_DIALOG_TIMEOUT):
        raise WindowNotFoundError("Save As dialog could not be focused")

    wait_ms(400)
    _gate_checkpoint()
    _submit_save_path(absolute_path)

    if is_window_open(TITLE_CONFIRM):
        logger.debug("Overwrite confirmation detected, pressing Yes")
        _gate_checkpoint()
        hotkey("alt", "y")
        wait_ms(150)

    if _wait_for_saved_file(file_path, previous_mtime_ns, previous_size):       
        if is_window_open(TITLE_SAVE):
            logger.warning(
                "Save dialog still open after file write; dismissing it with Escape"
            )
            press("esc")
            wait_ms(100)
        logger.info("Post %d saved successfully", post_id)
        return

    if is_window_open(TITLE_SAVE):
        logger.warning("Save dialog still open after first submit; retrying once")
        _gate_checkpoint()
        _submit_save_path(absolute_path)

        if is_window_open(TITLE_CONFIRM):
            logger.debug("Overwrite confirmation detected on retry, pressing Yes")
            _gate_checkpoint()
            hotkey("alt", "y")
            wait_ms(150)

        if _wait_for_saved_file(file_path, previous_mtime_ns, previous_size):
            if is_window_open(TITLE_SAVE):
                logger.warning(
                    "Save dialog still open after retry file write; dismissing it with Escape"
                )
                press("esc")
                wait_ms(100)
            logger.info("Post %d saved successfully after retry", post_id)
            return

    if is_window_open(TITLE_SAVE):
        logger.warning("Save dialog still open; retrying via folder navigation")
        _gate_checkpoint()
        _submit_save_via_directory_navigation(file_path)

        if is_window_open(TITLE_CONFIRM):
            logger.debug("Overwrite confirmation detected on folder-navigation retry, pressing Yes")
            _gate_checkpoint()
            hotkey("alt", "y")
            wait_ms(150)

        if _wait_for_saved_file(file_path, previous_mtime_ns, previous_size):
            if is_window_open(TITLE_SAVE):
                logger.warning(
                    "Save dialog still open after folder-navigation write; dismissing it with Escape"
                )
                press("esc")
                wait_ms(100)
            logger.info("Post %d saved successfully after folder-navigation retry", post_id)
            return

    wait_ms(150)
    if is_window_open(TITLE_SAVE):
        raise WindowNotFoundError("Save dialog is still open after save attempt")

    raise WindowNotFoundError(f"Saved file was not written: {file_path}")



def close_notepad() -> None:
    if not is_window_open(TITLE_NOTEPAD):
        logger.debug("Notepad window not detected; enforcing process cleanup")
        force_terminate_notepad_processes()
        return

    for attempt in range(1, 4):
        _gate_checkpoint()
        activate_window(TITLE_NOTEPAD, timeout=1)
        hotkey("alt", "f4")
        wait_ms(250)

        if is_window_open(TITLE_SAVE) or is_window_open(TITLE_CONFIRM):
            _gate_checkpoint()
            hotkey("alt", "n")
            wait_ms(200)

        if not is_window_open(TITLE_NOTEPAD):
            logger.debug("Notepad closed on attempt %d", attempt)
            return

    logger.warning("Notepad still open after Alt+F4 attempts; forcing process termination")
    force_terminate_notepad_processes()

    if is_window_open(TITLE_NOTEPAD):
        logger.warning("Notepad still open even after taskkill fallback")
    else:
        logger.debug("Notepad closed after taskkill fallback")


def force_terminate_notepad_processes() -> None:
    if config.DRY_RUN:
        logger.info("[DRY_RUN] force_terminate_notepad_processes()")
        return

    if os.name != "nt":
        return

    _gate_checkpoint()
    result = subprocess.run(
        ["taskkill", "/F", "/IM", "notepad.exe"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        logger.info("taskkill terminated Notepad instances")
        return

    combined_output = f"{result.stdout} {result.stderr}".lower()
    if "not found" in combined_output or "no running instance" in combined_output:
        logger.debug("taskkill found no running Notepad instances")
        return

    logger.warning("taskkill returned %d while terminating Notepad: %s", result.returncode, combined_output.strip())
