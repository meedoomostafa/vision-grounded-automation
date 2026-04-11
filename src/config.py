import ctypes
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _enable_windows_dpi_awareness() -> None:
    """Enable DPI awareness so screenshots and mouse coordinates stay aligned."""
    if os.name != "nt":
        return

    try:
        # PROCESS_PER_MONITOR_DPI_AWARE
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass

    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _resolve_desktop_dir() -> Path:
    """Resolve the user's real Desktop directory, including redirected folders."""
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

        onedrive = os.environ.get("OneDrive")
        if onedrive:
            redirected = Path(onedrive) / "Desktop"
            if redirected.exists():
                return redirected

    return Path.home() / "Desktop"


_enable_windows_dpi_awareness()

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
MLLM_MIN_INTERVAL_SECONDS: float = float(os.getenv("MLLM_MIN_INTERVAL_SECONDS", "12.5"))

# Paths — all pathlib, all dynamic
DESKTOP_DIR: Path = _resolve_desktop_dir()
OUTPUT_DIR: Path = DESKTOP_DIR / "tjm-project"
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
