from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from src.core.key_manager import RoundRobinKeyManager
from src.core.settings import Settings, enable_windows_dpi_awareness, load_settings

load_dotenv()
enable_windows_dpi_awareness()

settings: Settings

GOOGLE_API_KEY: str
GEMINI_API_KEYS: tuple[str, ...]
GEMINI_KEY_MANAGER: RoundRobinKeyManager
GEMINI_MODEL: str

DRY_RUN: bool
VISUAL_DEBUG: bool
LOG_LEVEL: str

MAX_RETRIES: int
BACKOFF_BASE: float
DIRECT_FULLSCREEN_ATTEMPTS: int
PRECISE_CROP_SIZE: int
GROUNDING_CAPTURE_ATTEMPTS: int
MLLM_MIN_INTERVAL_SECONDS: float
MAX_MLLM_CALLS_PER_RUN: int
PRECISE_MIN_CONFIDENCE: float
PRECISE_VERIFY_EVERY_N: int
ALLOW_HEURISTIC_REGION_FALLBACK: bool
TEMPLATE_MIN_SCORE: float

DESKTOP_DIR: Path
OUTPUT_DIR: Path
PROJECT_ROOT: Path
LOGS_DIR: Path
SCREENSHOTS_DIR: Path
DEBUG_SCREENSHOTS_DIR: Path
LOCK_FILE: Path

API_BASE_URL: str
API_POSTS_LIMIT: int
API_MAX_RETRIES: int
API_BACKOFF_BASE: float
GROUNDING_MODE: str
LAUNCH_STRATEGY: str
LAUNCH_CURSOR_RESTORE_MODE: str
LAUNCH_TRACE_SCREENSHOTS: bool

TYPING_INTERVAL: float
SETTLE_DELAY: float
WINDOW_TIMEOUT: int
SAVE_DIALOG_TIMEOUT: int
WATCHER_ENABLED: bool
FOCUS_DEBOUNCE_SECONDS: float
FOCUS_POLL_INTERVAL_SECONDS: float


def reload_settings() -> Settings:
    global settings
    global GOOGLE_API_KEY, GEMINI_API_KEYS, GEMINI_KEY_MANAGER, GEMINI_MODEL
    global DRY_RUN, VISUAL_DEBUG, LOG_LEVEL
    global MAX_RETRIES, BACKOFF_BASE, DIRECT_FULLSCREEN_ATTEMPTS
    global PRECISE_CROP_SIZE, GROUNDING_CAPTURE_ATTEMPTS
    global MLLM_MIN_INTERVAL_SECONDS, MAX_MLLM_CALLS_PER_RUN
    global PRECISE_MIN_CONFIDENCE, PRECISE_VERIFY_EVERY_N
    global ALLOW_HEURISTIC_REGION_FALLBACK, TEMPLATE_MIN_SCORE
    global DESKTOP_DIR, OUTPUT_DIR, PROJECT_ROOT, LOGS_DIR
    global SCREENSHOTS_DIR, DEBUG_SCREENSHOTS_DIR
    global LOCK_FILE
    global API_BASE_URL, API_POSTS_LIMIT, API_MAX_RETRIES, API_BACKOFF_BASE, GROUNDING_MODE
    global LAUNCH_STRATEGY, LAUNCH_CURSOR_RESTORE_MODE, LAUNCH_TRACE_SCREENSHOTS
    global TYPING_INTERVAL, SETTLE_DELAY, WINDOW_TIMEOUT, SAVE_DIALOG_TIMEOUT
    global WATCHER_ENABLED, FOCUS_DEBOUNCE_SECONDS, FOCUS_POLL_INTERVAL_SECONDS

    settings = load_settings()

    GEMINI_API_KEYS = settings.vision.api_keys
    GEMINI_KEY_MANAGER = settings.vision.key_manager
    GOOGLE_API_KEY = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else ""
    GEMINI_MODEL = settings.vision.model

    DRY_RUN = settings.runtime.dry_run
    VISUAL_DEBUG = settings.runtime.visual_debug
    LOG_LEVEL = settings.runtime.log_level

    MAX_RETRIES = settings.vision.max_retries
    BACKOFF_BASE = settings.vision.backoff_base
    DIRECT_FULLSCREEN_ATTEMPTS = settings.vision.direct_fullscreen_attempts
    PRECISE_CROP_SIZE = settings.vision.precise_crop_size
    GROUNDING_CAPTURE_ATTEMPTS = settings.vision.grounding_capture_attempts
    MLLM_MIN_INTERVAL_SECONDS = settings.vision.mllm_min_interval_seconds
    MAX_MLLM_CALLS_PER_RUN = settings.vision.max_mllm_calls_per_run
    PRECISE_MIN_CONFIDENCE = settings.vision.precise_min_confidence
    PRECISE_VERIFY_EVERY_N = settings.vision.precise_verify_every_n
    ALLOW_HEURISTIC_REGION_FALLBACK = settings.vision.allow_heuristic_region_fallback
    TEMPLATE_MIN_SCORE = settings.vision.template_min_score

    PROJECT_ROOT = settings.paths.project_root
    DESKTOP_DIR = settings.paths.desktop_dir
    OUTPUT_DIR = settings.paths.output_dir
    LOGS_DIR = settings.paths.logs_dir
    SCREENSHOTS_DIR = settings.paths.screenshots_dir
    DEBUG_SCREENSHOTS_DIR = settings.paths.debug_screenshots_dir
    LOCK_FILE = settings.paths.lock_file

    API_BASE_URL = settings.automation.api_base_url
    API_POSTS_LIMIT = settings.automation.api_posts_limit
    API_MAX_RETRIES = settings.automation.api_max_retries
    API_BACKOFF_BASE = settings.automation.api_backoff_base
    GROUNDING_MODE = settings.automation.grounding_mode
    LAUNCH_STRATEGY = settings.automation.launch_strategy
    LAUNCH_CURSOR_RESTORE_MODE = settings.automation.launch_cursor_restore_mode
    LAUNCH_TRACE_SCREENSHOTS = settings.automation.launch_trace_screenshots
    TYPING_INTERVAL = settings.automation.typing_interval
    SETTLE_DELAY = settings.automation.settle_delay
    WINDOW_TIMEOUT = settings.automation.window_timeout
    SAVE_DIALOG_TIMEOUT = settings.automation.save_dialog_timeout
    WATCHER_ENABLED = settings.automation.watcher_enabled
    FOCUS_DEBOUNCE_SECONDS = settings.automation.focus_debounce_seconds
    FOCUS_POLL_INTERVAL_SECONDS = settings.automation.focus_poll_interval_seconds

    return settings


reload_settings()
