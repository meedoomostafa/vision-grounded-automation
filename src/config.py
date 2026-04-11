import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# MLLM
GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL: str = "gemini-2.5-flash"

# Runtime modes
DRY_RUN: bool = os.getenv("DRY_RUN", "false").lower() == "true"
VISUAL_DEBUG: bool = os.getenv("VISUAL_DEBUG", "false").lower() == "true"
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

MAX_RETRIES: int = 3
BACKOFF_BASE: float = 2.0
PRECISE_CROP_SIZE: int = 400

# Paths — all pathlib, all dynamic
OUTPUT_DIR: Path = Path.home() / "Desktop" / "tjm-project"
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
SCREENSHOTS_DIR: Path = PROJECT_ROOT / "screenshots"
DEBUG_SCREENSHOTS_DIR: Path = SCREENSHOTS_DIR / "debug"

# External API
API_BASE_URL: str = "https://jsonplaceholder.typicode.com"
API_POSTS_LIMIT: int = 10

# Automation timing (seconds)
TYPING_INTERVAL: float = 0.02
SETTLE_DELAY: float = 1.0
WINDOW_TIMEOUT: int = 10
SAVE_DIALOG_TIMEOUT: int = 5
