from __future__ import annotations

import ctypes
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from src.core.key_manager import RoundRobinKeyManager


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    return int(value.strip())


def _parse_float(value: str | None, default: float) -> float:
    if value is None:
        return default
    return float(value.strip())


def _parse_choice(value: str | None, allowed: set[str], default: str) -> str:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in allowed:
        return normalized
    return default


def enable_windows_dpi_awareness() -> None:
    """Enable DPI awareness so screen capture and cursor coordinates stay aligned."""
    if os.name != "nt":
        return

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass

    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def resolve_desktop_dir(env: Mapping[str, str] | None = None) -> Path:
    """Resolve the user's Desktop path, including redirected Windows folders."""
    env_map = os.environ if env is None else env

    if os.name == "nt":
        try:
            csidl_desktopdirectory = 0x0010
            buffer = ctypes.create_unicode_buffer(260)
            result = ctypes.windll.shell32.SHGetFolderPathW(
                None,
                csidl_desktopdirectory,
                None,
                0,
                buffer,
            )
            if result == 0 and buffer.value:
                return Path(buffer.value)
        except Exception:
            pass

        onedrive = env_map.get("OneDrive")
        if onedrive:
            redirected = Path(onedrive) / "Desktop"
            if redirected.exists():
                return redirected

    return Path.home() / "Desktop"


@dataclass(frozen=True)
class PathSettings:
    project_root: Path
    desktop_dir: Path
    output_dir: Path
    logs_dir: Path
    screenshots_dir: Path
    debug_screenshots_dir: Path
    lock_file: Path


@dataclass(frozen=True)
class RuntimeSettings:
    dry_run: bool
    visual_debug: bool
    log_level: str


@dataclass(frozen=True)
class VisionSettings:
    model: str
    api_keys: tuple[str, ...]
    key_manager: RoundRobinKeyManager
    max_retries: int
    backoff_base: float
    direct_fullscreen_attempts: int
    precise_crop_size: int
    grounding_capture_attempts: int
    mllm_min_interval_seconds: float
    max_mllm_calls_per_run: int
    precise_min_confidence: float
    precise_verify_every_n: int
    allow_heuristic_region_fallback: bool
    template_min_score: float


@dataclass(frozen=True)
class AutomationSettings:
    api_base_url: str
    api_posts_limit: int
    api_max_retries: int
    api_backoff_base: float
    grounding_mode: str
    launch_strategy: str
    launch_cursor_restore_mode: str
    launch_trace_screenshots: bool
    typing_interval: float
    settle_delay: float
    window_timeout: int
    save_dialog_timeout: int
    watcher_enabled: bool
    focus_debounce_seconds: float
    focus_poll_interval_seconds: float


@dataclass(frozen=True)
class Settings:
    paths: PathSettings
    runtime: RuntimeSettings
    vision: VisionSettings
    automation: AutomationSettings


