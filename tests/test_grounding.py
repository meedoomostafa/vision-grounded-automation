import pytest
from PIL import Image, ImageDraw

from src import config
from src.core.exceptions import GroundingError
from src.core.key_manager import RoundRobinKeyManager
from src.vision.grounding import Candidate, Region, VisionGrounder
from src.vision.screenshot import crop_region

                         

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
                                                     
    cropped = crop_region(img, (500, 500, 500, 500))
    assert cropped.width >= 1 and cropped.height >= 1


                                

def test_coordinate_mapping_crop_to_screen():
                                        
    region = Region(x1=200, y1=300, x2=600, y2=700, confidence=0.9)
                                             
    local_x, local_y = 150, 100
    screen_x = region.x1 + local_x                   
    screen_y = region.y1 + local_y                   
    assert screen_x == 350
    assert screen_y == 400


                                 

def test_select_best_exact_label_match():
    grounder = VisionGrounder()
    candidates = [
        Candidate(x=100, y=100, confidence=0.99, label="Notepad++", region_bbox=(0, 0, 200, 200)),
        Candidate(x=300, y=300, confidence=0.85, label="Notepad", region_bbox=(200, 200, 400, 400)),
    ]
    best = grounder._select_best_candidate("Notepad", candidates)
                                                                            
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


                                            

def test_full_ground_dry_run():
    grounder = VisionGrounder()
    screenshot = Image.new("RGB", (1920, 1080), color=(50, 50, 50))
    coords = grounder.ground("Notepad", screenshot)
    assert isinstance(coords, tuple)
    assert len(coords) == 2
    x, y = coords
    assert 0 <= x < 1920
    assert 0 <= y < 1080
                            
    assert grounder._last_known_coords is not None


def test_stateful_reground_dry_run():
    grounder = VisionGrounder()
    screenshot = Image.new("RGB", (1920, 1080), color=(50, 50, 50))

                             
    grounder.ground("Notepad", screenshot)
    assert grounder._last_known_coords is not None

                                                   
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

    snapped_x, snapped_y = VisionGrounder._snap_to_visual_cluster(image, 540, 220)

    assert 520 <= snapped_x <= 540
    assert 350 <= snapped_y <= 390
