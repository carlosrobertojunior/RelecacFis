from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path


def asset_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "assets" / name


def set_window_icon(window: tk.Tk) -> None:
    try:
        window.iconbitmap(str(asset_path("favicon.ico")))
    except (OSError, tk.TclError):
        pass
