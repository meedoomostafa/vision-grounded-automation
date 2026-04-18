from PIL import Image

from src import main as app_main
from src.core import logger as logger_module


def _build_posts(count: int) -> list[dict]:
    return [
        {
            "id": index,
            "title": f"Post {index}",
            "body": f"Body {index}",
        }
        for index in range(1, count + 1)
    ]


def test_grounding_mode_selection(monkeypatch):
    monkeypatch.setattr(app_main.config, "GROUNDING_MODE", "first")
    assert app_main._should_use_grounding_for_post(0) is True
    assert app_main._should_use_grounding_for_post(1) is False

    monkeypatch.setattr(app_main.config, "GROUNDING_MODE", "all")
    assert app_main._should_use_grounding_for_post(0) is True
    assert app_main._should_use_grounding_for_post(1) is True

    monkeypatch.setattr(app_main.config, "GROUNDING_MODE", "none")
    assert app_main._should_use_grounding_for_post(0) is False
    assert app_main._should_use_grounding_for_post(1) is False


def test_main_dry_run_e2e(monkeypatch, tmp_path):
    output_dir = tmp_path / "output"
    logs_dir = tmp_path / "logs"
    sample_posts = _build_posts(10)

    monkeypatch.setattr(app_main.config, "DRY_RUN", True)
    monkeypatch.setattr(app_main.config, "VISUAL_DEBUG", False)
    monkeypatch.setattr(app_main.config, "API_POSTS_LIMIT", 10)
    monkeypatch.setattr(app_main.config, "LAUNCH_STRATEGY", "cascade")
    monkeypatch.setattr(app_main.config, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(app_main.config, "LOGS_DIR", logs_dir)
    monkeypatch.setattr(app_main.config, "LOCK_FILE", tmp_path / ".automation.lock")
    monkeypatch.setattr(app_main, "fetch_posts", lambda limit: sample_posts[:limit])
    monkeypatch.setattr(
        app_main,
        "setup_logging",
        lambda: logger_module.setup_logging(force=True),
    )

    app_main.main()

    created_files = sorted(output_dir.glob("post_*.txt"))
    assert len(created_files) == 10
    assert created_files[0].read_text(encoding="utf-8").startswith("DRY_RUN placeholder")

    log_file = logs_dir / "automation.log"
    assert log_file.exists()
    log_text = log_file.read_text(encoding="utf-8")
    assert "Complete: 10 succeeded, 0 failed out of 10" in log_text


def test_first_post_grounding_failure_cascades_to_deterministic(monkeypatch):
    class DummyGrounder:
        def __init__(self):
            self.template_calls = 0

        def template_fallback(self, target, screenshot):
            self.template_calls += 1
            return None

        def reset_state(self):
            return None

    grounder = DummyGrounder()
    launch_calls: list[bool] = []
    write_calls: list[int] = []
    save_calls: list[int] = []
    close_calls: list[bool] = []

    def _raise_grounding(*_args, **_kwargs):
        raise app_main.GroundingError("forced grounding failure")

    monkeypatch.setattr(app_main.config, "SETTLE_DELAY", 0.0)
    monkeypatch.setattr(app_main.config, "WINDOW_TIMEOUT", 1)
    monkeypatch.setattr(app_main.config, "LAUNCH_STRATEGY", "cascade")
    monkeypatch.setattr(app_main, "_capture_grounded_target", _raise_grounding)
    monkeypatch.setattr("src.vision.screenshot.capture_screen", lambda: Image.new("RGB", (200, 120), "black"))

    monkeypatch.setattr("src.automation.desktop.show_desktop", lambda: None)
    monkeypatch.setattr("src.automation.desktop.click", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("src.automation.desktop.double_click", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("src.automation.desktop.press", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("src.automation.desktop.wait_ms", lambda *_args, **_kwargs: None)

    monkeypatch.setattr("src.automation.window.wait_for_window", lambda *_args, **_kwargs: False)
    monkeypatch.setattr("src.automation.window.activate_window", lambda *_args, **_kwargs: True)

    def _launch_notepad_process():
        launch_calls.append(True)
        return True

    monkeypatch.setattr("src.automation.notepad.launch_notepad_process", _launch_notepad_process)
    monkeypatch.setattr("src.automation.notepad.write_post", lambda post: write_calls.append(post["id"]))
    monkeypatch.setattr("src.automation.notepad.save_post", lambda post_id: save_calls.append(post_id))
    monkeypatch.setattr("src.automation.notepad.close_notepad", lambda: close_calls.append(True))
    monkeypatch.setattr(app_main, "launch_notepad_process", _launch_notepad_process)
    monkeypatch.setattr(app_main, "write_post", lambda post: write_calls.append(post["id"]))
    monkeypatch.setattr(app_main, "save_post", lambda post_id: save_calls.append(post_id))
    monkeypatch.setattr(app_main, "close_notepad", lambda: close_calls.append(True))

    app_main._process_single_post(
        grounder,
        {"id": 1, "title": "t", "body": "b"},
        index=0,
        use_grounding=True,
    )

    assert grounder.template_calls == 1
    assert len(launch_calls) == 1
    assert write_calls == [1]
    assert save_calls == [1]
    assert len(close_calls) == 1


def test_first_post_grounding_failure_uses_template_before_deterministic(monkeypatch):
    class DummyGrounder:
        def __init__(self):
            self.template_calls = 0

        def template_fallback(self, target, screenshot):
            self.template_calls += 1
            return (88, 66)

        def reset_state(self):
            return None

    grounder = DummyGrounder()
    launch_calls: list[bool] = []
    dblclick_calls: list[tuple[int, int]] = []

    def _raise_grounding(*_args, **_kwargs):
        raise app_main.GroundingError("forced grounding failure")

    monkeypatch.setattr(app_main.config, "SETTLE_DELAY", 0.0)
    monkeypatch.setattr(app_main.config, "WINDOW_TIMEOUT", 1)
    monkeypatch.setattr(app_main.config, "LAUNCH_STRATEGY", "cascade")
    monkeypatch.setattr(app_main, "_capture_grounded_target", _raise_grounding)
    monkeypatch.setattr("src.vision.screenshot.capture_screen", lambda: Image.new("RGB", (200, 120), "black"))

    monkeypatch.setattr("src.automation.desktop.show_desktop", lambda: None)
    monkeypatch.setattr("src.automation.desktop.click", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "src.automation.desktop.double_click",
        lambda x, y, **_kwargs: dblclick_calls.append((x, y)),
    )
    monkeypatch.setattr("src.automation.desktop.press", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("src.automation.desktop.wait_ms", lambda *_args, **_kwargs: None)

    monkeypatch.setattr("src.automation.window.wait_for_window", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("src.automation.window.activate_window", lambda *_args, **_kwargs: True)

    def _launch_notepad_process():
        launch_calls.append(True)
        return True

    monkeypatch.setattr("src.automation.notepad.launch_notepad_process", _launch_notepad_process)
    monkeypatch.setattr("src.automation.notepad.write_post", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("src.automation.notepad.save_post", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("src.automation.notepad.close_notepad", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_main, "launch_notepad_process", _launch_notepad_process)
    monkeypatch.setattr(app_main, "write_post", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_main, "save_post", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_main, "close_notepad", lambda *_args, **_kwargs: None)

    app_main._process_single_post(
        grounder,
        {"id": 1, "title": "t", "body": "b"},
        index=0,
        use_grounding=True,
    )

    assert grounder.template_calls == 1
    assert dblclick_calls == [(88, 66)]
    assert len(launch_calls) == 0


def test_template_only_strategy_uses_botcity_path(monkeypatch):
    class DummyGrounder:
        def __init__(self):
            self.template_calls = 0

        def template_fallback(self, target, screenshot):
            self.template_calls += 1
            return (101, 202)

        def reset_state(self):
            return None

    grounder = DummyGrounder()
    launch_calls: list[bool] = []
    click_calls: list[tuple[int, int]] = []
    press_calls: list[str] = []
    dblclick_calls: list[tuple[int, int]] = []

    monkeypatch.setattr(app_main.config, "SETTLE_DELAY", 0.0)
    monkeypatch.setattr(app_main.config, "WINDOW_TIMEOUT", 1)
    monkeypatch.setattr(app_main.config, "LAUNCH_STRATEGY", "template_only")
    monkeypatch.setattr("src.vision.screenshot.capture_screen", lambda: Image.new("RGB", (200, 120), "black"))

    monkeypatch.setattr("src.automation.desktop.show_desktop", lambda: None)
    monkeypatch.setattr(
        "src.automation.desktop.click",
        lambda x, y, **_kwargs: click_calls.append((x, y)),
    )
    monkeypatch.setattr("src.automation.desktop.press", lambda key: press_calls.append(key))
    monkeypatch.setattr(
        "src.automation.desktop.double_click",
        lambda x, y, **_kwargs: dblclick_calls.append((x, y)),
    )
    monkeypatch.setattr("src.automation.desktop.wait_ms", lambda *_args, **_kwargs: None)

    monkeypatch.setattr("src.automation.window.wait_for_window", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("src.automation.window.activate_window", lambda *_args, **_kwargs: True)

    def _launch_notepad_process():
        launch_calls.append(True)
        return True

    monkeypatch.setattr(app_main, "launch_notepad_process", _launch_notepad_process)
    monkeypatch.setattr(app_main, "write_post", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_main, "save_post", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_main, "close_notepad", lambda *_args, **_kwargs: None)

    app_main._process_single_post(
        grounder,
        {"id": 1, "title": "t", "body": "b"},
        index=0,
        use_grounding=True,
    )

    assert grounder.template_calls == 1
    assert click_calls == [(101, 202)]
    assert press_calls == ["enter"]
    assert dblclick_calls == []
    assert len(launch_calls) == 0


def test_template_only_strategy_tries_next_candidate_after_false_positive(monkeypatch):
    class DummyGrounder:
        def __init__(self):
            self.template_candidate_calls: list[bool] = []

        def template_fallback_candidates(self, target, screenshot, use_botcity=True, max_candidates=6):
            self.template_candidate_calls.append(bool(use_botcity))
            if use_botcity:
                return [(101, 202), (303, 404)]
            return []

        def reset_state(self):
            return None

    grounder = DummyGrounder()
    launch_calls: list[bool] = []
    click_calls: list[tuple[int, int]] = []
    press_calls: list[str] = []
    dblclick_calls: list[tuple[int, int]] = []

    monkeypatch.setattr(app_main.config, "SETTLE_DELAY", 0.0)
    monkeypatch.setattr(app_main.config, "WINDOW_TIMEOUT", 1)
    monkeypatch.setattr(app_main.config, "LAUNCH_STRATEGY", "template_only")
    monkeypatch.setattr("src.vision.screenshot.capture_screen", lambda: Image.new("RGB", (200, 120), "black"))

    monkeypatch.setattr("src.automation.desktop.show_desktop", lambda: None)
    monkeypatch.setattr(
        "src.automation.desktop.click",
        lambda x, y, **_kwargs: click_calls.append((x, y)),
    )
    monkeypatch.setattr("src.automation.desktop.press", lambda key: press_calls.append(key))
    monkeypatch.setattr(
        "src.automation.desktop.double_click",
        lambda x, y, **_kwargs: dblclick_calls.append((x, y)),
    )
    monkeypatch.setattr("src.automation.desktop.wait_ms", lambda *_args, **_kwargs: None)

    def _wait_for_window(*_args, **_kwargs):
        return bool(click_calls and click_calls[-1] == (303, 404))

    monkeypatch.setattr("src.automation.window.wait_for_window", _wait_for_window)
    monkeypatch.setattr("src.automation.window.activate_window", lambda *_args, **_kwargs: True)

    def _launch_notepad_process():
        launch_calls.append(True)
        return True

    monkeypatch.setattr(app_main, "launch_notepad_process", _launch_notepad_process)
    monkeypatch.setattr(app_main, "write_post", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_main, "save_post", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_main, "close_notepad", lambda *_args, **_kwargs: None)

    app_main._process_single_post(
        grounder,
        {"id": 1, "title": "t", "body": "b"},
        index=0,
        use_grounding=True,
    )

    assert grounder.template_candidate_calls == [True]
    assert click_calls == [(101, 202), (101, 182), (303, 404)]
    assert press_calls == ["enter", "enter", "enter"]
    assert dblclick_calls == [(101, 202), (101, 182)]
    assert len(launch_calls) == 0


def test_template_only_strategy_skips_known_non_notepad_icon_candidates(monkeypatch):
    class DummyGrounder:
        def template_fallback_candidates(self, target, screenshot, use_botcity=True, max_candidates=6):
            return [(900, 430)]

        def reset_state(self):
            return None

    grounder = DummyGrounder()
    click_calls: list[tuple[int, int]] = []
    press_calls: list[str] = []
    dblclick_calls: list[tuple[int, int]] = []

    monkeypatch.setattr(app_main.config, "SETTLE_DELAY", 0.0)
    monkeypatch.setattr(app_main.config, "WINDOW_TIMEOUT", 1)
    monkeypatch.setattr(app_main.config, "LAUNCH_STRATEGY", "template_only")
    monkeypatch.setattr("src.vision.screenshot.capture_screen", lambda: Image.new("RGB", (200, 120), "black"))

    monkeypatch.setattr(
        "src.automation.desktop.list_desktop_icons",
        lambda: [
            ("output", (860, 400, 940, 480)),
            ("Notepad", (760, 525, 854, 612)),
        ],
    )

    monkeypatch.setattr("src.automation.desktop.show_desktop", lambda: None)
    monkeypatch.setattr(
        "src.automation.desktop.click",
        lambda x, y, **_kwargs: click_calls.append((x, y)),
    )
    monkeypatch.setattr("src.automation.desktop.press", lambda key: press_calls.append(key))
    monkeypatch.setattr(
        "src.automation.desktop.double_click",
        lambda x, y, **_kwargs: dblclick_calls.append((x, y)),
    )
    monkeypatch.setattr("src.automation.desktop.wait_ms", lambda *_args, **_kwargs: None)

    def _wait_for_window(*_args, **_kwargs):
        return bool(click_calls and click_calls[-1] == (807, 568))

    monkeypatch.setattr("src.automation.window.wait_for_window", _wait_for_window)
    monkeypatch.setattr("src.automation.window.activate_window", lambda *_args, **_kwargs: True)

    monkeypatch.setattr(app_main, "write_post", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_main, "save_post", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_main, "close_notepad", lambda *_args, **_kwargs: None)

    app_main._process_single_post(
        grounder,
        {"id": 1, "title": "t", "body": "b"},
        index=0,
        use_grounding=True,
    )

    assert click_calls == [(807, 568)]
    assert press_calls == ["enter"]
    assert dblclick_calls == []


def test_template_only_strategy_injects_notepad_center_for_unknown_candidates(monkeypatch):
    class DummyGrounder:
        def template_fallback_candidates(self, target, screenshot, use_botcity=True, max_candidates=6):
            return [(120, 120)]

        def reset_state(self):
            return None

    grounder = DummyGrounder()
    click_calls: list[tuple[int, int]] = []
    press_calls: list[str] = []

    monkeypatch.setattr(app_main.config, "SETTLE_DELAY", 0.0)
    monkeypatch.setattr(app_main.config, "WINDOW_TIMEOUT", 1)
    monkeypatch.setattr(app_main.config, "LAUNCH_STRATEGY", "template_only")
    monkeypatch.setattr("src.vision.screenshot.capture_screen", lambda: Image.new("RGB", (200, 120), "black"))

    monkeypatch.setattr(
        "src.automation.desktop.list_desktop_icons",
        lambda: [
            ("output", (860, 400, 940, 480)),
            ("Notepad", (760, 525, 854, 612)),
        ],
    )

    monkeypatch.setattr("src.automation.desktop.show_desktop", lambda: None)
    monkeypatch.setattr(
        "src.automation.desktop.click",
        lambda x, y, **_kwargs: click_calls.append((x, y)),
    )
    monkeypatch.setattr("src.automation.desktop.press", lambda key: press_calls.append(key))
    monkeypatch.setattr("src.automation.desktop.double_click", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("src.automation.desktop.wait_ms", lambda *_args, **_kwargs: None)

    def _wait_for_window(*_args, **_kwargs):
        return bool(click_calls and click_calls[-1] == (807, 568))

    monkeypatch.setattr("src.automation.window.wait_for_window", _wait_for_window)
    monkeypatch.setattr("src.automation.window.activate_window", lambda *_args, **_kwargs: True)

    monkeypatch.setattr(app_main, "write_post", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_main, "save_post", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_main, "close_notepad", lambda *_args, **_kwargs: None)

    app_main._process_single_post(
        grounder,
        {"id": 1, "title": "t", "body": "b"},
        index=0,
        use_grounding=True,
    )

    assert click_calls == [(807, 568)]
    assert press_calls == ["enter"]
