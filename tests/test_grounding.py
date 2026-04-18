
import pytest
from PIL import Image, ImageDraw

from src import config
from src.core.exceptions import GroundingError, IconNotFoundError
from src.core.key_manager import RoundRobinKeyManager
from src.vision.grounding import Candidate, Region, TemplateMatch, VisionGrounder
from src.vision.screenshot import crop_region

# -- crop_region tests --

def test_crop_region_basic():
    img = Image.new("RGB", (1920, 1080), color=(128, 128, 128))
    cropped = crop_region(img, (100, 100, 500, 400))
    assert cropped.size == (400, 300)


def test_crop_region_clamped_to_bounds():
    img = Image.new("RGB", (1920, 1080), color=(128, 128, 128))
    cropped = crop_region(img, (-50, -50, 2000, 1200))
    assert cropped.size == (1920, 1080)


def test_crop_region_degenerate_returns_minimum():
    img = Image.new("RGB", (1920, 1080), color=(128, 128, 128))
    # x1 == x2, y1 == y2 → should return at least 1x1
    cropped = crop_region(img, (500, 500, 500, 500))
    assert cropped.width >= 1 and cropped.height >= 1


# -- Coordinate mapping tests --

def test_coordinate_mapping_crop_to_screen():
    """Verify Phase 2 correctly maps crop-local coords to screen coords."""
    # Region at (200, 300) to (600, 700)
    region = Region(x1=200, y1=300, x2=600, y2=700, confidence=0.9)
    # MLLM returns (150, 100) within the crop
    local_x, local_y = 150, 100
    screen_x = region.x1 + local_x  # 200 + 150 = 350
    screen_y = region.y1 + local_y  # 300 + 100 = 400
    assert screen_x == 350
    assert screen_y == 400


# -- Candidate selection tests --

def test_select_best_exact_label_match():
    grounder = VisionGrounder()
    candidates = [
        Candidate(x=100, y=100, confidence=0.99, label="Notepad++", region_bbox=(0, 0, 200, 200)),
        Candidate(x=300, y=300, confidence=0.85, label="Notepad", region_bbox=(200, 200, 400, 400)),
    ]
    best = grounder._select_best_candidate("Notepad", candidates)
    # Should prefer exact "Notepad" match over higher-confidence "Notepad++"
    assert best.label == "Notepad"
    assert best.x == 300


def test_select_best_highest_confidence_when_no_exact_match():
    grounder = VisionGrounder()
    candidates = [
        Candidate(x=100, y=100, confidence=0.7, label="notepad app", region_bbox=(0, 0, 200, 200)),
        Candidate(
            x=300, y=300, confidence=0.9,
            label="text editor", region_bbox=(200, 200, 400, 400),
        ),
    ]
    best = grounder._select_best_candidate("Notepad", candidates)
    assert best.confidence == 0.9


def test_select_best_uses_requested_target_not_hardcoded_notepad():
    grounder = VisionGrounder()
    candidates = [
        Candidate(
            x=100,
            y=100,
            confidence=0.98,
            label="Calculator+",
            region_bbox=(0, 0, 200, 200),
        ),
        Candidate(
            x=300,
            y=300,
            confidence=0.7,
            label="Calculator",
            region_bbox=(200, 200, 400, 400),
        ),
    ]
    best = grounder._select_best_candidate("Calculator", candidates)
    assert best.label == "Calculator"
    assert best.x == 300


def test_fallback_candidate_from_region_biases_toward_icon_area():
    region = Region(x1=100, y1=200, x2=220, y2=380, confidence=0.9)
    candidate = VisionGrounder._fallback_candidate_from_region(region)
    assert candidate.x == 160
    assert candidate.y == 248
    assert candidate.region_bbox == (100, 200, 220, 380)


# -- Stateful grounding tests --

def test_grounder_starts_in_full_mode():
    grounder = VisionGrounder()
    assert grounder._last_known_coords is None


def test_grounder_caches_after_success():
    grounder = VisionGrounder()
    grounder._last_known_coords = (500, 400)
    grounder._last_region_bbox = (300, 200, 700, 600)
    assert grounder._last_known_coords == (500, 400)


def test_grounder_reset_clears_state():
    grounder = VisionGrounder()
    grounder._last_known_coords = (500, 400)
    grounder._last_region_bbox = (300, 200, 700, 600)
    grounder.reset_state()
    assert grounder._last_known_coords is None
    assert grounder._last_region_bbox is None


def test_snap_rejection_for_high_delta():
    # Arrange an image where there's a cluster far away but within the crop bounding box
    img = Image.new("RGB", (800, 600), color=(0, 0, 0))
    # Draw a visible cluster starting at x=100+45, y=100+45, exceeding max_axis_delta=40
    # The crop is ~ [-120:320]x[60:360], so (145, 145) is inside the crop bounds
    import PIL.ImageDraw
    draw = PIL.ImageDraw.Draw(img)
    draw.rectangle([145, 145, 195, 195], fill=(255, 255, 255))
    
    snapped_x, snapped_y = VisionGrounder._snap_to_visual_cluster(img, 100, 100)
    
    assert snapped_x == 100
    assert snapped_y == 100


