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
import time
from dataclasses import dataclass

from google import genai
from google.genai import types
from PIL import Image

from src import config
from src.core.exceptions import GroundingError, IconNotFoundError
from src.core.logger import get_logger
from src.core.retry import retry
from src.vision import prompts
from src.vision.annotator import annotate_detection, save_debug_crop
from src.vision.screenshot import crop_region

logger = get_logger(__name__)


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


class VisionGrounder:
    """Stateful cascaded visual search engine.

    Tracks last known icon position to optimize repeated searches.
    Falls back to full cascaded search when precise re-ground fails.
    """

    def __init__(self, model_name: str | None = None):
        self._model = model_name or config.GEMINI_MODEL

        if not config.DRY_RUN:
            self._client = genai.Client(api_key=config.GOOGLE_API_KEY)
        else:
            self._client = None

        self._last_known_coords: tuple[int, int] | None = None
        self._last_region_bbox: tuple[int, int, int, int] | None = None
        self._search_count = 0
        self._last_mllm_call_at = 0.0

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
                coords = self._precise_reground(target, screenshot)
                logger.info("Precise re-ground succeeded: (%d, %d)", *coords)
                return coords
            except GroundingError:
                logger.warning("Precise re-ground failed, falling back to full search")

        coords = self._full_cascaded_search(target, screenshot)
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
            if not candidate or candidate.confidence <= 0:
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

        # Cache for stateful re-grounding
        self._last_known_coords = (best.x, best.y)
        self._last_region_bbox = best.region_bbox
        return (best.x, best.y)

    # -- Precise re-ground (Phase 2 → 3 only) --

    def _precise_reground(
        self, target: str, screenshot: Image.Image
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

        if not candidate or candidate.confidence < 0.5:
            raise GroundingError("Precise re-ground: low confidence or not found")

        if not self._verify_candidate(target, screenshot, candidate):
            raise GroundingError("Precise re-ground: verification failed")

        self._last_known_coords = (candidate.x, candidate.y)
        self._last_region_bbox = bbox
        return (candidate.x, candidate.y)

    # -- Phase implementations --

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
    ) -> Candidate | None:
        """Phase 2: Ask MLLM for precise coordinates within a cropped region."""
        prompt = prompts.PRECISE_LOCATION.format(
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
        marked = annotate_detection(
            screenshot,
            (candidate.x, candidate.y),
            label=f"Candidate: {target}",
        )
        save_debug_crop(marked, "3", 0, f"verify_{candidate.x}_{candidate.y}")

        prompt = prompts.VERIFICATION.format(
            det_x=candidate.x,
            det_y=candidate.y,
            target=target,
        )

        data = self._query_mllm(prompt, marked)

        is_match = data.get("is_match", False)
        reasoning = data.get("reasoning", "")

        if is_match:
            logger.debug("Verification passed: %s", reasoning)
        else:
            logger.debug("Verification failed: %s", reasoning)

        return bool(is_match)

    # -- Candidate scoring --

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

        now = time.monotonic()
        elapsed = now - self._last_mllm_call_at
        remaining = config.MLLM_MIN_INTERVAL_SECONDS - elapsed
        if remaining > 0:
            logger.info("Waiting %.1fs before next MLLM call to respect rate limits", remaining)
            time.sleep(remaining)

        self._last_mllm_call_at = time.monotonic()

    @retry(
        max_attempts=config.MAX_RETRIES,
        backoff_base=config.BACKOFF_BASE,
        exceptions=(GroundingError,),
    )
    def _query_mllm(self, prompt: str, image: Image.Image) -> dict:
        """Send prompt + PIL.Image to Gemini, return parsed JSON dict."""
        if config.DRY_RUN:
            return self._mock_response(prompt)

        try:
            self._wait_for_mllm_slot()
            response = self._client.models.generate_content(
                model=self._model,
                contents=[prompt, image],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
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
        if "exact center" in lower or "within this cropped" in lower:
            return {"x": 150, "y": 150, "confidence": 0.95, "label": "Notepad"}
        if "is_match" in lower or "verify" in lower:
            return {"is_match": True, "reasoning": "Mock: verified as Notepad"}
        return {}
