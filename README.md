# Vision-Grounded Desktop Automation

A Python application that combines MLLM-based icon grounding with deterministic UI fallbacks to automate Notepad writing/saving on Windows.

The project uses ScreenSeekeR-style phased grounding (region -> precise -> verify), but the live orchestration is intentionally hybrid for reliability.

## Current Behavior Snapshot (April 2026)

- Single-instance runtime lock is enforced through a lock file and PID metadata.
- Posts are fetched from JSONPlaceholder with retry and an offline fallback list.
- First post launch uses visual grounding of the Notepad desktop shortcut.
- Remaining posts launch Notepad deterministically via notepad.exe.
- Optional background FocusWatcher pauses automation when unexpected popup-like windows steal focus.

## Architecture

```
src/
|- main.py                 # Orchestration entry point and recovery loop
|- config.py               # Global config module (loads from core.settings)
|- automation/
|  |- api_client.py        # JSONPlaceholder fetch + validation + fallback posts
|  |- control.py           # ExecutionGate (pause/resume coordination)
|  |- desktop.py           # BotCity DesktopBot input primitives
|  |- notepad.py           # Launch, write, save, close Notepad workflows
|  \- window.py            # Window detection/activation via BotCity -> pywinauto
|- vision/
|  |- screenshot.py        # mss capture + bounded cropping
|  |- prompts.py           # Prompt templates (region/precise/verify/popup)
|  |- grounding.py         # VisionGrounder + call budget + key rotation
|  \- annotator.py         # Screenshot overlays and debug image output
|- watcher/
|  \- focus.py             # Foreground-window watcher for popup anomalies
\- core/
  |- exceptions.py        # Domain-specific exceptions
  |- key_manager.py       # Round-robin API key manager
  |- logger.py            # Console + rotating file logging
  |- retry.py             # Exponential backoff decorator
  |- settings.py          # Typed settings and defaults
  \- singleton.py         # PID-backed lock with stale lock recovery
```

## End-to-End Runtime Flow

1. `src.main:main` acquires `SingletonLock` on `.automation.lock`.
2. Logging is initialized and output folders are ensured.
3. Posts are fetched using `fetch_posts(limit=API_POSTS_LIMIT)`.
4. If `DRY_RUN=true`, placeholder files are written and the run exits.
5. In live mode:
  - `VisionGrounder` is created.
  - `FocusWatcher` starts if `WATCHER_ENABLED=true`.
  - Automation gate is armed with expected titles: `Notepad`, `Save`, `Confirm`.
6. Per post:
  - Post index 0: desktop grounding path (`show_desktop` -> ground icon -> click/enter -> fallback double-click -> fallback notepad.exe).
  - Post index 1..N: deterministic launch path (`launch_notepad_process()` only).
  - Write content, save `post_{id}.txt`, handle overwrite prompts, verify file write, then close Notepad.
7. On failure: recover by attempting close + state reset, then continue to next post.
8. On shutdown: disarm gate, stop watcher, print success/failure summary.

## Grounding Strategy (VisionGrounder)

`VisionGrounder.ground()` currently follows this order:

1. Precise re-ground around cached coordinates (if state exists).
2. Direct full-screen locate + verification.
3. Full cascaded search:
  - Phase 1: identify candidate regions.
  - Phase 2: locate coordinates inside each region.
  - Phase 3: verify candidate identity.

Additional safeguards:

- Rate pacing between MLLM calls via `MLLM_MIN_INTERVAL_SECONDS` (scaled by number of configured keys).
- Hard per-run call budget via `MAX_MLLM_CALLS_PER_RUN`.
- Round-robin Gemini key rotation through `RoundRobinKeyManager`.
- JSON fallback extraction when model output is mixed/non-strict.

Important runtime note:

- Main orchestration currently grounds only the first post (`use_grounding=index == 0`) and resets grounding state after each post. The precise re-ground path exists in `VisionGrounder` but is not currently exercised by posts 2..N in `src.main`.

## Focus Anomaly Watcher

