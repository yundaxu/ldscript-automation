"""OCR 文字识别模块 — 在屏幕截图中识别文字。

基于 easyocr 实现，支持中英文混合识别。
MAA 框架使用 PaddleOCR，此处使用更轻量的 easyocr 作为替代。
"""
import os

import numpy as np

from auto_ld.log import get_logger

_easyocr = None
_reader = None
_reader_langs = None


def _get_reader(languages=None):
    """Lazy-load easyocr Reader (首次加载会下载模型，约 100MB)。"""
    global _easyocr, _reader, _reader_langs
    if languages is None:
        languages = ["ch_sim", "en"]
    if _reader is not None and _reader_langs == languages:
        return _reader
    if _easyocr is None:
        try:
            import easyocr
            _easyocr = easyocr
        except ImportError:
            raise ImportError(
                "easyocr is required. Install: pip install easyocr"
            )
    from auto_ld._compat import get_models_dir, is_frozen
    models_dir = get_models_dir()
    if is_frozen():
        os.makedirs(models_dir, exist_ok=True)
    _reader = _easyocr.Reader(
        languages, gpu=False, model_storage_directory=models_dir,
    )
    _reader_langs = languages
    return _reader


class OCREngine:
    """OCR 文字识别引擎。

    使用 easyocr 在屏幕截图中识别中英文文字。

    Usage:
        ocr = OCREngine()
        results = ocr.read(screenshot_bytes)
        # → [{"text": "确定", "x": 500, "y": 300, "confidence": 0.95}, ...]
        found = ocr.find("确定", screenshot_bytes)
        # → {"x": 500, "y": 300, "confidence": 0.95}
    """

    def __init__(self, languages: list[str] | None = None) -> None:
        self._log = get_logger("OCR")
        self._langs = languages or ["ch_sim", "en"]

    def read(self, image_bytes: bytes) -> list[dict]:
        """识别图片中所有文字。

        Args:
            image_bytes: PNG 图像字节数据

        Returns:
            识别结果列表，每项含 text / x / y / width / height / confidence
        """
        reader = _get_reader(self._langs)
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = nparr  # easyocr 可以直接处理 bytes

        try:
            raw = reader.readtext(image_bytes)
        except Exception:
            # Fallback: decode to numpy array
            import cv2
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            raw = reader.readtext(img)

        results = []
        for bbox, text, conf in raw:
            if not text.strip():
                continue
            x1, y1 = int(bbox[0][0]), int(bbox[0][1])
            x2, y2 = int(bbox[2][0]), int(bbox[2][1])
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            results.append({
                "text": text.strip(),
                "x": cx,
                "y": cy,
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "confidence": round(float(conf), 3),
            })
        self._log.info("OCR found %d text region(s)", len(results))
        return results

    def find(
        self, target: str, image_bytes: bytes,
        roi: tuple | None = None,
    ) -> dict | None:
        """在图片中查找指定文字的位置。

        Args:
            target: 要查找的文字
            image_bytes: PNG 图像字节数据
            roi: 搜索区域 (x1, y1, x2, y2)

        Returns:
            匹配结果 dict (含 x/y/confidence)，未找到返回 None
        """
        results = self.read(image_bytes)
        target_lower = target.lower().strip()

        best = None
        for r in results:
            if roi:
                cx, cy = r["x"], r["y"]
                if not (roi[0] <= cx <= roi[2] and roi[1] <= cy <= roi[3]):
                    continue
            text_lower = r["text"].lower()
            if target_lower in text_lower or text_lower in target_lower:
                if best is None or r["confidence"] > best["confidence"]:
                    best = r
        if best:
            self._log.info(
                "OCR matched '%s' → '%s' at (%d,%d) conf=%.3f",
                target, best["text"], best["x"], best["y"], best["confidence"],
            )
        else:
            self._log.info("OCR did not find '%s'", target)
        return best

    def contains(self, target: str, image_bytes: bytes) -> bool:
        """检查图片中是否包含指定文字（模糊匹配）。

        Args:
            target: 要查找的文字
            image_bytes: PNG 图像字节数据

        Returns:
            True 表示找到匹配
        """
        results = self.read(image_bytes)
        target_lower = target.lower().strip()
        for r in results:
            text_lower = r["text"].lower().strip()
            if target_lower in text_lower or text_lower in target_lower:
                return True
        return False
