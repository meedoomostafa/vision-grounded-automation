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
    TITLE_CONFIRM,
    TITLE_NOTEPAD,
    TITLE_SAVE,
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

EXPECTED_WINDOW_TITLES = tuple(dict.fromkeys((*TITLE_NOTEPAD, *TITLE_SAVE, *TITLE_CONFIRM)))


def _should_use_grounding_for_post(index: int) -> bool:
    mode = config.GROUNDING_MODE
    if mode == "all":
        return True
    if mode == "none":
        return False
    return index == 0


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
    logger.info("Grounding mode: %s", config.GROUNDING_MODE)
    logger.info("Launch strategy: %s", config.LAUNCH_STRATEGY)
    logger.info("Launch cursor restore mode: %s", config.LAUNCH_CURSOR_RESTORE_MODE)
    logger.info("Launch trace screenshots: %s", config.LAUNCH_TRACE_SCREENSHOTS)
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
                    _process_single_post(
                        grounder,
                        post,
                        index,
                        use_grounding=_should_use_grounding_for_post(index),
                    )
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
        # Strict post-loop cleanup: ensure 0 Notepad window leaks on the desktop.
        import os as _os
        if _os.name == "nt":
            _os.system("taskkill /F /IM notepad.exe >nul 2>&1")

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
    from src.automation.desktop import (
        click,
        double_click,
        get_cursor_position,
        move_cursor,
        press,
        show_desktop,
        wait_ms,
    )
    from src.automation.window import activate_window, wait_for_window
    from src.core.exceptions import GroundingError, WindowNotFoundError
    from src.vision.annotator import annotate_detection, save_annotated, save_debug_image
    from src.vision.screenshot import capture_screen
    import src.config as config
    import os

    screenshot = None
    x = y = None
    strategy = getattr(config, "LAUNCH_STRATEGY", "cascade")
    restore_launch_clicks = getattr(config, "LAUNCH_CURSOR_RESTORE_MODE", "off") == "end"

    def _is_notepad_icon_name(name: str) -> bool:
        lowered = name.strip().lower()
        return ("notepad" in lowered) or ("المفكرة" in name)

    def _filter_template_candidates_by_icon_name(
        raw_candidates: list[tuple[int, int]],
    ) -> list[tuple[int, int]]:
        if not raw_candidates:
            return []

        try:
            from src.automation.desktop import list_desktop_icons
        except Exception:
            return raw_candidates

        desktop_icons = list_desktop_icons()
        if not desktop_icons:
            return raw_candidates

        notepad_icon_centers: list[tuple[int, int]] = []
        for icon_name, (left, top, right, bottom) in desktop_icons:
            if not _is_notepad_icon_name(icon_name):
                continue
            notepad_icon_centers.append((left + ((right - left) // 2), top + ((bottom - top) // 2)))

        def _icon_name_for_point(point_x: int, point_y: int) -> str | None:
            for icon_name, (left, top, right, bottom) in desktop_icons:
                if left <= point_x <= right and top <= point_y <= bottom:
                    return icon_name
            return None

        matched_notepad: list[tuple[int, int]] = []
        unknown_points: list[tuple[int, int]] = []
        for point_x, point_y in raw_candidates:
            icon_name = _icon_name_for_point(point_x, point_y)
            if not icon_name:
                unknown_points.append((point_x, point_y))
                continue

            if _is_notepad_icon_name(icon_name):
                matched_notepad.append((point_x, point_y))
                continue

            logger.info(
                "Skipping template candidate (%d, %d): resolved to desktop icon '%s'",
                point_x,
                point_y,
                icon_name,
            )

        if matched_notepad:
            logger.info(
                "Keeping %d template candidate(s) resolved to Notepad",
                len(matched_notepad),
            )
            return matched_notepad

        if notepad_icon_centers:
            center_x, center_y = notepad_icon_centers[0]
            logger.info(
                "Injecting desktop Notepad icon candidate (%d, %d) from icon metadata",
                center_x,
                center_y,
            )
            return [(center_x, center_y)]

        if unknown_points:
            logger.warning(
                "No icon-resolved Notepad candidate found; keeping %d unresolved template candidate(s)",
                len(unknown_points),
            )
            return unknown_points

        return raw_candidates

    def _template_candidates(
        screenshot_image,
        *,
        use_botcity: bool = True,
        max_candidates: int = 6,
    ) -> list[tuple[int, int]]:
        if hasattr(grounder, "template_fallback_candidates"):
            try:
                coords_list = grounder.template_fallback_candidates(
                    "Notepad",
                    screenshot_image,
                    use_botcity=use_botcity,
                    max_candidates=max_candidates,
                )
            except TypeError:
                coords_list = grounder.template_fallback_candidates("Notepad", screenshot_image)
            return _filter_template_candidates_by_icon_name(list(coords_list or []))

        try:
            coords = grounder.template_fallback("Notepad", screenshot_image, use_botcity=use_botcity)
        except TypeError:
            coords = grounder.template_fallback("Notepad", screenshot_image)

        candidates = [coords] if coords is not None else []
        return _filter_template_candidates_by_icon_name(candidates)

    def _is_valid_click_point(point_x: int | None, point_y: int | None) -> bool:
        if point_x is None or point_y is None:
            return False
        # Never allow left/top edge click coordinates; they are often invalid fallbacks.
        if point_x <= 0 or point_y <= 0:
            return False
        return True

    def _capture_launch_cursor_anchor() -> tuple[int, int] | None:
        if getattr(config, "LAUNCH_CURSOR_RESTORE_MODE", "off") != "end":
            return None

        anchor = get_cursor_position(allow_bot_fallback=False)
        if anchor is not None:
            if anchor[0] <= 0 or anchor[1] <= 0:
                logger.debug(
                    "Ignoring non-positive launch cursor anchor captured from OS cursor API: %s",
                    anchor,
                )
                return None
            logger.debug("Captured launch cursor anchor at (%d, %d)", anchor[0], anchor[1])
        return anchor

    def _restore_launch_cursor_anchor(
        anchor: tuple[int, int] | None,
        *,
        phase: str,
    ) -> None:
        if anchor is None:
            return

        if anchor[0] <= 0 or anchor[1] <= 0:
            logger.debug(
                "Skipping cursor restore after %s because anchor is non-positive: %s",
                phase,
                anchor,
            )
            return

        move_cursor(anchor[0], anchor[1])
        logger.debug(
            "Restored launch cursor anchor to (%d, %d) after %s",
            anchor[0],
            anchor[1],
            phase,
        )

    def _capture_launch_trace(tag: str) -> None:
        if not getattr(config, "LAUNCH_TRACE_SCREENSHOTS", False):
            return

        safe_tag = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in tag)
        save_debug_image(capture_screen(), f"launch_trace_{safe_tag}")

    if strategy == "template_only":
        def _attempt_template_launch(base_x: int, base_y: int, phase: str) -> bool:
            attempt_points = [(base_x, base_y), (base_x, max(0, base_y - 20))]

            for attempt_index, (ax, ay) in enumerate(attempt_points, start=1):
                if not _is_valid_click_point(ax, ay):
                    logger.warning(
                        "Skipping invalid template launch coordinates (%s, %s) [%s]",
                        ax,
                        ay,
                        phase,
                    )
                    continue

                if attempt_index > 1:
                    logger.warning(
                        "Template-only launch retrying with adjusted coordinates (%d, %d) [%s]",
                        ax,
                        ay,
                        phase,
                    )

                _capture_launch_trace(f"{phase}_attempt{attempt_index}_pre_click_{ax}_{ay}")
                click(ax, ay, restore_cursor=restore_launch_clicks)
                wait_ms(120)
                press("enter")
                if wait_for_window(TITLE_NOTEPAD, timeout=3):
                    _capture_launch_trace(f"{phase}_attempt{attempt_index}_opened_after_enter_{ax}_{ay}")
                    return True

                _capture_launch_trace(f"{phase}_attempt{attempt_index}_post_enter_{ax}_{ay}")

                logger.warning(
                    "Template-only Enter launch did not open Notepad; trying double-click [%s]",
                    phase,
                )
                _capture_launch_trace(f"{phase}_attempt{attempt_index}_pre_double_{ax}_{ay}")
                double_click(ax, ay, restore_cursor=restore_launch_clicks)
                if wait_for_window(TITLE_NOTEPAD, timeout=config.WINDOW_TIMEOUT):
                    _capture_launch_trace(f"{phase}_attempt{attempt_index}_opened_after_double_{ax}_{ay}")
                    return True

                _capture_launch_trace(f"{phase}_attempt{attempt_index}_post_double_{ax}_{ay}")

            return False
        launch_cursor_anchor = _capture_launch_cursor_anchor()
        try:
            show_desktop()
            screenshot = capture_screen()
            opened = False
            attempted_candidates: list[tuple[int, int]] = []

            first_pass_candidates = _template_candidates(screenshot, use_botcity=True, max_candidates=6)
            if not first_pass_candidates:
                raise WindowNotFoundError("Template-only launch failed: Notepad icon not found")

            for candidate_index, (tx, ty) in enumerate(first_pass_candidates, start=1):
                if not _is_valid_click_point(tx, ty):
                    logger.warning(
                        "Skipping invalid template-only candidate (%s, %s)",
                        tx,
                        ty,
                    )
                    continue

                logger.info(
                    "Template-only candidate %d/%d [botcity/opencv] at (%d, %d)",
                    candidate_index,
                    len(first_pass_candidates),
                    tx,
                    ty,
                )
                attempted_candidates.append((tx, ty))
                opened = _attempt_template_launch(tx, ty, "botcity/opencv")
                if opened:
                    break

            if not opened:
                show_desktop()
                screenshot = capture_screen()
                second_pass_candidates = _template_candidates(
                    screenshot,
                    use_botcity=False,
                    max_candidates=8,
                )

                for candidate_index, (ox, oy) in enumerate(second_pass_candidates, start=1):
                    if not _is_valid_click_point(ox, oy):
                        logger.warning(
                            "Skipping invalid opencv-only candidate (%s, %s)",
                            ox,
                            oy,
                        )
                        continue

                    if any(abs(ox - px) <= 20 and abs(oy - py) <= 20 for px, py in attempted_candidates):
                        continue
                    logger.warning(
                        "Template-only retry candidate %d [opencv-only] at (%d, %d)",
                        candidate_index,
                        ox,
                        oy,
                    )
                    attempted_candidates.append((ox, oy))
                    opened = _attempt_template_launch(ox, oy, "opencv-only")
                    if opened:
                        break

            if not opened:
                raise WindowNotFoundError("Template-only launch clicked icon but Notepad did not open")
        finally:
            _restore_launch_cursor_anchor(
                launch_cursor_anchor,
                phase="template-only launch sequence",
            )

        execution_gate.wait_if_paused()
        activate_window(TITLE_NOTEPAD)
        wait_ms(int(config.SETTLE_DELAY * 1000))
        execution_gate.wait_if_paused()
        write_post(post)
        execution_gate.wait_if_paused()
        save_post(post["id"])
        execution_gate.wait_if_paused()
        close_notepad()
        if os.name == "nt":
            execution_gate.wait_if_paused()
            os.system("taskkill /F /IM notepad.exe >nul 2>&1")
        grounder.reset_state()
        wait_ms(int(config.SETTLE_DELAY * 1000))
        return

    if use_grounding:
        try:
            screenshot, x, y = _capture_grounded_target(grounder, post["id"], "full_post")
        except GroundingError as exc:
            logger.warning(
                "Grounding failed before launch; trying template and deterministic fallbacks: %s",
                exc,
            )
            show_desktop()
            screenshot = capture_screen()

    opened = False
    launch_cursor_anchor = _capture_launch_cursor_anchor()
    try:
        if use_grounding and _is_valid_click_point(x, y):
            for launch_attempt in range(1, 3):
                if index < 3 and launch_attempt == 1:
                    regions_data = _build_regions_for_annotation(grounder)
                    annotated = annotate_detection(screenshot, (x, y), regions=regions_data)
                    save_annotated(annotated, f"detection_{index + 1}")

                _capture_launch_trace(f"grounded_attempt{launch_attempt}_pre_click_{x}_{y}")
                click(x, y, restore_cursor=restore_launch_clicks)
                wait_ms(120)
                press("enter")
                if wait_for_window(TITLE_NOTEPAD, timeout=3):
                    _capture_launch_trace(f"grounded_attempt{launch_attempt}_opened_after_enter_{x}_{y}")
                    opened = True
                    break

                _capture_launch_trace(f"grounded_attempt{launch_attempt}_post_enter_{x}_{y}")

                logger.warning("Desktop icon Enter launch did not open Notepad; falling back to double-click")
                _capture_launch_trace(f"grounded_attempt{launch_attempt}_pre_double_{x}_{y}")
                double_click(x, y, restore_cursor=restore_launch_clicks)
                if wait_for_window(TITLE_NOTEPAD, timeout=config.WINDOW_TIMEOUT):
                    _capture_launch_trace(f"grounded_attempt{launch_attempt}_opened_after_double_{x}_{y}")
                    opened = True
                    break

                _capture_launch_trace(f"grounded_attempt{launch_attempt}_post_double_{x}_{y}")

                if launch_attempt == 2:
                    logger.warning("MLLM grounded launch failed twice; trying non-MLLM launch fallbacks")
                    break

                logger.warning("Notepad launch attempt failed; resetting grounding state and retrying")
                grounder.reset_state()
                try:
                    screenshot, x, y = _capture_grounded_target(grounder, post["id"], "full_post_retry")
                except GroundingError as exc:
                    logger.warning(
                        "Grounding retry failed before second launch attempt; switching to non-MLLM fallbacks: %s",
                        exc,
                    )
                    show_desktop()
                    screenshot = capture_screen()
                    x = y = None
                    break

        elif use_grounding and (x is not None or y is not None):
            logger.warning("Ignoring invalid grounded coordinates (%s, %s)", x, y)

        if not opened:
            if screenshot is None:
                show_desktop()
                screenshot = capture_screen()

            template_candidates = _template_candidates(screenshot, use_botcity=True, max_candidates=6)
            for candidate_index, (tx, ty) in enumerate(template_candidates, start=1):
                if not _is_valid_click_point(tx, ty):
                    logger.warning(
                        "Skipping invalid template fallback candidate (%s, %s)",
                        tx,
                        ty,
                    )
                    continue

                logger.info(
                    "Template fallback candidate %d/%d at (%d, %d)",
                    candidate_index,
                    len(template_candidates),
                    tx,
                    ty,
                )
                _capture_launch_trace(f"template_fallback_candidate{candidate_index}_pre_double_{tx}_{ty}")
                double_click(tx, ty, restore_cursor=restore_launch_clicks)
                if wait_for_window(TITLE_NOTEPAD, timeout=config.WINDOW_TIMEOUT):
                    _capture_launch_trace(f"template_fallback_candidate{candidate_index}_opened_after_double_{tx}_{ty}")
                    opened = True
                    break

                _capture_launch_trace(f"template_fallback_candidate{candidate_index}_post_double_{tx}_{ty}")

            if not opened:
                logger.warning("Template fallback failed; using deterministic Win+R launch")
                opened = launch_notepad_process()
    finally:
        _restore_launch_cursor_anchor(
            launch_cursor_anchor,
            phase="launch sequence",
        )

    if not opened:
        raise WindowNotFoundError("Notepad did not launch after all fallbacks")

    execution_gate.wait_if_paused()
    activate_window(TITLE_NOTEPAD)
    wait_ms(int(config.SETTLE_DELAY * 1000))

    execution_gate.wait_if_paused()
    write_post(post)
    execution_gate.wait_if_paused()
    save_post(post["id"])
    execution_gate.wait_if_paused()
    close_notepad()
    if os.name == "nt":
        execution_gate.wait_if_paused()
        os.system("taskkill /F /IM notepad.exe >nul 2>&1")
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
    import os
    from src.automation.desktop import wait_ms
    from src.automation.notepad import force_terminate_notepad_processes

    try:
        close_notepad()
    except Exception:
        pass

    # Aggressive cleanup: force-kill any remaining Notepad instances.
    try:
        force_terminate_notepad_processes()
    except Exception:
        pass
    if os.name == "nt":
        os.system("taskkill /F /IM notepad.exe >nul 2>&1")

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

    max_attempts = max(1, config.GROUNDING_CAPTURE_ATTEMPTS)

    for attempt in range(1, max_attempts + 1):
        logger.debug("Preparing desktop for post %d (ground attempt %d)", post_id, attempt)
        show_desktop()
        screenshot = capture_screen()
        save_debug_image(screenshot, f"{debug_prefix}_{post_id}_attempt_{attempt}")

        try:
            x, y = grounder.ground("Notepad", screenshot)
            if x <= 0 or y <= 0:
                raise GroundingError(f"Grounding returned invalid coordinates ({x}, {y})")
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
