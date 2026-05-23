"""Compatibility helpers for PyInstaller frozen mode."""
import os
import sys


def get_project_root() -> str:
    """Get project root directory — works in both script and frozen mode."""
    if getattr(sys, "frozen", False):
        # PyInstaller: use exe directory (writable, persistent)
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        # Script mode: _compat.py is at <root>/auto_ld/_compat.py → go up 2 levels
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_models_dir() -> str:
    """Get easyocr models directory — bundled in frozen mode, ~/.EasyOCR otherwise."""
    if getattr(sys, "frozen", False):
        return os.path.join(get_project_root(), "EasyOCR", "model")
    return os.path.join(os.path.expanduser("~"), ".EasyOCR", "model")


def is_frozen() -> bool:
    """Check if running as PyInstaller bundled executable."""
    return bool(getattr(sys, "frozen", False))
