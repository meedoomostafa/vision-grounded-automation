from __future__ import annotations

import subprocess
import time
from pathlib import Path

from src import config
from src.automation.control import execution_gate
from src.automation.desktop import hotkey, press, type_text, wait_ms
from src.automation.window import (
    activate_window,
    close_window,
    is_window_open,
    wait_for_window,
)
from src.core.exceptions import WindowNotFoundError
from src.core.logger import get_logger

logger = get_logger(__name__)


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
        hotkey("ctrl", "n")
        wait_ms(200)

    title = post.get("title", "Untitled")
    body = post.get("body", "")
    content = f"Title: {title}\n\n{body}"

    logger.info("Typing post %s (%d characters)", post.get("id", "?"), len(content))
    type_text(content)


def launch_notepad_process() -> bool:
    if config.DRY_RUN:
        logger.info("[DRY_RUN] launch_notepad_process() -> True")
        return True

    try:
        subprocess.Popen(["notepad.exe"])
    except OSError as exc:
        logger.error("Deterministic Notepad launch failed: %s", exc)
        return False

    return wait_for_window("Notepad", timeout=config.WINDOW_TIMEOUT)


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

    hotkey("ctrl", "s")
    if not wait_for_window("Save", timeout=config.SAVE_DIALOG_TIMEOUT):
        logger.warning("Save dialog not detected, trying Ctrl+Shift+S")
        hotkey("ctrl", "shift", "s")
        if not wait_for_window("Save", timeout=config.SAVE_DIALOG_TIMEOUT):
            raise WindowNotFoundError("Save As dialog did not appear")

    if not activate_window("Save", timeout=config.SAVE_DIALOG_TIMEOUT):
        raise WindowNotFoundError("Save As dialog could not be focused")

    wait_ms(150)
    hotkey("alt", "n")
    wait_ms(80)
    hotkey("ctrl", "a")
    wait_ms(80)
    type_text(absolute_path, interval=0.01)
    wait_ms(120)

    press("enter")
    wait_ms(250)

    if is_window_open("Confirm"):
        logger.debug("Overwrite confirmation detected, pressing Yes")
        hotkey("alt", "y")
        wait_ms(150)

    if _wait_for_saved_file(file_path, previous_mtime_ns, previous_size):
        if is_window_open("Save"):
            logger.warning(
                "Save dialog still open after file write; dismissing it with Escape"
            )
            press("esc")
            wait_ms(100)
        logger.info("Post %d saved successfully", post_id)
        return

    wait_ms(150)
    if is_window_open("Save"):
        raise WindowNotFoundError("Save dialog is still open after save attempt")

    raise WindowNotFoundError(f"Saved file was not written: {file_path}")


def close_notepad() -> None:
    if not is_window_open("Notepad"):
        logger.debug("Notepad already closed")
        return

    if not close_window("Notepad"):
        logger.debug("Window close failed, trying Alt+F4")
        activate_window("Notepad")
        wait_ms(100)
        hotkey("alt", "F4")

    wait_ms(200)

    if is_window_open("Notepad"):
        hotkey("alt", "n")
        wait_ms(150)

    if is_window_open("Notepad"):
        logger.warning("Notepad still open after close attempts")
    else:
        logger.debug("Notepad closed")