`FocusWatcher` (background daemon thread) monitors the foreground window and can pause automation when suspicious popup-like windows appear.

Detection signals include:

- Window class `#32770`.
- Popup keywords in title (for example: alert, confirm, warning, save).
- Unexpected process focus (with blacklist exclusions).

When triggered:

1. Gate pauses the main flow.
2. A screenshot is analyzed via Gemini popup prompt.
3. A safe action is executed (`esc`, `enter`, `alt+F4`, `alt+n`, or ignore).
4. Gate resumes execution.

## Setup

### Windows One-Liner

```powershell
iwr -useb https://raw.githubusercontent.com/meedoomostafa/vision-grounded-automation/main/install.ps1 | iex
```

### Manual Setup

```bash
uv sync
copy .env.example .env
```

Then edit `.env`.

## Configuration (.env)

```env
# Gemini keys (preferred: indexed multi-key)
AI__Gemini__ApiKeys__0=your_first_gemini_api_key_here
AI__Gemini__ApiKeys__1=your_second_gemini_api_key_here

# Legacy fallback key names are still supported:
# GOOGLE_API_KEY=your_key
# GEMINI_API_KEY=your_key

GEMINI_MODEL=gemini-2.5-flash

DRY_RUN=false
VISUAL_DEBUG=false
LOG_LEVEL=INFO

OUTPUT_FOLDER=tjm-project

API_BASE_URL=https://jsonplaceholder.typicode.com
API_POSTS_LIMIT=10

MAX_RETRIES=3
BACKOFF_BASE=2.0

MLLM_MIN_INTERVAL_SECONDS=12.5
MAX_MLLM_CALLS_PER_RUN=80
PRECISE_CROP_SIZE=400
PRECISE_MIN_CONFIDENCE=0.55
PRECISE_VERIFY_EVERY_N=1
ALLOW_HEURISTIC_REGION_FALLBACK=false

TYPING_INTERVAL=0.02
SETTLE_DELAY=1.0
WINDOW_TIMEOUT=10
SAVE_DIALOG_TIMEOUT=5

WATCHER_ENABLED=true
FOCUS_DEBOUNCE_SECONDS=5.0
FOCUS_POLL_INTERVAL_SECONDS=0.2
```

## Usage

```bash
uv run desktop-automation
# or
uv run python -m src.main
```

Outputs are written to:

- `%USERPROFILE%/Desktop/<OUTPUT_FOLDER>/post_{id}.txt` on Windows desktop path resolution.

## Build

### Build Windows EXE on Windows

```bash
uv run build_exe.py
```

### Build Windows EXE from Linux (Docker + Wine)

```bash
./build_docker.sh
```

## Error Handling and Recovery

| Scenario | Current handling |
|----------|------------------|
| API fetch failure | Retry with exponential backoff, then offline fallback posts |
| Grounding failure | Retry capture/ground attempts, then post-level recovery |
| Notepad launch failure | Escalate click/enter -> double-click -> notepad.exe fallback |
| Save dialog missing | Retry with Ctrl+Shift+S and explicit window focus |
| File not written | Poll mtime/size and fail with WindowNotFoundError if unchanged |
| Unexpected popup focus | Pause, analyze, act, resume through execution gate |
| Mid-run exception | Recover, reset state, continue to next post |

## Testing

```bash
uv run pytest tests/ -n auto -v
uv run ruff check src/ tests/
```

The suite is primarily DRY_RUN/mocked and validates:

- Settings loading and key rotation.
- Retry and logging behavior.
- Grounding helper logic and budget guards.
- Notepad save flow and window helpers.
- Focus watcher blacklist/debounce/popup heuristics.
- End-to-end dry-run orchestration.

## Known Gaps / Notes

- Live integration tests (real Gemini + real desktop interactions) are not part of CI tests.
- Some build scripts still reference `pyautogui` hidden imports even though runtime input control uses BotCity DesktopBot.
- `_snap_to_visual_cluster` uses fixed local heuristics tuned to desktop icon geometry.
