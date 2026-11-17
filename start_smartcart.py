"""Double-click launcher for the local SmartCart development app."""
from __future__ import annotations

import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
PYTHON = BACKEND / ".venv" / "Scripts" / "python.exe"
WINDOWS_NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)


def responds(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1.5) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def npm_command() -> str | None:
    local_npm = Path(os.environ.get("TEMP", "")) / "smartcart-node" / "node-v22.15.0-win-x64" / "npm.cmd"
    if local_npm.is_file():
        return str(local_npm)
    return shutil.which("npm")


def launch_backend() -> None:
    subprocess.Popen(
        [str(PYTHON), "-m", "uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0"],
        cwd=BACKEND,
        creationflags=WINDOWS_NEW_CONSOLE,
    )


def launch_frontend(npm: str) -> None:
    command = f'"{npm}" run dev -- --host 0.0.0.0'
    subprocess.Popen(command, cwd=FRONTEND, shell=True, creationflags=WINDOWS_NEW_CONSOLE)


def main() -> int:
    print("Starting SmartCart…")
    if not responds("http://127.0.0.1:8000/api/health"):
        if not PYTHON.is_file():
            print("SmartCart's Python environment is missing. Open BEGINNER_SETUP.md for help.")
            return 1
        launch_backend()
    else:
        print("API is already running.")

    if not responds("http://127.0.0.1:5173/"):
        npm = npm_command()
        if not npm:
            print("Node.js/npm was not found. Open BEGINNER_SETUP.md for help.")
            return 1
        launch_frontend(npm)
    else:
        print("Website is already running.")

    for _ in range(40):
        if responds("http://127.0.0.1:5173/") and responds("http://127.0.0.1:5173/api/health"):
            break
        time.sleep(0.75)
    else:
        print("SmartCart did not start in time. Check the two SmartCart console windows for errors.")
        return 1

    address = "http://localhost:5173/"
    print(f"SmartCart is ready: {address}")
    webbrowser.open(address)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
