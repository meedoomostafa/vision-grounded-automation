#!/bin/bash
set -e

echo "=========================================================="
echo "Building Windows Executable using Docker (tobix/pywine)..."
echo "=========================================================="

# Ensure output directory exists
mkdir -p dist

# Run PyInstaller inside a Windows/Wine container
# We map the current directory to /src
docker run --rm \
    -v "$(pwd):/src" \
    -w /src \
    tobix/pywine:3.12 \
    wine cmd /c "pip install uv && uv venv && uv pip install . pyinstaller && uv run pyinstaller --noconfirm --onefile --name DesktopAutomation --clean --hidden-import PIL._tkinter_finder --hidden-import pyautogui --hidden-import mss --hidden-import pywinctl src/main.py"

echo "=========================================================="
echo "Build complete! Check the 'dist/' folder for DesktopAutomation.exe"
echo "=========================================================="
