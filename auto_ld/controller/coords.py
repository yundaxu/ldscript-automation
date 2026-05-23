"""坐标数据管理 — 保存命名的坐标点和区域。

存储位置: configs/coordinates.json
"""
import json
import os

from auto_ld.log import get_logger

COORDS_PATH = os.path.join("configs", "coordinates.json")


def _load() -> dict:
    if not os.path.exists(COORDS_PATH):
        return {"points": {}, "regions": {}}
    try:
        with open(COORDS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"points": {}, "regions": {}}


def _save(data: dict) -> None:
    os.makedirs("configs", exist_ok=True)
    with open(COORDS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_coords() -> dict:
    """返回所有坐标: {points: {name: {x,y}}, regions: {name: {x1,y1,x2,y2}}}"""
    return _load()


def save_point(name: str, x: int, y: int) -> bool:
    data = _load()
    data["points"][name] = {"x": x, "y": y}
    _save(data)
    get_logger("Coords").info("Saved point '%s': (%d,%d)", name, x, y)
    return True


def save_region(name: str, x1: int, y1: int, x2: int, y2: int) -> bool:
    data = _load()
    data["regions"][name] = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
    _save(data)
    get_logger("Coords").info("Saved region '%s': (%d,%d)-(%d,%d)", name, x1, y1, x2, y2)
    return True


def delete_coord(name: str) -> bool:
    data = _load()
    found = False
    if name in data["points"]:
        del data["points"][name]
        found = True
    if name in data["regions"]:
        del data["regions"][name]
        found = True
    if found:
        _save(data)
    return found


def get_point(name: str) -> dict | None:
    return _load()["points"].get(name)


def get_region(name: str) -> dict | None:
    return _load()["regions"].get(name)
