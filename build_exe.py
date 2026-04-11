import os
import subprocess
import sys
from pathlib import Path

def main():
    print("="*50)
    print("Building Windows Executable for Desktop Automation")
    print("="*50)

    # Ensure we're in the right directory
    project_root = Path(__file__).resolve().parent
    os.chdir(project_root)

    if sys.platform != "win32":
        print("WARNING: You are running this on a non-Windows OS.")
        print("PyInstaller compiles native executables. To get a Windows .exe,")
        print("you must run this script ON a Windows machine.")
        print("-" * 50)

    # PyInstaller command arguments
    args = [
        "pyinstaller",
        "--noconfirm",
        "--onefile",
        "--name", "DesktopAutomation",
        "--clean",
        "--hidden-import", "PIL._tkinter_finder", # Often needed for Pillow
        "--hidden-import", "pyautogui",
        "--hidden-import", "mss",
        "--hidden-import", "pywinctl",
        "src/main.py"
    ]

    print(f"Running: {' '.join(args)}\n")
    
    try:
        subprocess.run(args, check=True)
        print("\n" + "="*50)
        print("Build Successful!")
        print(f"Executable is located in: {project_root / 'dist'}")
        print("Note: Make sure to place your .env file in the same directory as the .exe when running.")
        print("="*50)
    except subprocess.CalledProcessError as e:
        print(f"\nBuild failed with exit code {e.returncode}")
        sys.exit(e.returncode)
    except FileNotFoundError:
        print("\nERROR: 'pyinstaller' not found. Make sure it is installed in your environment.")
        print("Run: uv sync")
        sys.exit(1)

if __name__ == "__main__":
    main()
