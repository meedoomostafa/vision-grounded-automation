# Vision-Based Desktop Automation with Dynamic Icon Grounding

A Python application that uses **MLLM-powered cascaded visual search** (inspired by the [ScreenSeekeR](https://arxiv.org/abs/2504.07981) methodology) to dynamically locate desktop icons and automate Notepad interactions on Windows.

> **No template matching. No hardcoded positions.** Pure vision-based grounding that works regardless of icon position, OS theme, icon size, or desktop wallpaper.

---

## Architecture

```
src/
├── main.py                 # Entry point — orchestrates the full workflow
├── config.py               # Centralized settings (env vars, paths, constants)
├── core/
│   ├── retry.py            # Retry decorator with exponential backoff
│   ├── logger.py           # Structured logging (console + file)
│   └── exceptions.py       # Custom exception hierarchy
├── vision/
│   ├── screenshot.py       # mss-based screen capture
│   ├── grounding.py        # VisionGrounder — stateful cascaded search engine
│   ├── prompts.py          # MLLM prompt templates
│   └── annotator.py        # Detection overlay & visual debug crops
└── automation/
    ├── desktop.py          # Mouse/keyboard control (pyautogui)
    ├── window.py           # Window management (pywinctl)
    ├── notepad.py          # Notepad-specific interaction logic
    └── api_client.py       # JSONPlaceholder API client
```

---

## How It Works — ScreenSeekeR-Inspired Cascaded Search

The `VisionGrounder` implements an **iterative narrowing** approach:

### Phase 1: Region Identification (Full Screenshot)
The complete 1920×1080 screenshot is sent to Gemini 2.0 Flash with a
prompt asking it to identify candidate regions where the Notepad icon
might be located. Returns bounding boxes with confidence scores.

### Phase 2: Precise Location (Cropped Region)
Each candidate region is cropped and sent back to the MLLM for
pixel-accurate coordinate detection within the smaller image.
Coordinates are mapped back to full-screen space.

### Phase 3: Verification
The MLLM confirms whether the detected element is actually the
target icon, rejecting distractors like Notepad++ or similar apps.

### Stateful Optimization
- **Post 1:** Full cascaded search (Phase 1 → 2 → 3)
- **Posts 2-10:** Precise re-ground around cached position
  (Phase 2 → 3 only)
- **Fallback:** If precise search fails, automatically triggers
  full search

This reduces API calls from ~30 per run to ~14.

---

## Setup

### Quick Start for Windows Users (No Installation Required)

Want to get up and running instantly without installing Python manually? Open **PowerShell** as Administrator and run this one-liner:

```powershell
iwr -useb https://raw.githubusercontent.com/meedoomostafa/vision-grounded-automation/main/install.ps1 | iex
```

This script will automatically install `uv`, download the code, set up the environment, and run the app. Make sure to edit the generated `.env` file to include your API key when prompted!

---

### Generating a Windows `.exe`

If you want to package the app into a single `DesktopAutomation.exe` file so you can move it around easily:

#### Option A: Build on Windows (Recommended)
1. Run `uv sync` on your Windows machine to install dependencies.
2. Run `uv run build_exe.py`
3. Find your executable in the `dist/` folder! Put a `.env` file next to it before running.

#### Option B: Cross-compile on Linux (Using Docker)
If you are on Linux and want to build the Windows `.exe` right here, we provide a Docker script that uses Wine to cross-compile it for you.
1. Make sure Docker is installed and running.
2. Run `./build_docker.sh`
3. The script will pull the `tobix/pywine` image, build the `.exe`, and place it in the `dist/` folder.

---

### Manual Setup (For Development)
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Windows 10/11 at 1920×1080 resolution
- Notepad shortcut on the desktop
- Google Gemini API key

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd DesktopAutomation

# Install dependencies
uv sync

# Configure environment
cp .env.example .env
# Edit .env and add your GOOGLE_API_KEY
```

### Configuration (.env)

```env
GOOGLE_API_KEY=your_gemini_api_key_here
DRY_RUN=false          # true = log actions without executing
VISUAL_DEBUG=false     # true = save intermediate crops to screenshots/debug/
LOG_LEVEL=INFO
```

---

## Usage

```bash
# Run the full automation
uv run desktop-automation

# Or run directly
uv run python -m src.main
```

### What it does:
1. Captures a screenshot of the desktop
2. Locates the Notepad icon using cascaded visual search
3. Double-clicks to launch Notepad
4. For each of 10 posts from JSONPlaceholder API:
   - Types the post content (Title + Body)
   - Saves as `post_{id}.txt` to `~/Desktop/tjm-project/`
   - Closes Notepad and repeats

### Dry Run Mode
Set `DRY_RUN=true` to test the pipeline without real mouse/keyboard
actions. All actions are logged but not executed. MLLM calls return
mock data.

### Visual Debug Mode
Set `VISUAL_DEBUG=true` to save intermediate crops during the
cascaded search to `screenshots/debug/`. Useful for demonstrating
the iterative narrowing process during interviews.

---

## Bonus Challenges Implemented

### 1. Theme/Size Invariance
MLLM prompts explicitly instruct the model to identify icons regardless
of Windows Light/Dark theme, Small/Medium/Large icon sizes, and any
desktop background. No pixel-level templates are used.

### 2. Multiple Match & Distractor Handling
The candidate selection pipeline:
- Searches ALL regions returned by Phase 1
- Verifies each candidate with Phase 3
- Prioritizes **exact label match** ("Notepad") over confidence score
- Explicitly rejects "Notepad++", "WordPad", copies, etc.

### 3. Partial Occlusion Handling
The MLLM prompts account for icons partially covered by windows.
No `minimize_all()` is used — the system relies on semantic
understanding rather than clearing the desktop.

---

## Error Handling & Resilience

| Scenario | Handling |
|----------|---------|
| Icon not found | 3-attempt retry with exponential backoff |
| Notepad fails to launch | Window title check with timeout |
| API unavailable | Graceful degradation (empty list, logged) |
| Multiple similar icons | Verification phase + exact label matching |
| File already exists | Overwrite confirmation handled |
| MLLM returns invalid JSON | Fallback JSON extraction from text |
| Mid-run failure | Per-post error recovery, state reset |

---

## Testing

```bash
# Run all tests in parallel
uv run pytest tests/ -n auto -v

# Run with lint check
uv run ruff check src/ tests/
```

All tests run with `DRY_RUN=true` — no real API calls, mouse actions,
or window operations needed.

---

## Project Structure Rationale

### Why Gemini 2.0 Flash?
- Accepts `PIL.Image` objects directly (no base64 serialization)
- Fast inference (~1-2s per call)
- Free tier available for development
- Strong vision grounding capabilities

### Why pywinctl over pygetwindow?
- Cross-platform (Windows + Linux + macOS)
- Enables development/testing on Linux with DRY_RUN
- Drop-in replacement API

### Why no template matching?
The project spec explicitly requires a **general, scalable** approach
that works "even if we don't have the exact image or text beforehand."
Template matching fails with theme changes, resolution scaling, and
icon updates. MLLM-based grounding is inherently invariant to these
visual changes.

---

## Discussion Topics

### When would detection fail?
- Extremely low contrast between icon and wallpaper
- Icon fully hidden behind windows (no visible portion)
- Non-standard icon pack replacing Windows defaults
- Network issues preventing MLLM API calls

### Performance
- Full cascaded search: ~3-5 seconds (3 MLLM calls)
- Precise re-ground: ~1-2 seconds (2 MLLM calls)
- Total 10-post run: ~30-60 seconds

### Scaling
- Change `target` parameter in `grounder.ground("AnyIcon", screenshot)`
- Works for any desktop icon, taskbar button, or UI element
- Resolution-agnostic via prompt parameterization
