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
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Output directory ready: %s", config.OUTPUT_DIR)


def write_post(post: dict) -> None:
    title = post.get("title", "Untitled")
    body = post.get("body", "")
    content = f"Title: {title}\n\n{body}"

    logger.info("Typing post %s (%d characters)", post.get("id", "?"), len(content))
    type_text(content)


def save_post(post_id: int) -> None:
    file_path = config.OUTPUT_DIR / f"post_{post_id}.txt"
    absolute_path = str(file_path.resolve())

    logger.info("Saving post_%d to %s", post_id, absolute_path)

    hotkey("ctrl", "s")

    if not wait_for_window("Save", timeout=config.SAVE_DIALOG_TIMEOUT):
                                                         
        logger.warning("Save dialog not detected, trying Ctrl+Shift+S")
        hotkey("ctrl", "shift", "s")
        if not wait_for_window("Save", timeout=config.SAVE_DIALOG_TIMEOUT):
            raise WindowNotFoundError("Save As dialog did not appear")

    time.sleep(0.3)

                                                 
    hotkey("ctrl", "a")
    time.sleep(0.1)
    type_text(absolute_path, interval=0.01)
    time.sleep(0.2)

                  
    press("enter")
    time.sleep(0.5)

                                                   
    if is_window_open("Confirm"):
        logger.debug("Overwrite confirmation detected, pressing Yes")
        hotkey("alt", "y")
        time.sleep(0.3)

                                                   
    time.sleep(0.3)
    if is_window_open("Save"):
        logger.warning("Save dialog still open — possible save failure")

    logger.info("Post %d saved successfully", post_id)


def close_notepad() -> None:
    if not is_window_open("Notepad"):
        logger.debug("Notepad already closed")
        return

                              
    if not close_window("Notepad"):
        logger.debug("Window close failed, trying Alt+F4")
        activate_window("Notepad")
        time.sleep(0.2)
        hotkey("alt", "F4")

    time.sleep(0.3)

                                          
    if is_window_open("Notepad"):
                                                                    
        hotkey("alt", "n")
        time.sleep(0.3)

    if is_window_open("Notepad"):
        logger.warning("Notepad still open after close attempts")
    else:
        logger.debug("Notepad closed")
