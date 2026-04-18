"""Stateful VisionGrounder — ScreenSeekeR-inspired cascaded visual search engine.

Algorithm overview:
  Full search (Phase 1→2→3):
    1. Send full screenshot to MLLM → get candidate regions
    2. For each region: crop → send to MLLM → get precise (x,y)
    3. Verify each candidate → select best match
  Precise re-ground (Phase 2→3 only):
    Crop around last known position → precise locate → verify

State management:
  After a successful ground, caches the coordinates and region.
  Next call uses precise re-ground first, falling back to full search.
"""

from __future__ import annotations

import json
import tempfile
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from google import genai
from google.genai import types
from PIL import Image, ImageFilter

from src import config
from src.core.exceptions import GroundingError, IconNotFoundError
from src.core.logger import get_logger
from src.core.retry import retry
from src.vision import prompts
from src.vision.annotator import annotate_detection, save_debug_crop, draw_coordinate_grid
from src.vision.screenshot import crop_region

logger = get_logger(__name__)
_RATE_LIMIT_EVENT = Event()


@dataclass
class Region:
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float
    reasoning: str = ""


@dataclass
class Candidate:
    x: int
    y: int
    confidence: float
    label: str
    region_bbox: tuple[int, int, int, int]


@dataclass(frozen=True)
class TemplateMatch:
    x: int
    y: int
    score: float
    width: int
    height: int


