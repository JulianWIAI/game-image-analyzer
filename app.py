"""
app.py — GUI Entry Point
========================
Launch the Game Image Analyzer graphical interface.

Run this file directly to open the desktop application:

    python app.py

The GUI provides a full-featured interface to all pipeline steps
(scan, charts, overviews, PDF report, type analysis, full pipeline)
without needing to use the command line.

For CLI usage see main.py.
"""

import sys
import ctypes
from pathlib import Path


def _prepare_windows_taskbar_icon():
    """
    On Windows, set a unique AppUserModelID so the OS treats this process as
    a standalone application rather than grouping it under the Python interpreter.
    This is the prerequisite for Windows to use our custom icon in the taskbar.
    Must be called before the Tk window is created.
    """
    if sys.platform != "win32":
        return

    # Unique ID — Windows uses this to separate our app from other Python processes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
        "GameImageAnalyzer.App.1.0"
    )

    # Pre-convert PNG → ICO and store alongside the PNG so the path is stable.
    # iconbitmap() requires a real .ico file; a temp file can be cleaned up
    # before Windows finishes reading it.
    png_path = Path(__file__).parent / "assets" / "app_icon.png"
    ico_path = Path(__file__).parent / "assets" / "app_icon.ico"

    if png_path.exists() and not ico_path.exists():
        try:
            from PIL import Image
            Image.open(png_path).save(
                ico_path, format="ICO",
                sizes=[(256, 256), (48, 48), (32, 32), (16, 16)],
            )
        except Exception:
            pass  # non-fatal — window will still open without custom taskbar icon


_prepare_windows_taskbar_icon()

from SBS.GUI import GameImageAnalyzerGUI


if __name__ == "__main__":
    app = GameImageAnalyzerGUI()
    app.mainloop()