def load_settings(
    env: Mapping[str, str] | None = None,
    *,
    project_root: Path | None = None,
) -> Settings:
    env_map = os.environ if env is None else env
    root = project_root or Path(__file__).resolve().parents[2]
    desktop_dir = resolve_desktop_dir(env_map)
    output_folder = env_map.get("OUTPUT_FOLDER", "tjm-project").strip() or "tjm-project"

    key_manager = RoundRobinKeyManager.from_env(env_map)
    api_keys = key_manager.keys

    paths = PathSettings(
        project_root=root,
        desktop_dir=desktop_dir,
        output_dir=desktop_dir / output_folder,
        logs_dir=root / "logs",
        screenshots_dir=root / "screenshots",
        debug_screenshots_dir=root / "screenshots" / "debug",
        lock_file=root / ".automation.lock",
    )
    runtime = RuntimeSettings(
        dry_run=_parse_bool(env_map.get("DRY_RUN"), default=False),
        visual_debug=_parse_bool(env_map.get("VISUAL_DEBUG"), default=False),
        log_level=(env_map.get("LOG_LEVEL", "INFO").strip() or "INFO").upper(),
    )
    legacy_max_retries = _parse_int(env_map.get("MAX_RETRIES"), default=3)
    legacy_backoff_base = _parse_float(env_map.get("BACKOFF_BASE"), default=2.0)

    vision = VisionSettings(
        model=env_map.get("GEMINI_MODEL", "gemini-1.5-flash").strip() or "gemini-1.5-flash",
        api_keys=api_keys,
        key_manager=key_manager,
        max_retries=_parse_int(env_map.get("MLLM_MAX_RETRIES"), default=legacy_max_retries),
        backoff_base=_parse_float(env_map.get("MLLM_BACKOFF_BASE"), default=legacy_backoff_base),
        direct_fullscreen_attempts=_parse_int(
            env_map.get("DIRECT_FULLSCREEN_ATTEMPTS"),
            default=1,
        ),
        precise_crop_size=_parse_int(env_map.get("PRECISE_CROP_SIZE"), default=400),
        grounding_capture_attempts=_parse_int(
            env_map.get("GROUNDING_CAPTURE_ATTEMPTS"),
            default=1,
        ),
        mllm_min_interval_seconds=_parse_float(
            env_map.get("MLLM_MIN_INTERVAL_SECONDS"),
            default=12.5,
        ),
        max_mllm_calls_per_run=_parse_int(env_map.get("MAX_MLLM_CALLS_PER_RUN"), default=80),
        precise_min_confidence=_parse_float(
            env_map.get("PRECISE_MIN_CONFIDENCE"),
            default=0.55,
        ),
        precise_verify_every_n=_parse_int(
            env_map.get("PRECISE_VERIFY_EVERY_N"),
            default=1,
        ),
        allow_heuristic_region_fallback=_parse_bool(
            env_map.get("ALLOW_HEURISTIC_REGION_FALLBACK"),
            default=False,
        ),
        template_min_score=_parse_float(
            env_map.get("TEMPLATE_MIN_SCORE"),
            default=0.46,
        ),
    )
    automation = AutomationSettings(
        api_base_url=env_map.get("API_BASE_URL", "https://jsonplaceholder.typicode.com").strip()
        or "https://jsonplaceholder.typicode.com",
        api_posts_limit=_parse_int(env_map.get("API_POSTS_LIMIT"), default=3),
        api_max_retries=_parse_int(env_map.get("API_MAX_RETRIES"), default=2),
        api_backoff_base=_parse_float(env_map.get("API_BACKOFF_BASE"), default=1.5),
        grounding_mode=_parse_choice(
            env_map.get("GROUNDING_MODE"),
            {"first", "all", "none"},
            default="first",
        ),
        launch_strategy=_parse_choice(
            env_map.get("LAUNCH_STRATEGY"),
            {"cascade", "template_only"},
            default="cascade",
        ),
        launch_cursor_restore_mode=_parse_choice(
            env_map.get("LAUNCH_CURSOR_RESTORE_MODE"),
            {"off", "end"},
            default="off",
        ),
        launch_trace_screenshots=_parse_bool(
            env_map.get("LAUNCH_TRACE_SCREENSHOTS"),
            default=False,
        ),
        typing_interval=_parse_float(env_map.get("TYPING_INTERVAL"), default=0.02),
        settle_delay=_parse_float(env_map.get("SETTLE_DELAY"), default=1.0),
        window_timeout=_parse_int(env_map.get("WINDOW_TIMEOUT"), default=10),
        save_dialog_timeout=_parse_int(env_map.get("SAVE_DIALOG_TIMEOUT"), default=5),
        watcher_enabled=_parse_bool(env_map.get("WATCHER_ENABLED"), default=True),
        focus_debounce_seconds=_parse_float(
            env_map.get("FOCUS_DEBOUNCE_SECONDS"),
            default=5.0,
        ),
        focus_poll_interval_seconds=_parse_float(
            env_map.get("FOCUS_POLL_INTERVAL_SECONDS"),
            default=0.2,
        ),
    )
    return Settings(paths=paths, runtime=runtime, vision=vision, automation=automation)