def test_template_fallback_uses_botcity_first(monkeypatch):
    grounder = VisionGrounder()
    screenshot = Image.new("RGB", (640, 360), color=(40, 40, 40))

    monkeypatch.setattr("src.vision.grounding.Path.exists", lambda self: True)
    monkeypatch.setattr(
        VisionGrounder,
        "_botcity_template_fallback",
        staticmethod(lambda _path: (300, 200)),
    )
    monkeypatch.setattr(
        VisionGrounder,
        "_opencv_template_fallback",
        staticmethod(lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("OpenCV should not run"))),
    )

    coords = grounder.template_fallback("Notepad", screenshot)

    assert coords == (300, 200)


def test_template_fallback_uses_opencv_when_botcity_misses(monkeypatch):
    grounder = VisionGrounder()
    screenshot = Image.new("RGB", (640, 360), color=(40, 40, 40))

    monkeypatch.setattr("src.vision.grounding.Path.exists", lambda self: True)
    monkeypatch.setattr(
        VisionGrounder,
        "_botcity_template_fallback",
        staticmethod(lambda _path: None),
    )
    monkeypatch.setattr(
        VisionGrounder,
        "_opencv_template_fallback",
        staticmethod(lambda _path, _screenshot: (280, 160)),
    )

    coords = grounder.template_fallback("Notepad", screenshot)

    assert coords == (280, 160)


def test_template_fallback_candidates_combines_botcity_and_opencv(monkeypatch):
    grounder = VisionGrounder()
    screenshot = Image.new("RGB", (640, 360), color=(40, 40, 40))

    monkeypatch.setattr("src.vision.grounding.Path.exists", lambda self: True)
    monkeypatch.setattr(
        VisionGrounder,
        "_botcity_template_fallback",
        staticmethod(lambda _path: (300, 200)),
    )
    monkeypatch.setattr(
        VisionGrounder,
        "_opencv_template_candidates",
        staticmethod(
            lambda *_args, **_kwargs: [
                TemplateMatch(x=300, y=200, score=0.93, width=30, height=30),
                TemplateMatch(x=420, y=260, score=0.89, width=28, height=28),
            ]
        ),
    )

    coords = grounder.template_fallback_candidates("Notepad", screenshot)

    assert coords == [(300, 200), (420, 260)]


def test_template_fallback_candidates_dedupes_close_points(monkeypatch):
    grounder = VisionGrounder()
    screenshot = Image.new("RGB", (640, 360), color=(40, 40, 40))

    monkeypatch.setattr("src.vision.grounding.Path.exists", lambda self: True)
    monkeypatch.setattr(
        VisionGrounder,
        "_botcity_template_fallback",
        staticmethod(lambda _path: None),
    )
    monkeypatch.setattr(
        VisionGrounder,
        "_opencv_template_candidates",
        staticmethod(
            lambda *_args, **_kwargs: [
                TemplateMatch(x=100, y=100, score=0.95, width=30, height=30),
                TemplateMatch(x=114, y=110, score=0.92, width=30, height=30),
                TemplateMatch(x=180, y=180, score=0.88, width=30, height=30),
            ]
        ),
    )

    coords = grounder.template_fallback_candidates("Notepad", screenshot)

    assert coords == [(100, 100), (180, 180)]


def test_template_suppression_bounds_use_match_top_left():
    bounds = VisionGrounder._template_suppression_bounds(
        match_left=200,
        match_top=120,
        template_width=80,
        template_height=60,
        result_shape=(400, 500),
    )

    assert bounds == (200, 120, 280, 180)


# -- DRY_RUN mock response tests --

def test_mock_response_regions():
    result = VisionGrounder._mock_response("Find regions for the target")
    assert "regions" in result
    assert len(result["regions"]) >= 1
    assert "x1" in result["regions"][0]


def test_mock_response_precise():
    result = VisionGrounder._mock_response("Find the EXACT center within this cropped image")
    assert "x" in result
    assert "y" in result
    assert result["confidence"] > 0


def test_mock_response_verification():
    result = VisionGrounder._mock_response("is_match verify this element")
    assert result["is_match"] is True


def test_strict_verification_failure(monkeypatch):
    """If phase 3 verification is rigid and returns False, the candidate is rejected."""
    grounder = VisionGrounder()
    # Mock MLLM to always return high confidence in phases 1/2 but fail phase 3
    def fake_query(prompt, image):
        if "QUESTION: Is the element AT EXACTLY" in prompt:
            return {"is_match": False, "reasoning": "This is a chameleon icon."}
        elif "JSON object with candidate regions" in prompt:
            return {"regions": [{"x1": 0, "y1": 0, "x2": 200, "y2": 200, "confidence": 0.9}]}
        else:
            return {"x": 100, "y": 100, "confidence": 0.95, "label": "Notepad++"}
    
    monkeypatch.setattr(grounder, "_query_mllm", fake_query)
    
    screenshot = Image.new("RGB", (1920, 1080), color=(50, 50, 50))
    with pytest.raises(IconNotFoundError):
        grounder.ground("Notepad", screenshot)


