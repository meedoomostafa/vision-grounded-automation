from pathlib import Path

from src.core.settings import load_settings


def test_load_settings_uses_pathlib_and_multi_key_env(tmp_path):
    env = {
        "AI__Gemini__ApiKeys__0": "key-a",
        "AI__Gemini__ApiKeys__1": "key-b",
        "OUTPUT_FOLDER": "generated-posts",
        "DRY_RUN": "true",
        "VISUAL_DEBUG": "true",
        "LOG_LEVEL": "debug",
        "GEMINI_MODEL": "gemini-2.5-flash",
    }

    settings = load_settings(env, project_root=tmp_path)

    assert settings.paths.project_root == tmp_path
    assert settings.paths.logs_dir == tmp_path / "logs"
    assert settings.paths.screenshots_dir == tmp_path / "screenshots"
    assert settings.paths.debug_screenshots_dir == tmp_path / "screenshots" / "debug"
    assert settings.paths.lock_file == tmp_path / ".automation.lock"
    assert settings.paths.output_dir.name == "generated-posts"
    assert settings.runtime.dry_run is True
    assert settings.runtime.visual_debug is True
    assert settings.runtime.log_level == "DEBUG"
    assert settings.vision.api_keys == ("key-a", "key-b")
    assert settings.vision.key_manager.peek() == "key-a"
    assert settings.vision.direct_fullscreen_attempts == 1
    assert settings.vision.grounding_capture_attempts == 1
    assert settings.vision.template_min_score == 0.46
    assert settings.automation.api_max_retries == 2
    assert settings.automation.api_backoff_base == 1.5
    assert settings.automation.grounding_mode == "first"
    assert settings.automation.launch_strategy == "cascade"
    assert settings.automation.watcher_enabled is True
    assert settings.automation.focus_debounce_seconds == 5.0
    assert settings.automation.focus_poll_interval_seconds == 0.2


def test_load_settings_supports_legacy_single_key(tmp_path):
    settings = load_settings(
        {"GOOGLE_API_KEY": "legacy-key"},
        project_root=tmp_path,
    )

    assert settings.vision.api_keys == ("legacy-key",)


def test_load_settings_keeps_project_root_as_path(tmp_path):
    settings = load_settings({}, project_root=tmp_path / "workspace")

    assert isinstance(settings.paths.project_root, Path)
    assert settings.paths.project_root == tmp_path / "workspace"


def test_load_settings_parses_split_retry_and_grounding_mode(tmp_path):
    settings = load_settings(
        {
            "AI__Gemini__ApiKeys__0": "key-a",
            "GROUNDING_MODE": "all",
            "API_MAX_RETRIES": "1",
            "API_BACKOFF_BASE": "1.1",
            "MLLM_MAX_RETRIES": "2",
            "MLLM_BACKOFF_BASE": "1.3",
            "DIRECT_FULLSCREEN_ATTEMPTS": "2",
            "GROUNDING_CAPTURE_ATTEMPTS": "2",
            "TEMPLATE_MIN_SCORE": "0.2",
            "LAUNCH_STRATEGY": "template_only",
        },
        project_root=tmp_path,
    )

    assert settings.automation.grounding_mode == "all"
    assert settings.automation.api_max_retries == 1
    assert settings.automation.api_backoff_base == 1.1
    assert settings.vision.max_retries == 2
    assert settings.vision.backoff_base == 1.3
    assert settings.vision.direct_fullscreen_attempts == 2
    assert settings.vision.grounding_capture_attempts == 2
    assert settings.vision.template_min_score == 0.2
    assert settings.automation.launch_strategy == "template_only"


def test_load_settings_invalid_grounding_mode_falls_back_to_first(tmp_path):
    settings = load_settings(
        {
            "AI__Gemini__ApiKeys__0": "key-a",
            "GROUNDING_MODE": "sometimes",
        },
        project_root=tmp_path,
    )

    assert settings.automation.grounding_mode == "first"


def test_load_settings_invalid_launch_strategy_falls_back_to_cascade(tmp_path):
    settings = load_settings(
        {
            "AI__Gemini__ApiKeys__0": "key-a",
            "LAUNCH_STRATEGY": "phase2-only",
        },
        project_root=tmp_path,
    )

    assert settings.automation.launch_strategy == "cascade"
