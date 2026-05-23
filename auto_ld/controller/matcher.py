"""图像模板匹配模块 — 在屏幕截图中查找目标图像的位置。

MAA 框架模式参考:
  - OpenCV 模板匹配 (TM_CCOEFF_NORMED)
  - 支持 ROI 区域限制搜索
  - 返回最佳匹配坐标和置信度
"""
import os

import numpy as np

from auto_ld.log import get_logger

_cv2 = None


def _get_cv2():
    global _cv2
    if _cv2 is None:
        try:
            import cv2 as cv
            _cv2 = cv
        except ImportError:
            raise ImportError(
                "opencv-python is required. Install: pip install opencv-python numpy"
            )
    return _cv2


class TemplateMatcher:
    """图像模板匹配器。Lazy init，首次使用时才加载 OpenCV 和模板。"""

    def __init__(self, templates_dir: str = "images", threshold: float = 0.8) -> None:
        self._dir = templates_dir
        self._threshold = threshold
        self._templates: dict = {}
        self._loaded = False
        self._log = get_logger("Matcher")

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        os.makedirs(self._dir, exist_ok=True)
        self._loaded = True
        self._load_existing()

    def _load_existing(self) -> None:
        cv = _get_cv2()
        if not os.path.exists(self._dir):
            return
        for fname in os.listdir(self._dir):
            if fname.endswith((".png", ".jpg", ".jpeg", ".bmp")):
                name = os.path.splitext(fname)[0]
                path = os.path.join(self._dir, fname)
                img = cv.imread(path)
                if img is not None:
                    self._templates[name] = img
                    self._log.info("Loaded template: %s (%dx%d)", name, *img.shape[:2][::-1])

    def add_template(self, name: str, image_bytes: bytes) -> str:
        cv = _get_cv2()
        self._ensure_loaded()
        path = os.path.join(self._dir, f"{name}.png")
        with open(path, "wb") as f:
            f.write(image_bytes)
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv.imdecode(nparr, cv.IMREAD_COLOR)
        if img is not None:
            self._templates[name] = img
            self._log.info("Template saved: %s (%dx%d)", name, *img.shape[:2][::-1])
        return path

    def remove_template(self, name: str) -> bool:
        self._ensure_loaded()
        self._templates.pop(name, None)
        path = os.path.join(self._dir, f"{name}.png")
        if os.path.exists(path):
            os.remove(path)
            return True
        return False

    def list_templates(self) -> list[dict]:
        self._ensure_loaded()
        return [{"name": n, "width": t.shape[1], "height": t.shape[0]} for n, t in self._templates.items()]

    def find(
        self, name_or_path: str, screenshot_bytes: bytes,
        threshold: float | None = None,
        roi: tuple | None = None,
    ) -> dict | None:
        cv = _get_cv2()
        self._ensure_loaded()
        # Accept file path or registered name
        template = None
        if name_or_path in self._templates:
            template = self._templates[name_or_path]
        elif os.path.exists(name_or_path):
            template = cv.imread(name_or_path)
            if template is not None:
                self._log.debug("Loaded template from path: %s", name_or_path)
        if template is None:
            self._log.error("Template not found: %s", name_or_path)
            return None
        th = threshold if threshold is not None else self._threshold
        nparr = np.frombuffer(screenshot_bytes, np.uint8)
        screen = cv.imdecode(nparr, cv.IMREAD_COLOR)
        if screen is None:
            return None
        ox, oy = 0, 0
        if roi and roi[2] > roi[0] and roi[3] > roi[1]:
            screen = screen[roi[1]:roi[3], roi[0]:roi[2]]
            ox, oy = roi[0], roi[1]
        th_h, tw = template.shape[:2]
        sh, sw = screen.shape[:2]
        if tw > sw or th_h > sh:
            return None
        result = cv.matchTemplate(screen, template, cv.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv.minMaxLoc(result)
        if max_val < th:
            return None
        x = max_loc[0] + ox + tw // 2
        y = max_loc[1] + oy + th_h // 2
        self._log.debug("Match '%s': conf=%.3f at (%d,%d)", name_or_path, max_val, x, y)
        return {"x": x, "y": y, "confidence": float(max_val)}

    def find_all(
        self, name: str, screenshot_bytes: bytes, threshold: float | None = None
    ) -> list[dict]:
        cv = _get_cv2()
        self._ensure_loaded()
        if name not in self._templates:
            return []
        template = self._templates[name]
        th = threshold if threshold is not None else self._threshold
        nparr = np.frombuffer(screenshot_bytes, np.uint8)
        screen = cv.imdecode(nparr, cv.IMREAD_COLOR)
        if screen is None:
            return []
        result = cv.matchTemplate(screen, template, cv.TM_CCOEFF_NORMED)
        th_h, tw = template.shape[:2]
        locations = []
        mask = np.zeros(result.shape, dtype=bool)
        while True:
            _, max_val, _, max_loc = cv.minMaxLoc(result)
            if max_val < th:
                break
            if mask[max_loc[1], max_loc[0]]:
                break
            x = max_loc[0] + tw // 2
            y = max_loc[1] + th_h // 2
            locations.append({"x": x, "y": y, "confidence": float(max_val)})
            y1 = max(0, max_loc[1] - th_h // 2)
            y2 = min(mask.shape[0], max_loc[1] + th_h // 2)
            x1 = max(0, max_loc[0] - tw // 2)
            x2 = min(mask.shape[1], max_loc[0] + tw // 2)
            mask[y1:y2, x1:x2] = True
            result[mask] = 0
        locations.sort(key=lambda m: m["confidence"], reverse=True)
        return locations