class VisionGrounder:
    """Stateful cascaded visual search engine.

    Tracks last known icon position to optimize repeated searches.
    Falls back to full cascaded search when precise re-ground fails.
    """

    def __init__(self, model_name: str | None = None):
        self._model = model_name or config.GEMINI_MODEL

        if not config.DRY_RUN:
            self._client_cache: dict[str, genai.Client] = {}
        else:
            self._client_cache = {}

        self._last_known_coords: tuple[int, int] | None = None
        self._last_region_bbox: tuple[int, int, int, int] | None = None
        self._search_count = 0
        self._last_mllm_call_at = 0.0
        self._mllm_calls_used = 0

    def ground(self, target: str, screenshot: Image.Image) -> tuple[int, int]:
        """Locate target element on screen. Returns absolute (x, y) coordinates.

        Uses stateful grounding: precise re-ground if position is cached,
        full cascaded search otherwise.
        """
        self._search_count += 1
        logger.info(
            "Grounding '%s' (search #%d, mode=%s)",
            target,
            self._search_count,
            "PRECISE" if self._last_known_coords else "FULL",
        )

        # Attempt precise re-ground if we have cached coordinates
        if self._last_known_coords:
            try:
                coords = self._precise_reground(
                    target,
                    screenshot,
                    verify=True,
                )
                coords = self._apply_target_click_bias(target, coords, screenshot)
                self._last_known_coords = coords
                logger.info("Precise re-ground succeeded: (%d, %d)", *coords)
                return coords
            
            except GroundingError:
                logger.warning("Precise re-ground failed, falling back to full search")

        direct_coords = self._verified_direct_fullscreen_locate(target, screenshot)
        if direct_coords is not None:
            direct_coords = self._apply_target_click_bias(target, direct_coords, screenshot)
            self._last_known_coords = direct_coords
            logger.info(
                "Verified direct full-screen locate found '%s' at (%d, %d)",
                target,
                direct_coords[0],
                direct_coords[1],
            )
            return direct_coords

        coords = self._full_cascaded_search(target, screenshot)
        coords = self._apply_target_click_bias(target, coords, screenshot)
        self._last_known_coords = coords
        logger.info("Full cascaded search found '%s' at (%d, %d)", target, *coords)
        return coords

    def reset_state(self) -> None:
        """Clear cached position, forcing full search on next call."""
        self._last_known_coords = None
        self._last_region_bbox = None
        logger.debug("Grounding state reset")

    @property
    def last_region_bbox(self) -> tuple[int, int, int, int] | None:
        return self._last_region_bbox

    @staticmethod
    def _is_notepad_target(target: str) -> bool:
        lowered = target.strip().lower()
        return "notepad" in lowered

    def _apply_target_click_bias(
        self,
        target: str,
        coords: tuple[int, int],
        screenshot: Image.Image,
    ) -> tuple[int, int]:
        """Apply a small downward bias for known desktop-icon targets.

        Notepad detections tend to land on the upper glyph edge, while launch
        reliability improves when the click lands closer to the icon body.
        """
        if not self._is_notepad_target(target):
            return coords

        x, y = coords
        y = max(0, min(screenshot.height - 1, y + 35))
        return (x, y)

    def template_fallback(
        self,
        target: str,
        screenshot: Image.Image,
        *,
        use_botcity: bool = True,
    ) -> tuple[int, int] | None:
        """Tier-2 CV fallback: BotCity template, then OpenCV multi-scale matching."""
        if not self._is_notepad_target(target):
            return None

        template_path = Path("notepad.png")
        if not template_path.exists():
            logger.warning("Template fallback skipped: notepad.png not found")
            return None

        coords = self._botcity_template_fallback(template_path) if use_botcity else None
        if coords is None:
            coords = self._opencv_template_fallback(template_path, screenshot)

        if coords is not None:
            # Template matching already returns icon-centered coordinates;
            # keep them unchanged to avoid drifting into the label area.
            self._last_known_coords = coords

        return coords

    def template_fallback_candidates(
        self,
        target: str,
        screenshot: Image.Image,
        *,
        use_botcity: bool = True,
        max_candidates: int = 6,
    ) -> list[tuple[int, int]]:
        """Return ordered template candidates for launch retries.

        BotCity contributes at most one strict match, while OpenCV contributes
        multiple high-scoring candidates across scales.
        """
        if not self._is_notepad_target(target):
            return []

        template_path = Path("notepad.png")
        if not template_path.exists():
            logger.warning("Template fallback skipped: notepad.png not found")
            return []

        candidates: list[tuple[int, int]] = []

        if use_botcity:
            botcity_coords = self._botcity_template_fallback(template_path)
            if botcity_coords is not None:
                candidates.append(botcity_coords)

        opencv_matches = self._opencv_template_candidates(
            template_path,
            screenshot,
            max_candidates=max_candidates,
        )
        candidates.extend((match.x, match.y) for match in opencv_matches)

        unique_candidates = self._dedupe_coordinate_candidates(candidates)
        if unique_candidates:
            logger.info(
                "Template fallback produced %d unique candidate(s)",
                len(unique_candidates),
            )
        return unique_candidates

    @staticmethod
    def _dedupe_coordinate_candidates(
        candidates: list[tuple[int, int]],
        *,
        min_distance: int = 30,
    ) -> list[tuple[int, int]]:
        if not candidates:
            return []

        unique: list[tuple[int, int]] = []
        min_distance_sq = min_distance * min_distance
        for candidate_x, candidate_y in candidates:
            if any(
                ((candidate_x - existing_x) ** 2) + ((candidate_y - existing_y) ** 2)
                < min_distance_sq
                for existing_x, existing_y in unique
            ):
                continue
            unique.append((candidate_x, candidate_y))

        return unique

    @staticmethod
    def _botcity_template_fallback(template_path: Path) -> tuple[int, int] | None:
        try:
            from src.automation.desktop import get_bot

            bot = get_bot()
            variant_paths: list[tuple[Path, float, str]] = [(template_path.resolve(), 1.0, "native")]
            temporary_files: list[Path] = []

            try:
                with Image.open(template_path) as base_image:
                    base_rgba = base_image.convert("RGBA")
                    alpha = base_rgba.getchannel("A")
                    alpha_hist = alpha.histogram()
                    transparent_ratio = sum(alpha_hist[:250]) / max(sum(alpha_hist), 1)

                    rendered_variants: list[tuple[Image.Image, str]] = [(base_rgba.convert("RGB"), "native")]

                    if transparent_ratio > 0.05:
                        logger.info(
                            "BotCity template has transparency ratio %.2f; creating composited variants",
                            transparent_ratio,
                        )
                        for background_name, color in (
                            ("bg_dark", (16, 16, 16)),
                            ("bg_mid", (80, 80, 80)),
                            ("bg_light", (210, 210, 210)),
                        ):
                            flattened = Image.new("RGB", base_rgba.size, color)
                            flattened.paste(base_rgba, mask=alpha)
                            rendered_variants.append((flattened, background_name))

                    scales = (0.85, 0.66, 0.50, 0.40, 0.33, 0.28, 0.24, 0.20, 0.16, 0.12, 0.10, 0.08, 0.06)
                    seen_sizes: set[tuple[int, int, str]] = set()

                    for rendered, variant_name in rendered_variants:
                        width, height = rendered.size
                        for scale in scales:
                            scaled_w = int(width * scale)
                            scaled_h = int(height * scale)
                            if scaled_w < 12 or scaled_h < 12:
                                continue
                            size_key = (scaled_w, scaled_h, variant_name)
                            if size_key in seen_sizes:
                                continue
                            seen_sizes.add(size_key)

                            scaled = rendered.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

                            temp_file = tempfile.NamedTemporaryFile(
                                prefix="botcity_notepad_",
                                suffix=".png",
                                delete=False,
                            )
                            temp_path = Path(temp_file.name)
                            temp_file.close()
                            scaled.save(temp_path)
                            temporary_files.append(temp_path)
                            variant_paths.append((temp_path, scale, variant_name))

                for idx, (candidate_path, scale, variant_name) in enumerate(variant_paths):
                    label = f"notepad_template_{idx}"
                    bot.add_image(label, str(candidate_path))

                    # Keep BotCity strict; weak matches are prone to false positives.
                    # OpenCV fallback handles harder cases with score-based selection.
                    for matching in (0.90, 0.86, 0.82):
                        found = bot.find(label, matching=matching, waiting_time=1200, grayscale=True)
                        if found:
                            x = found.left + (found.width // 2)
                            y = found.top + (found.height // 2)
                            logger.info(
                                "BotCity template matched %s at (%d, %d) [matching=%.2f scale=%.2f variant=%s]",
                                template_path.name,
                                x,
                                y,
                                matching,
                                scale,
                                variant_name,
                            )
                            return (x, y)

                logger.warning("BotCity template fallback did not find notepad.png")
                return None
            finally:
                for temp_path in temporary_files:
                    try:
                        temp_path.unlink(missing_ok=True)
                    except Exception:
                        pass
        except Exception as exc:
            logger.warning("BotCity template fallback failed: %s", exc)
            return None

    @staticmethod
    def _opencv_template_fallback(
        template_path: Path,
        screenshot: Image.Image,
    ) -> tuple[int, int] | None:
        matches = VisionGrounder._opencv_template_candidates(
            template_path,
            screenshot,
            max_candidates=1,
        )
        if not matches:
            return None

        best = matches[0]
        logger.info(
            "OpenCV template matched notepad.png at (%d, %d) [score=%.2f]",
            best.x,
            best.y,
            best.score,
        )
        return (best.x, best.y)

    @staticmethod
    def _opencv_template_candidates(
        template_path: Path,
        screenshot: Image.Image,
        *,
        max_candidates: int = 6,
    ) -> list[TemplateMatch]:
        try:
            import cv2
            import numpy as np
        except Exception as exc:  # pragma: no cover - dependency/runtime specific
            logger.warning("OpenCV template fallback unavailable: %s", exc)
            return []

        template = cv2.imread(str(template_path), cv2.IMREAD_UNCHANGED)
        if template is None:
            logger.warning("OpenCV template fallback could not load %s", template_path)
            return []

        screen_bgr = cv2.cvtColor(np.array(screenshot.convert("RGB")), cv2.COLOR_RGB2BGR)
        screen_gray = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)

        if template.ndim == 3 and template.shape[2] == 4:
            template_gray = cv2.cvtColor(template[:, :, :3], cv2.COLOR_BGR2GRAY)
            template_mask = template[:, :, 3]
        elif template.ndim == 3:
            template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
            template_mask = None
        else:
            template_gray = template
            template_mask = None

        raw_matches: list[TemplateMatch] = []
        # Include very small scales so high-resolution web icon templates can
        # still match tiny desktop shortcut icons.
        scales = (0.06, 0.08, 0.10, 0.12, 0.16, 0.20, 0.25, 0.33, 0.50, 0.66, 0.75, 0.85, 1.0, 1.15, 1.30, 1.45)
        threshold = max(0.0, min(1.0, float(getattr(config, "TEMPLATE_MIN_SCORE", 0.46))))
        per_scale_peaks = 4

        for scale in scales:
            new_w = int(template_gray.shape[1] * scale)
            new_h = int(template_gray.shape[0] * scale)
            if new_w < 12 or new_h < 12:
                continue
            if new_w > screen_gray.shape[1] or new_h > screen_gray.shape[0]:
                continue

            interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
            resized_template = cv2.resize(template_gray, (new_w, new_h), interpolation=interpolation)

            if template_mask is not None:
                resized_mask = cv2.resize(template_mask, (new_w, new_h), interpolation=cv2.INTER_NEAREST)
                result = cv2.matchTemplate(
                    screen_gray,
                    resized_template,
                    cv2.TM_CCORR_NORMED,
                    mask=resized_mask,
                )
            else:
                result = cv2.matchTemplate(screen_gray, resized_template, cv2.TM_CCOEFF_NORMED)

            result_work = result.copy()
            for _ in range(per_scale_peaks):
                _, max_val, _, max_loc = cv2.minMaxLoc(result_work)
                score = float(max_val)
                if score < threshold:
                    break

                center_x = max_loc[0] + (new_w // 2)
                center_y = max_loc[1] + (new_h // 2)
                raw_matches.append(
                    TemplateMatch(
                        x=center_x,
                        y=center_y,
                        score=score,
                        width=new_w,
                        height=new_h,
                    )
                )

                suppress_left, suppress_top, suppress_right, suppress_bottom = (
                    VisionGrounder._template_suppression_bounds(
                        max_loc[0],
                        max_loc[1],
                        new_w,
                        new_h,
                        result_work.shape,
                    )
                )
                result_work[suppress_top:suppress_bottom, suppress_left:suppress_right] = -1.0

        if not raw_matches:
            logger.warning(
                "OpenCV template fallback did not find notepad.png (best_score=%.2f, threshold=%.2f)",
                float("-inf"),
                threshold,
            )
            return []

        raw_matches.sort(key=lambda item: item.score, reverse=True)
        unique_matches: list[TemplateMatch] = []
        min_distance_sq = 30 * 30
        for candidate in raw_matches:
            if any(
                ((candidate.x - existing.x) ** 2) + ((candidate.y - existing.y) ** 2)
                < min_distance_sq
                for existing in unique_matches
            ):
                continue
            unique_matches.append(candidate)
            if len(unique_matches) >= max(1, max_candidates):
                break

        best_match = unique_matches[0]

        if config.VISUAL_DEBUG:
            crop_half_w = max(48, min(160, best_match.width // 2))
            crop_half_h = max(48, min(160, best_match.height // 2))
            left = max(0, best_match.x - crop_half_w)
            top = max(0, best_match.y - crop_half_h)
            right = min(screenshot.width, best_match.x + crop_half_w)
            bottom = min(screenshot.height, best_match.y + crop_half_h)

            candidate = screenshot.crop((left, top, right, bottom))
            config.DEBUG_SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
            candidate_path = config.DEBUG_SCREENSHOTS_DIR / "template_candidate_notepad.png"
            candidate.save(candidate_path)
            logger.info("Saved template candidate crop: %s", candidate_path)

        logger.info(
            "OpenCV template produced %d candidate(s); best=(%d, %d) score=%.2f",
            len(unique_matches),
            best_match.x,
            best_match.y,
            best_match.score,
        )
        return unique_matches

    @staticmethod
    def _template_suppression_bounds(
        match_left: int,
        match_top: int,
        template_width: int,
        template_height: int,
        result_shape: tuple[int, int],
    ) -> tuple[int, int, int, int]:
        """Compute suppression bounds for a template match top-left coordinate."""
        suppress_left = max(0, match_left)
        suppress_top = max(0, match_top)
        suppress_right = min(result_shape[1], match_left + template_width)
        suppress_bottom = min(result_shape[0], match_top + template_height)
        return (suppress_left, suppress_top, suppress_right, suppress_bottom)

    # -- Full cascaded search (Phase 1 → 2 → 3) --

    def _full_cascaded_search(
        self, target: str, screenshot: Image.Image
    ) -> tuple[int, int]:
        """Run all three phases: region identification → precise location → verification."""
        regions = self._identify_regions(target, screenshot)
        if not regions:
            raise IconNotFoundError(f"No candidate regions found for '{target}'")

        # Sort by confidence descending
        regions.sort(key=lambda r: r.confidence, reverse=True)
        logger.info("Phase 1 found %d candidate region(s)", len(regions))

        candidates: list[Candidate] = []

        for i, region in enumerate(regions):
            bbox = (region.x1, region.y1, region.x2, region.y2)
            cropped = crop_region(screenshot, bbox)
            save_debug_crop(cropped, "1", i, f"region_{region.confidence:.0%}")

            candidate = self._locate_in_region(
                target, cropped, region,
                screen_size=(screenshot.width, screenshot.height),
            )
            if not candidate or candidate.confidence < config.PRECISE_MIN_CONFIDENCE:
                if config.ALLOW_HEURISTIC_REGION_FALLBACK:
                    fallback = self._fallback_candidate_from_region(region)
                    if self._verify_candidate(target, screenshot, fallback):
                        candidates.append(fallback)
                        logger.info(
                            "Using verified heuristic candidate from region at (%d, %d)",
                            fallback.x,
                            fallback.y,
                        )
                continue

            save_debug_crop(cropped, "2", i, f"precise_{candidate.x}_{candidate.y}")

            if self._verify_candidate(target, screenshot, candidate):
                candidates.append(candidate)
                logger.debug(
                    "Verified candidate at (%d, %d) conf=%.2f label='%s'",
                    candidate.x,
                    candidate.y,
                    candidate.confidence,
                    candidate.label,
                )

        if not candidates:
            raise IconNotFoundError(f"'{target}' not found after searching all regions")

        best = self._select_best_candidate(target, candidates)

        best_x, best_y = self._snap_to_visual_cluster(
            screenshot,
            best.x,
            best.y,
        )

        # Cache for stateful re-grounding
        self._last_known_coords = (best_x, best_y)
        self._last_region_bbox = best.region_bbox
        return (best_x, best_y)

    # -- Precise re-ground (Phase 2 → 3 only) --

    def _precise_reground(
        self, target: str, screenshot: Image.Image, verify: bool = False
    ) -> tuple[int, int]:
        """Crop around cached position and re-locate with Phase 2 + 3."""
        cx, cy = self._last_known_coords
        half = config.PRECISE_CROP_SIZE

        bbox = (
            max(0, cx - half),
            max(0, cy - half),
            min(screenshot.width, cx + half),
            min(screenshot.height, cy + half),
        )

        cropped = crop_region(screenshot, bbox)
        save_debug_crop(cropped, "P", 0, "precise_crop")

        region = Region(x1=bbox[0], y1=bbox[1], x2=bbox[2], y2=bbox[3], confidence=1.0)
        candidate = self._locate_in_region(
            target, cropped, region,
            screen_size=(screenshot.width, screenshot.height),
        )

        if not candidate or candidate.confidence < config.PRECISE_MIN_CONFIDENCE:
            fallback = Candidate(
                x=cx,
                y=cy,
                confidence=0.55,
                label="cached_position",
                region_bbox=bbox,
            )
            if verify and self._verify_candidate(target, screenshot, fallback):
                cx, cy = self._snap_to_visual_cluster(screenshot, cx, cy)
                self._last_region_bbox = bbox
                return (cx, cy)
            raise GroundingError("Precise re-ground: low confidence or not found")

        if verify and not self._verify_candidate(target, screenshot, candidate):
            raise GroundingError("Precise re-ground: verification failed")

        candidate.x, candidate.y = self._snap_to_visual_cluster(
            screenshot,
            candidate.x,
            candidate.y,
        )

        self._last_known_coords = (candidate.x, candidate.y)
        self._last_region_bbox = bbox
        return (candidate.x, candidate.y)

    # -- Phase implementations --

    def _direct_fullscreen_locate(
        self,
        target: str,
        screenshot: Image.Image,
    ) -> Candidate | None:
        """Fast-path exact location query on the full screenshot."""
        prompt = prompts.FULLSCREEN_LOCATION.format(
            width=screenshot.width,
            height=screenshot.height,
            target=target,
        )

        region = Region(
            x1=0,
            y1=0,
            x2=screenshot.width,
            y2=screenshot.height,
            confidence=1.0,
        )

        annotated_screenshot = draw_coordinate_grid(screenshot)

        return self._locate_in_region(
            target,
            annotated_screenshot,
            region,
            screen_size=(screenshot.width, screenshot.height),
            prompt_template=prompt,
        )

    def _verified_direct_fullscreen_locate(
        self,
        target: str,
        screenshot: Image.Image,
        attempts: int | None = None,
    ) -> tuple[int, int] | None:
        if attempts is None:
            attempts = max(1, config.DIRECT_FULLSCREEN_ATTEMPTS)

        for attempt in range(1, attempts + 1):
            candidate = self._direct_fullscreen_locate(target, screenshot)
            if candidate is None or candidate.confidence < config.PRECISE_MIN_CONFIDENCE:
                logger.warning(
                    "Direct full-screen locate attempt %d/%d returned no reliable candidate",
                    attempt,
                    attempts,
                )
                continue

            if not self._verify_candidate(target, screenshot, candidate):
                logger.warning(
                    "Direct full-screen locate attempt %d/%d failed verification at (%d, %d)",
                    attempt,
                    attempts,
                    candidate.x,
                    candidate.y,
                )
                continue

            candidate.x, candidate.y = self._snap_to_visual_cluster(
                screenshot,
                candidate.x,
                candidate.y,
            )

            self._last_known_coords = (candidate.x, candidate.y)
            self._last_region_bbox = candidate.region_bbox
            return (candidate.x, candidate.y)

        return None

    def _identify_regions(self, target: str, screenshot: Image.Image) -> list[Region]:
        """Phase 1: Ask MLLM to identify candidate regions in the full screenshot."""
        prompt = prompts.REGION_IDENTIFICATION.format(
            width=screenshot.width,
            height=screenshot.height,
            target=target,
        )

        data = self._query_mllm(prompt, screenshot)
        raw_regions = data.get("regions", [])

        regions = []
        for r in raw_regions:
            try:
                region = Region(
                    x1=max(0, min(int(r["x1"]), screenshot.width - 1)),
                    y1=max(0, min(int(r["y1"]), screenshot.height - 1)),
                    x2=max(1, min(int(r["x2"]), screenshot.width)),
                    y2=max(1, min(int(r["y2"]), screenshot.height)),
                    confidence=float(r.get("confidence", 0.5)),
                    reasoning=r.get("reasoning", ""),
                )
                # Sanity check: region must be within screen bounds and non-degenerate
                if region.x2 > region.x1 and region.y2 > region.y1:
                    regions.append(region)
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning("Skipping malformed region %s: %s", r, exc)

        return regions

    def _locate_in_region(
        self, target: str, cropped: Image.Image, region: Region,
        screen_size: tuple[int, int] = (1920, 1080),
        prompt_template: str | None = None,
    ) -> Candidate | None:
        """Phase 2: Ask MLLM for precise coordinates within a cropped region."""
        prompt = prompt_template or prompts.PRECISE_LOCATION.format(
            crop_w=cropped.width,
            crop_h=cropped.height,
            target=target,
        )

        data = self._query_mllm(prompt, cropped)

        try:
            local_x = int(data["x"])
            local_y = int(data["y"])
            confidence = float(data.get("confidence", 0))
            label = str(data.get("label", ""))
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("Malformed precise location response: %s", exc)
            return None

        if local_x < 0 or local_y < 0 or label == "not_found":
            return None

        screen_x = region.x1 + local_x
        screen_y = region.y1 + local_y

        screen_x = max(0, min(screen_x, screen_size[0] - 1))
        screen_y = max(0, min(screen_y, screen_size[1] - 1))

        return Candidate(
            x=screen_x,
            y=screen_y,
            confidence=confidence,
            label=label,
            region_bbox=(region.x1, region.y1, region.x2, region.y2),
        )

    def _verify_candidate(
        self, target: str, screenshot: Image.Image, candidate: Candidate
    ) -> bool:
        """Phase 3: Ask MLLM to confirm the detection is correct."""
        # Step 1: High-resolution zoom-crop verification
        zoom_size = 300
        zoom_bbox = (
            max(0, candidate.x - zoom_size // 2),
            max(0, candidate.y - zoom_size // 2),
            min(screenshot.width, candidate.x + zoom_size // 2),
            min(screenshot.height, candidate.y + zoom_size // 2),
        )
        zoomed = crop_region(screenshot, zoom_bbox)
        # Adjust candidate coords to be relative to the zoomed crop
        local_x = candidate.x - zoom_bbox[0]
        local_y = candidate.y - zoom_bbox[1]
        
        marked_crop = annotate_detection(
            zoomed,
            (local_x, local_y),
            label=f"Candidate: {target}",
        )
        save_debug_crop(marked_crop, "3", 0, f"verify_crop_{candidate.x}_{candidate.y}")

        prompt = prompts.VERIFICATION.format(
            det_x=local_x,
            det_y=local_y,
            target=target,
        )

        data = self._query_mllm(prompt, marked_crop)
        is_match = data.get("is_match", False)
        reasoning = data.get("reasoning", "")

        if not is_match:
            logger.debug("Crop verification failed: %s", reasoning)
            # Step 2: Fallback to full-screen verification if crop failed
            logger.info("Falling back to full-screen verification...")
            marked_full = annotate_detection(
                screenshot,
                (candidate.x, candidate.y),
                label=f"Candidate: {target}",
            )
            save_debug_crop(marked_full, "3", 1, f"verify_full_{candidate.x}_{candidate.y}")
            
            prompt_full = prompts.VERIFICATION.format(
                det_x=candidate.x,
                det_y=candidate.y,
                target=target,
            )
            data_full = self._query_mllm(prompt_full, marked_full)
            is_match = data_full.get("is_match", False)
            reasoning = data_full.get("reasoning", "")

        if is_match:
            logger.debug("Verification passed: %s", reasoning)
        else:
            logger.debug("Verification failed: %s", reasoning)

        return bool(is_match)

    # -- Candidate scoring --

    @staticmethod
    def _snap_to_visual_cluster(
        screenshot: Image.Image,
        approx_x: int,
        approx_y: int,
    ) -> tuple[int, int]:
        """Snap an approximate click point to the nearest visible desktop-item cluster."""
        max_axis_delta = 40
        max_cluster_width = 160
        max_cluster_height = 190
        left = max(0, approx_x - 220)
        top = max(0, approx_y - 60)
        right = min(screenshot.width, approx_x + 220)
        bottom = min(screenshot.height, approx_y + 260)

        crop = screenshot.crop((left, top, right, bottom)).convert("RGB")
        blurred = crop.filter(ImageFilter.GaussianBlur(radius=10))
        width, height = crop.size
        crop_pixels = crop.load()
        blurred_pixels = blurred.load()

        mask = [0] * (width * height)
        for cy in range(height):
            for cx in range(width):
                pixel = crop_pixels[cx, cy]
                blurred_pixel = blurred_pixels[cx, cy]
                delta = sum(abs(pixel[channel] - blurred_pixel[channel]) for channel in range(3))
                if delta > 45:
                    mask[(cy * width) + cx] = 1

        seen: set[int] = set()
        best_click = (approx_x, approx_y)
        best_score = float("-inf")

        for index, value in enumerate(mask):
            if not value or index in seen:
                continue

            queue = deque([index])
            seen.add(index)
            area = 0
            min_x = width
            min_y = height
            max_x = 0
            max_y = 0

            while queue:
                current = queue.popleft()
                area += 1
                cx = current % width
                cy = current // width
                min_x = min(min_x, cx)
                min_y = min(min_y, cy)
                max_x = max(max_x, cx)
                max_y = max(max_y, cy)

                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if 0 <= nx < width and 0 <= ny < height:
                        neighbor = (ny * width) + nx
                        if mask[neighbor] and neighbor not in seen:
                            seen.add(neighbor)
                            queue.append(neighbor)

            cluster_width = (max_x - min_x) + 1
            cluster_height = (max_y - min_y) + 1
            if area < 60:
                continue
            if cluster_width > max_cluster_width or cluster_height > max_cluster_height:
                continue

            abs_x1 = left + min_x
            abs_y1 = top + min_y
            abs_x2 = left + max_x
            abs_y2 = top + max_y
            center_x = abs_x1 + ((abs_x2 - abs_x1) // 2)
            center_y = abs_y1 + ((abs_y2 - abs_y1) // 2)
            score = area - (abs(center_x - approx_x) * 3) - (abs(center_y - approx_y) * 2)
            if score <= best_score:
                continue

            # Bias toward icon body rather than label baseline.
            y_offset = max(24, min((abs_y2 - abs_y1) // 2, 48))
            best_click = (center_x, min(abs_y2, abs_y1 + y_offset))
            best_score = score

        dx = abs(best_click[0] - approx_x)
        dy = abs(best_click[1] - approx_y)
        if dx > max_axis_delta or dy > max_axis_delta:
            logger.debug(
                "Rejected snap from (%d, %d) to (%d, %d): delta exceeds %dpx",  
                approx_x,
                approx_y,
                best_click[0],
                best_click[1],
                max_axis_delta,
            )
            return (approx_x, approx_y)
        if best_click != (approx_x, approx_y):
            logger.info(
                "Snapped approximate point (%d, %d) to visual cluster (%d, %d)",
                approx_x,
                approx_y,
                best_click[0],
                best_click[1],
            )
            save_debug_crop(crop, "S", 0, f"snap_{best_click[0]}_{best_click[1]}")

        return best_click

    @staticmethod
    def _fallback_candidate_from_region(region: Region) -> Candidate:
        """Estimate a click point from a candidate region when precise locate fails.

        Desktop icon regions usually include the icon in the upper portion and the
        label beneath it, so we bias the click toward the upper third instead of
        the full geometric center.
        """
        width = region.x2 - region.x1
        height = region.y2 - region.y1

        x = region.x1 + (width // 2)
        y_offset = max(12, min(height // 3, 48))
        y = min(region.y2 - 1, region.y1 + y_offset)

        return Candidate(
            x=x,
            y=y,
            confidence=max(0.35, region.confidence * 0.6),
            label="heuristic_region_center",
            region_bbox=(region.x1, region.y1, region.x2, region.y2),
        )

    def _select_best_candidate(self, target: str, candidates: list[Candidate]) -> Candidate:
        """Pick the best match from verified candidates.

        Prioritizes exact label match, then highest confidence.
        """
        # Prefer candidates whose label exactly matches (case-insensitive)
        target_lower = target.strip().lower()
        exact_matches = [c for c in candidates if c.label.strip().lower() == target_lower]
        pool = exact_matches if exact_matches else candidates

        return max(pool, key=lambda c: c.confidence)

    # -- MLLM communication --

    def _wait_for_mllm_slot(self) -> None:
        """Pace outbound MLLM calls so free-tier quotas are not exhausted immediately."""
        if config.DRY_RUN or config.MLLM_MIN_INTERVAL_SECONDS <= 0:
            return

        key_count = max(1, len(getattr(config, "GEMINI_API_KEYS", ()) or ()))
        effective_interval = config.MLLM_MIN_INTERVAL_SECONDS / key_count
        now = time.monotonic()
        elapsed = now - self._last_mllm_call_at
        remaining = effective_interval - elapsed
        if remaining > 0:
            logger.info("Waiting %.1fs before next MLLM call to respect rate limits", remaining)
            _RATE_LIMIT_EVENT.wait(remaining)

        self._last_mllm_call_at = time.monotonic()

    def _get_client(self) -> genai.Client:
        if config.DRY_RUN:
            raise RuntimeError("MLLM client is unavailable in DRY_RUN mode")

        key_manager = getattr(config, "GEMINI_KEY_MANAGER", None)
        if key_manager:
            api_key = key_manager.next_key()
        else:
            api_key = config.GOOGLE_API_KEY

        if not api_key:
            raise GroundingError("No Gemini API key configured")

        client = self._client_cache.get(api_key)
        if client is None:
            client = genai.Client(api_key=api_key)
            self._client_cache[api_key] = client

        return client

    @retry(
        max_attempts=config.MAX_RETRIES,
        backoff_base=config.BACKOFF_BASE,
        exceptions=(GroundingError,),
    )
    def _query_mllm(self, prompt: str, image: Image.Image) -> dict:
        """Send prompt + PIL.Image to Gemini, return parsed JSON dict."""
        if config.DRY_RUN:
            return self._mock_response(prompt)

        budget = config.MAX_MLLM_CALLS_PER_RUN
        if budget > 0 and self._mllm_calls_used >= budget:
            raise GroundingError(
                f"MLLM call budget exhausted ({self._mllm_calls_used}/{budget})"
            )

        try:
            self._wait_for_mllm_slot()
            client = self._get_client()
            response = client.models.generate_content(
                model=self._model,
                contents=[prompt, image],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
            self._mllm_calls_used += 1
            text = response.text or ""
        except Exception as exc:
            raise GroundingError(f"MLLM API call failed: {exc}") from exc

        # Parse JSON response
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Attempt to extract JSON from mixed text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            raise GroundingError(f"MLLM returned non-JSON: {text[:300]}")

    def analyze_popup(self, screenshot: Image.Image, window_title: str, process_name: str) -> dict:
        """Ask Gemini for a safe single-step dismissal action for an unexpected popup."""
        prompt = prompts.POPUP_RESOLUTION.format(
            window_title=window_title or "<unknown>",
            process_name=process_name or "<unknown>",
        )
        data = self._query_mllm(prompt, screenshot)
        action = str(data.get("action", "ignore")).strip().lower()
        if action not in {
            "ignore",
            "press_escape",
            "press_enter",
            "hotkey_alt_f4",
            "hotkey_alt_n",
        }:
            action = "ignore"
        return {
            "action": action,
            "reasoning": str(data.get("reasoning", "")),
        }

    @staticmethod
    def _mock_response(prompt: str) -> dict:
        """Return deterministic mock data for DRY_RUN testing."""
        lower = prompt.lower()
        if "regions" in lower:
            return {
                "regions": [
                    {
                        "x1": 50,
                        "y1": 50,
                        "x2": 350,
                        "y2": 350,
                        "confidence": 0.92,
                        "reasoning": "Mock: desktop icon area top-left",
                    }
                ]
            }
        if "full screenshot" in lower and "exact center" in lower:
            return {"x": 1280, "y": 455, "confidence": 0.96, "label": "Notepad"}
        if "exact center" in lower or "within this cropped" in lower:
            return {"x": 150, "y": 150, "confidence": 0.95, "label": "Notepad"}
        if "is_match" in lower or "verify" in lower:
            return {"is_match": True, "reasoning": "Mock: verified as Notepad"}
        return {}
