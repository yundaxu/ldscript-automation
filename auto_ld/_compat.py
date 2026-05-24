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
    bundled data (templates, images).  In script mode it is the same as
    get_project_root().
    """
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    else:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_models_dir() -> str:
    """Get easyocr models directory — writable path under exe dir in frozen mode."""
    if getattr(sys, "frozen", False):
        return os.path.join(get_project_root(), "EasyOCR", "model")
    return os.path.join(os.path.expanduser("~"), ".EasyOCR", "model")


def is_frozen() -> bool:
    """Check if running as PyInstaller bundled executable."""
    return bool(getattr(sys, "frozen", False))


def preload_models(logger=None) -> bool:
    """Pre-download easyocr models at startup (frozen mode only).

    Creates an easyocr Reader which auto-downloads missing model files
    from the official URLs.  Called once at program startup so the user
    sees download progress immediately rather than waiting on first OCR.

    Returns True if models are ready, False if download failed.
    """
    if not getattr(sys, "frozen", False):
        return True  # dev mode — models managed by pip/user

    models_dir = get_models_dir()
    os.makedirs(models_dir, exist_ok=True)

    try:
        import easyocr
    except ImportError:
        if logger:
            logger.error("easyocr 未安装，文字识别功能不可用")
        return False

    if logger:
        logger.info("正在检查/下载 OCR 模型到 %s ...", models_dir)

    try:
        easyocr.Reader(
            ["ch_sim", "en"], gpu=False,
            model_storage_directory=models_dir,
            download_enabled=True, verbose=True,
        )
        if logger:
            logger.info("OCR 模型就绪")
        return True
    except Exception as e:
        if logger:
            logger.error("OCR 模型下载失败: %s", e)
        return False
