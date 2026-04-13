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
