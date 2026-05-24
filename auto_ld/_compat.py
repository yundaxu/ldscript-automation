"""Compatibility helpers for PyInstaller frozen mode."""
import os
import shutil
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
    bundled data (templates, images).  In script mode it is the same as
    get_project_root().
    """
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    else:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_models_dir() -> str:
    """Get easyocr models directory — writable, models copied from bundle on first use."""
    if getattr(sys, "frozen", False):
        return os.path.join(get_project_root(), "EasyOCR", "model")
    return os.path.join(os.path.expanduser("~"), ".EasyOCR", "model")


def ensure_models() -> None:
    """Copy bundled model files to writable models directory on first run (frozen only).

    Bundled models are at <MEIPASS>/EasyOCR/model/ (read-only).
    This copies them to <exe_dir>/EasyOCR/model/ (writable) so easyocr
    can verify/use them without re-downloading.
    """
    if not getattr(sys, "frozen", False):
        return

    writable_dir = get_models_dir()
    os.makedirs(writable_dir, exist_ok=True)

    bundled_dir = os.path.join(get_resource_dir(), "EasyOCR", "model")
    if not os.path.isdir(bundled_dir):
        return

    for fname in os.listdir(bundled_dir):
        bundled = os.path.join(bundled_dir, fname)
        target = os.path.join(writable_dir, fname)
        if not os.path.isfile(target):
            shutil.copy2(bundled, target)


def is_frozen() -> bool:
    """Check if running as PyInstaller bundled executable."""
    return bool(getattr(sys, "frozen", False))
