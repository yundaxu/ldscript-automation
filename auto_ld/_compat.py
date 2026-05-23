"""Compatibility helpers for PyInstaller frozen mode."""
import os
import sys


def get_project_root() -> str:
    """Get writable data directory — exe dir in frozen, project root in script mode.

    Use this for files the user/application writes to: configs, pipelines, logs.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_resource_dir() -> str:
    """Get read-only bundled resource directory.

    In frozen mode this returns sys._MEIPASS where PyInstaller extracts
    bundled data (templates, images, models).  In script mode it is the
    same as get_project_root().
    """
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    else:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_models_dir() -> str:
    """Get easyocr models directory — bundled in frozen mode, ~/.EasyOCR otherwise."""
    if getattr(sys, "frozen", False):
        return os.path.join(get_resource_dir(), "EasyOCR", "model")
    return os.path.join(os.path.expanduser("~"), ".EasyOCR", "model")


def is_frozen() -> bool:
    """Check if running as PyInstaller bundled executable."""
    return bool(getattr(sys, "frozen", False))
