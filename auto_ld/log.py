"""模拟器脚本自助 统一日志模块。"""
import logging
import os
import sys
from datetime import datetime

_log_initialized = False


def get_logger(name: str) -> logging.Logger:
    """Get or create a logger for the given module name."""
    global _log_initialized
    if not _log_initialized:
        _init_logging()
        _log_initialized = True
    return logging.getLogger(name)


def _init_logging() -> None:
    log_dir = os.environ.get("AUTOLD_LOG_DIR", "logs")
    os.makedirs(log_dir, exist_ok=True)

    level_name = os.environ.get("AUTOLD_LOG_LEVEL", "INFO")
    level = getattr(logging, level_name.upper(), logging.INFO)

    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)-5s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    ch.setLevel(level)
    root.addHandler(ch)

    # File handler
    fh = logging.FileHandler(
        os.path.join(log_dir, f"autold_{datetime.now().strftime('%Y%m%d')}.log"),
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    fh.setLevel(level)
    root.addHandler(fh)
