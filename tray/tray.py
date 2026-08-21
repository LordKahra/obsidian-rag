import ctypes
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from config import WSL_DISTRO, WSL_USER, REPO_PATH
except ImportError:
    # pythonw.exe has no console, so a print()/exception here would vanish silently.
    ctypes.windll.user32.MessageBoxW(
        0, "No config.py found in tray/. Copy config.example.py to config.py and set your WSL details.",
        "Obsidian RAG Tray", 0x10,
    )
    raise SystemExit(1)

# Matched on the full absolute command rather than just "indexer.py" — the bare filename is
# common enough as plain text in an unrelated concurrent shell command (e.g. someone discussing
# this very file) that pgrep -f can false-positive against it.
INDEXER_MATCH_PATTERN = f"{REPO_PATH}/venv/bin/python -u {REPO_PATH}/indexer.py"

INDEXER_CMD = ["wsl.exe", "-d", WSL_DISTRO, "-u", WSL_USER, "--"] + INDEXER_MATCH_PATTERN.split(" ")
PGREP_CMD = ["wsl.exe", "-d", WSL_DISTRO, "-u", WSL_USER, "--", "pgrep", "-f", INDEXER_MATCH_PATTERN]
PKILL_CMD = ["wsl.exe", "-d", WSL_DISTRO, "-u", WSL_USER, "--", "pkill", "-f", INDEXER_MATCH_PATTERN]

LOG_PATH = Path(__file__).resolve().parent / "indexer.log"

_lock = threading.Lock()


def is_running():
    result = subprocess.run(PGREP_CMD, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    return result.returncode == 0

def start_indexer():
    with _lock:
        if is_running():
            return
        log_file = open(LOG_PATH, "a", encoding="utf-8")
        subprocess.Popen(INDEXER_CMD, stdout=log_file, stderr=subprocess.STDOUT,
                          creationflags=subprocess.CREATE_NO_WINDOW)

def stop_indexer():
    with _lock:
        subprocess.run(PKILL_CMD, creationflags=subprocess.CREATE_NO_WINDOW)

def restart_indexer():
    stop_indexer()
    time.sleep(1)
    start_indexer()

def open_log():
    if not LOG_PATH.exists():
        LOG_PATH.touch()
    os.startfile(LOG_PATH)

def make_icon_image():
    """A simple crescent moon, drawn procedurally so no separate asset file is needed."""
    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((4, 4, size - 4, size - 4), fill=(235, 235, 245, 255))
    draw.ellipse((16, 0, size + 4, size - 8), fill=(0, 0, 0, 0))
    return image

def status_text(icon):
    return "Status: Running" if is_running() else "Status: Stopped"

def on_start(icon, item):
    start_indexer()

def on_stop(icon, item):
    stop_indexer()

def on_restart(icon, item):
    restart_indexer()

def on_open_log(icon, item):
    open_log()

def on_quit(icon, item):
    icon.stop()

def build_menu():
    return pystray.Menu(
        pystray.MenuItem(status_text, None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Start", on_start),
        pystray.MenuItem("Stop", on_stop),
        pystray.MenuItem("Restart", on_restart),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open Log", on_open_log),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", on_quit),
    )

def main():
    if not is_running():
        start_indexer()
    pystray.Icon("obsidian-rag-indexer", make_icon_image(), "Obsidian RAG Indexer", build_menu()).run()

if __name__ == "__main__":
    main()
