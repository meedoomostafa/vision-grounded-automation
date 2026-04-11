import sys
import time

from src import config
from src.automation.api_client import fetch_posts
from src.automation.desktop import double_click
from src.automation.notepad import (
    close_notepad,
    ensure_output_directory,
    save_post,
    write_post,
)
from src.automation.window import activate_window, wait_for_window
from src.core.exceptions import DesktopAutomationError, WindowNotFoundError
from src.core.logger import get_logger, setup_logging
from src.vision.annotator import annotate_detection, save_annotated
from src.vision.grounding import VisionGrounder
from src.vision.screenshot import capture_screen

logger = get_logger(__name__)


def main() -> None:
    setup_logging()
    logger.info("=" * 60)
    logger.info("Desktop Automation — Starting")
    logger.info("DRY_RUN=%s  VISUAL_DEBUG=%s", config.DRY_RUN, config.VISUAL_DEBUG)
    logger.info("Output directory: %s", config.OUTPUT_DIR)
    logger.info("=" * 60)

                
    grounder = VisionGrounder()
    ensure_output_directory()

                 
    posts = fetch_posts(limit=config.API_POSTS_LIMIT)
    if not posts:
        logger.error("No posts retrieved from API. Cannot proceed.")
        sys.exit(1)

    logger.info("Processing %d posts", len(posts))

    results = {"success": 0, "failed": 0}

    for i, post in enumerate(posts):
        post_id = post["id"]
        logger.info("-" * 40)
        logger.info("Post %d/%d (id=%d)", i + 1, len(posts), post_id)

        try:
            _process_single_post(grounder, post, i)
            results["success"] += 1
        except DesktopAutomationError as exc:
            logger.error("Failed post %d: %s", post_id, exc)
            results["failed"] += 1
            _recover(grounder)
        except Exception as exc:
            logger.error("Unexpected error on post %d: %s", post_id, exc, exc_info=True)
            results["failed"] += 1
            _recover(grounder)

             
    logger.info("=" * 60)
    logger.info(
        "Complete: %d succeeded, %d failed out of %d",
        results["success"],
        results["failed"],
        len(posts),
    )
    logger.info("Output: %s", config.OUTPUT_DIR)
    logger.info("=" * 60)


def _process_single_post(grounder: VisionGrounder, post: dict, index: int) -> None:
                                                         
    screenshot = capture_screen()

                         
    coords = grounder.ground("Notepad", screenshot)
    x, y = coords

                                                                      
    if index < 3:
        regions_data = _build_regions_for_annotation(grounder)
        annotated = annotate_detection(screenshot, coords, regions=regions_data)
        save_annotated(annotated, f"detection_{index + 1}")

                    
    double_click(x, y)
    if not wait_for_window("Notepad", timeout=config.WINDOW_TIMEOUT):
        raise WindowNotFoundError("Notepad did not launch after double-click")

    activate_window("Notepad")
    time.sleep(config.SETTLE_DELAY)

                   
    write_post(post)

               
    save_post(post["id"])

           
    close_notepad()
    time.sleep(config.SETTLE_DELAY)


def _recover(grounder: VisionGrounder) -> None:
    try:
        close_notepad()
    except Exception:
        pass
    grounder.reset_state()
    time.sleep(config.SETTLE_DELAY)


def _build_regions_for_annotation(grounder: VisionGrounder) -> list[dict] | None:
    bbox = grounder.last_region_bbox
    if bbox:
        return [{"x1": bbox[0], "y1": bbox[1], "x2": bbox[2], "y2": bbox[3], "confidence": 1.0}]
    return None


if __name__ == "__main__":
    main()
