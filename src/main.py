"""Main entry point for the hybrid desktop automation pipeline."""

from __future__ import annotations

import signal
import sys
from contextlib import contextmanager
from typing import Any

from src import config
from src.automation.api_client import fetch_posts
from src.automation.control import execution_gate
from src.automation.desktop import hotkey, press
from src.automation.notepad import (
    close_notepad,
    ensure_output_directory,
    launch_notepad_process,
    save_post,
    write_post,
)
from src.core.exceptions import (
    DesktopAutomationError,
    GroundingError,
    SingletonLockError,
)
from src.core.logger import get_logger, setup_logging
from src.core.singleton import SingletonLock

logger = get_logger(__name__)

EXPECTED_WINDOW_TITLES = ("Notepad", "Save", "Confirm")


def main() -> None:
    """Run the desktop automation pipeline under a singleton runtime lock."""
    with SingletonLock(config.LOCK_FILE):
        _run()


def _run() -> None:
    setup_logging()
    logger.info("=" * 60)
    logger.info("Desktop Automation - Starting")
    logger.info("DRY_RUN=%s  VISUAL_DEBUG=%s", config.DRY_RUN, config.VISUAL_DEBUG)
    logger.info("Output directory: %s", config.OUTPUT_DIR)
    logger.info("Runtime lock: %s", config.LOCK_FILE)
    logger.info("Watcher enabled: %s", config.WATCHER_ENABLED)
    logger.info("=" * 60)

    ensure_output_directory()
    posts = fetch_posts(limit=config.API_POSTS_LIMIT)
    if not posts:
        logger.error("No posts retrieved from API. Cannot proceed.")
        sys.exit(1)

    logger.info("Processing %d posts", len(posts))
    results = {"success": 0, "failed": 0}

    if config.DRY_RUN:
        _run_dry_run(posts, results)
        _log_summary(results, len(posts))
        return

    from src.vision.grounding import VisionGrounder
    from src.watcher import FocusWatcher

    grounder = VisionGrounder()
    watcher = (
        FocusWatcher(execution_gate, lambda event: _handle_focus_anomaly(grounder, event))
        if config.WATCHER_ENABLED
        else None
    )

    execution_gate.arm(EXPECTED_WINDOW_TITLES)
    try:
        if watcher is not None:
            watcher.start()

        with _signal_handlers(watcher):
            for index, post in enumerate(posts):
                post_id = post["id"]
                logger.info("-" * 40)
                logger.info("Post %d/%d (id=%d)", index + 1, len(posts), post_id)

                try:
                    _process_single_post(grounder, post, index, use_grounding=index == 0)
                    results["success"] += 1
                except GroundingError as exc:
                    logger.error("Failed post %d: %s", post_id, exc)
                    results["failed"] += 1
                    _recover(grounder, reset_grounding=True)
                except DesktopAutomationError as exc:
                    logger.error("Failed post %d: %s", post_id, exc)
                    results["failed"] += 1
                    _recover(grounder, reset_grounding=True)
                except Exception as exc:  # pragma: no cover - defensive top-level guard
                    logger.error(
                        "Unexpected error on post %d: %s",
                        post_id,
                        exc,
                        exc_info=True,
                    )
                    results["failed"] += 1
                    _recover(grounder, reset_grounding=True)
    finally:
        execution_gate.disarm()
        execution_gate.resume("run finished")
        if watcher is not None:
            watcher.stop()
            watcher.join(timeout=2.0)

    _log_summary(results, len(posts))


def _run_dry_run(posts: list[dict], results: dict[str, int]) -> None:
    for post in posts:
        logger.info("-" * 40)
        logger.info("DRY_RUN post id=%d", post["id"])
        save_post(post["id"])
        results["success"] += 1


def _process_single_post(
    grounder: Any,
    post: dict,
    index: int,
    *,
    use_grounding: bool,
) -> None:
    """Handle one post: ground, launch, type, save, and close."""
    from src.automation.desktop import click, double_click, press, wait_ms
    from src.automation.window import activate_window, wait_for_window
    from src.core.exceptions import WindowNotFoundError
    from src.vision.annotator import annotate_detection, save_annotated

    if use_grounding:
        screenshot, x, y = _capture_grounded_target(grounder, post["id"], "full_post")
    else:
        screenshot = None
        x = y = None

    if use_grounding:
        for launch_attempt in range(1, 3):
            if index < 3 and launch_attempt == 1:
                regions_data = _build_regions_for_annotation(grounder)
                annotated = annotate_detection(screenshot, (x, y), regions=regions_data)
                save_annotated(annotated, f"detection_{index + 1}")

            click(x, y)
            wait_ms(120)
            press("enter")
            if wait_for_window("Notepad", timeout=3):
                break

            logger.warning("Desktop icon Enter launch did not open Notepad; falling back to double-click")
            double_click(x, y)
            if wait_for_window("Notepad", timeout=config.WINDOW_TIMEOUT):
                break

            if launch_attempt == 2:
                logger.warning(
                    "Grounded desktop launch failed twice; using deterministic Notepad fallback"
                )
                if launch_notepad_process():
                    break
                raise WindowNotFoundError("Notepad did not launch after double-click")

            logger.warning("Notepad launch attempt failed; resetting grounding state and retrying")
            grounder.reset_state()
            screenshot, x, y = _capture_grounded_target(grounder, post["id"], "full_post_retry")
    elif not launch_notepad_process():
        raise WindowNotFoundError("Notepad did not launch via deterministic fallback")

    activate_window("Notepad")
    wait_ms(int(config.SETTLE_DELAY * 1000))

    write_post(post)
    save_post(post["id"])
    close_notepad()
    grounder.reset_state()
    wait_ms(int(config.SETTLE_DELAY * 1000))