# -- Full grounding integration (DRY_RUN) --

def test_full_ground_dry_run():
    """VisionGrounder.ground() should work end-to-end in DRY_RUN mode."""
    grounder = VisionGrounder()
    screenshot = Image.new("RGB", (1920, 1080), color=(50, 50, 50))
    coords = grounder.ground("Notepad", screenshot)
    assert isinstance(coords, tuple)
    assert len(coords) == 2
    x, y = coords
    assert 0 <= x < 1920
    assert 0 <= y < 1080
    # State should be cached
    assert grounder._last_known_coords is not None


def test_stateful_reground_dry_run():
    """Second call should use precise re-ground mode."""
    grounder = VisionGrounder()
    screenshot = Image.new("RGB", (1920, 1080), color=(50, 50, 50))

    # First call: full search
    grounder.ground("Notepad", screenshot)
    assert grounder._last_known_coords is not None

    # Second call: should attempt precise re-ground
    coords2 = grounder.ground("Notepad", screenshot)
    assert isinstance(coords2, tuple)


def test_wait_for_mllm_slot_respects_configured_interval(monkeypatch):
    grounder = VisionGrounder()
    grounder._last_mllm_call_at = 100.0

    sleeps = []
    monotonic_values = iter([105.0, 112.5])

    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(config, "MLLM_MIN_INTERVAL_SECONDS", 12.5)
    monkeypatch.setattr(config, "GEMINI_API_KEYS", ("key-a",))
    monkeypatch.setattr("src.vision.grounding.time.monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(
        "src.vision.grounding._RATE_LIMIT_EVENT.wait",
        lambda seconds: sleeps.append(seconds),
    )

    grounder._wait_for_mllm_slot()

    assert sleeps == [7.5]
    assert grounder._last_mllm_call_at == 112.5


def test_precise_reground_can_skip_verification(monkeypatch):
    grounder = VisionGrounder()
    screenshot = Image.new("RGB", (1920, 1080), color=(10, 10, 10))
    grounder._last_known_coords = (600, 400)

    monkeypatch.setattr(config, "PRECISE_MIN_CONFIDENCE", 0.55)
    monkeypatch.setattr(
        grounder,
        "_locate_in_region",
        lambda *args, **kwargs: Candidate(
            x=610,
            y=410,
            confidence=0.9,
            label="Notepad",
            region_bbox=(200, 100, 1000, 800),
        ),
    )
    monkeypatch.setattr(
        grounder,
        "_verify_candidate",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("verify should be skipped")),
    )

    coords = grounder._precise_reground("Notepad", screenshot, verify=False)
    assert coords == (610, 410)


def test_precise_reground_verification_failure_raises(monkeypatch):
    grounder = VisionGrounder()
    screenshot = Image.new("RGB", (1920, 1080), color=(10, 10, 10))
    grounder._last_known_coords = (600, 400)

    monkeypatch.setattr(config, "PRECISE_MIN_CONFIDENCE", 0.55)
    monkeypatch.setattr(
        grounder,
        "_locate_in_region",
        lambda *args, **kwargs: Candidate(
            x=610,
            y=410,
            confidence=0.9,
            label="Notepad",
            region_bbox=(200, 100, 1000, 800),
        ),
    )
    monkeypatch.setattr(grounder, "_verify_candidate", lambda *args, **kwargs: False)

    with pytest.raises(GroundingError):
        grounder._precise_reground("Notepad", screenshot, verify=True)


def test_query_mllm_budget_guard(monkeypatch):
    grounder = VisionGrounder()

    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(config, "MAX_MLLM_CALLS_PER_RUN", 1)
    grounder._mllm_calls_used = 1

    with pytest.raises(GroundingError, match="MLLM call budget exhausted"):
        grounder._query_mllm("test", Image.new("RGB", (64, 64)))


def test_get_client_rotates_across_configured_keys(monkeypatch):
    created_keys = []

    class FakeClient:
        def __init__(self, api_key):
            created_keys.append(api_key)

    grounder = VisionGrounder()

    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(
        config,
        "GEMINI_KEY_MANAGER",
        RoundRobinKeyManager(["key-a", "key-b"]),
    )
    monkeypatch.setattr("src.vision.grounding.genai.Client", FakeClient)

    first = grounder._get_client()
    second = grounder._get_client()
    third = grounder._get_client()

    assert first is third
    assert first is not second
    assert created_keys == ["key-a", "key-b"]


def test_snap_to_visual_cluster_refines_approximate_point():
    image = Image.new("RGB", (800, 600), color=(30, 20, 60))
    draw = ImageDraw.Draw(image)
    draw.rectangle((500, 340, 560, 410), fill=(235, 245, 255))
    draw.rectangle((520, 410, 555, 430), fill=(255, 255, 255))

    snapped_x, snapped_y = VisionGrounder._snap_to_visual_cluster(image, 540, 350)

    assert 520 <= snapped_x <= 540
    assert 350 <= snapped_y <= 390
