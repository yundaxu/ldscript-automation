"""模板注册表 — JSON 文件存储模板名到图片路径的映射。

存储位置: configs/templates.json
"""
import json
import os

from auto_ld.log import get_logger

REGISTRY_PATH = os.path.join("configs", "templates.json")


def _load_registry() -> dict:
    if not os.path.exists(REGISTRY_PATH):
        return {}
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_registry(data: dict) -> None:
    os.makedirs("configs", exist_ok=True)
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def register(name: str, image_path: str) -> None:
    data = _load_registry()
    data[name] = image_path
    _save_registry(data)


def unregister(name: str) -> None:
    data = _load_registry()
    data.pop(name, None)
    _save_registry(data)


def get_path(name: str) -> str | None:
    return _load_registry().get(name)


def list_all() -> dict:
    return _load_registry()
