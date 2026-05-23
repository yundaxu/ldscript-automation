"""包名数据管理 — 保存常用的应用包名。

存储位置: configs/packages.json
"""
import json
import os

PACKAGES_PATH = os.path.join("configs", "packages.json")


def _load() -> list[str]:
    if not os.path.exists(PACKAGES_PATH):
        return []
    try:
        with open(PACKAGES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save(data: list[str]) -> None:
    os.makedirs("configs", exist_ok=True)
    with open(PACKAGES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_packages() -> list[str]:
    return _load()


def add_package(name: str) -> bool:
    data = _load()
    if name not in data:
        data.append(name)
        _save(data)
    return True


def remove_package(name: str) -> bool:
    data = _load()
    if name in data:
        data.remove(name)
        _save(data)
        return True
    return False
