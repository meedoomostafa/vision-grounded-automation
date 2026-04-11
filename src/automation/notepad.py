"""Notepad-specific automation: launch, write, save, close.

Save As handling uses absolute path injection — no UI directory navigation.
"""

import time

from src import config
from src.automation.desktop import hotkey, press, type_text
from src.automation.window import (
    activate_window,
    close_window,
    is_window_open,
    wait_for_window,
)
from src.core.exceptions import WindowNotFoundError
from src.core.logger import get_logger

logger = get_logger(__name__)


def ensure_output_directory() -> None:
    """Create the output directory if it doesn't exist."""
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Output directory ready: %s", config.OUTPUT_DIR)


def write_post(post: dict) -> None:
    """Type formatted post content into the active Notepad window.

    Format: "Title: {title}\n\n{body}"
    """
    title = post.get("title", "Untitled")
    body = post.get("body", "")
    content = f"Title: {title}\n\n{body}"

    logger.info("Typing post %s (%d characters)", post.get("id", "?"), len(content))
    type_text(content)


def save_post(post_id: int) -> None:
    """Save current Notepad content as post_{id}.txt.

    Rock-solid Save As handling:
    1. Trigger Ctrl+S (opens Save As for new files)
    2. Wait for Save As dialog to become active
    3. Select all text in filename field
    4. Inject full absolute path (no UI directory navigation)
    5. Press Enter to confirm
    6. Handle overwrite confirmation if file exists
    """
    file_path = config.OUTPUT_DIR / f"post_{post_id}.txt"
    absolute_path = str(file_path.resolve())

    logger.info("Saving post_%d to %s", post_id, absolute_path)

    hotkey("ctrl", "s")

    if not wait_for_window("Save", timeout=config.SAVE_DIALOG_TIMEOUT):
        # Fallback: try Ctrl+Shift+S for explicit Save As
        logger.warning("Save dialog not detected, trying Ctrl+Shift+S")
        hotkey("ctrl", "shift", "s")
        if not wait_for_window("Save", timeout=config.SAVE_DIALOG_TIMEOUT):
            raise WindowNotFoundError("Save As dialog did not appear")

    time.sleep(0.3)

    # Clear filename field and type absolute path
    hotkey("ctrl", "a")
    time.sleep(0.1)
    type_text(absolute_path, interval=0.01)
    time.sleep(0.2)

    # Confirm save
    press("enter")
    time.sleep(0.5)

    # Handle "file already exists" overwrite dialog
    if is_window_open("Confirm"):
        logger.debug("Overwrite confirmation detected, pressing Yes")
        hotkey("alt", "y")
        time.sleep(0.3)

    # Verify Save As dialog closed (save completed)
    time.sleep(0.3)
    if is_window_open("Save"):
        logger.warning("Save dialog still open — possible save failure")

    logger.info("Post %d saved successfully", post_id)


def close_notepad() -> None:
    """Close Notepad gracefully.

    Tries pywinctl close first, falls back to Alt+F4.
    Handles any "save changes?" prompts by discarding.
    """
    if not is_window_open("Notepad"):
        logger.debug("Notepad already closed")
        return

    # Try window manager close
    if not close_window("Notepad"):
        logger.debug("Window close failed, trying Alt+F4")
        activate_window("Notepad")
        time.sleep(0.2)
        hotkey("alt", "F4")

    time.sleep(0.3)

    # Handle "do you want to save?" prompt
    if is_window_open("Notepad"):
        # Press "Don't Save" — Tab to the button and Enter, or Alt+N
        hotkey("alt", "n")
        time.sleep(0.3)

    if is_window_open("Notepad"):
        logger.warning("Notepad still open after close attempts")
    else:
        logger.debug("Notepad closed")