def _handle_focus_anomaly(grounder: Any, event) -> None:
    from src.automation.desktop import get_bot
    from src.vision.annotator import save_debug_image
    from src.vision.screenshot import capture_screen

    logger.warning(
        "Focus anomaly detected: title=%r process=%s class=%s",
        event.title,
        event.process_name,
        event.class_name,
    )

    screenshot = capture_screen()
    save_debug_image(screenshot, f"focus_anomaly_{int(event.timestamp)}")
    analysis = grounder.analyze_popup(screenshot, event.title, event.process_name)

    action = analysis["action"]
    reasoning = analysis["reasoning"]
    logger.warning("Popup resolution action=%s reason=%s", action, reasoning)

    with execution_gate.bypass_pause():
        if action == "press_escape":
            press("esc")
        elif action == "press_enter":
            press("enter")
        elif action == "hotkey_alt_f4":
            hotkey("alt", "F4")
        elif action == "hotkey_alt_n":
            hotkey("alt", "n")
        get_bot().wait(250)


def _recover(grounder: Any, reset_grounding: bool = False) -> None:
    """Attempt recovery after a failure by closing Notepad and resetting state."""
    from src.automation.desktop import wait_ms

    try:
        close_notepad()
    except Exception:
        pass

    if reset_grounding:
        grounder.reset_state()

    wait_ms(int(config.SETTLE_DELAY * 1000))


def _capture_grounded_target(
    grounder: Any,
    post_id: int,
    debug_prefix: str,
) -> tuple[Any, int, int]:
    from src.automation.desktop import show_desktop
    from src.vision.annotator import save_debug_image
    from src.vision.screenshot import capture_screen

    last_error: GroundingError | None = None

    for attempt in range(1, 4):
        logger.debug("Preparing desktop for post %d (ground attempt %d)", post_id, attempt)
        show_desktop()
        screenshot = capture_screen()
        save_debug_image(screenshot, f"{debug_prefix}_{post_id}_attempt_{attempt}")

        try:
            x, y = grounder.ground("Notepad", screenshot)
            return screenshot, x, y
        except GroundingError as exc:
            last_error = exc
            logger.warning(
                "Grounding attempt %d for post %d failed: %s",
                attempt,
                post_id,
                exc,
            )
            grounder.reset_state()

    raise last_error or GroundingError("Grounding failed without an exception")


def _log_summary(results: dict[str, int], total_posts: int) -> None:
    logger.info("=" * 60)
    logger.info(
        "Complete: %d succeeded, %d failed out of %d",
        results["success"],
        results["failed"],
        total_posts,
    )
    logger.info("Output: %s", config.OUTPUT_DIR)
    logger.info("=" * 60)


def _build_regions_for_annotation(grounder: Any) -> list[dict] | None:
    bbox = grounder.last_region_bbox
    if bbox:
        return [
            {
                "x1": bbox[0],
                "y1": bbox[1],
                "x2": bbox[2],
                "y2": bbox[3],
                "confidence": 1.0,
            }
        ]
    return None


@contextmanager
def _signal_handlers(watcher) -> None:
    signals = [signal.SIGINT]
    if hasattr(signal, "SIGTERM"):
        signals.append(signal.SIGTERM)

    previous_handlers = {sig: signal.getsignal(sig) for sig in signals}

    def _handle_signal(signum, frame):
        logger.warning("Received shutdown signal %s", signum)
        execution_gate.resume("shutdown signal")
        if watcher is not None:
            watcher.stop()
        raise KeyboardInterrupt

    for sig in signals:
        signal.signal(sig, _handle_signal)

    try:
        yield
    finally:
        for sig, previous in previous_handlers.items():
            signal.signal(sig, previous)


if __name__ == "__main__":
    try:
        main()
    except SingletonLockError as exc:
        setup_logging()
        logger.error("%s", exc)
        sys.exit(1)
    except KeyboardInterrupt:
        setup_logging()
        logger.warning("Interrupted by user")
        sys.exit(130)
