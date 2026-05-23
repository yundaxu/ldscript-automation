"""高级触控封装 — 在 Adb 控制器上提供便捷的触控操作。

提供带延时、长按、随机点击等高级触控语义。
"""
import time

from auto_ld.log import get_logger


class Touch:
    """高级触控操作封装。

    在底层 ADB 控制器之上提供更丰富的触控语义:
    - 点击 (带可选延时)
    - 长按
    - 滑动
    - 返回/主页键

    所有操作自动附带短暂延时以模拟真实操作节奏。
    """

    def __init__(self, adb) -> None:
        """初始化触控控制器。

        Args:
            adb: auto_ld.controller.adb.Adb 实例
        """
        self._adb = adb
        self._log = get_logger("Touch")

    def click(self, x: int, y: int, delay: float = 0.05) -> bool:
        """点击指定坐标，并等待指定延时。

        Args:
            x: 横坐标
            y: 纵坐标
            delay: 操作后延时 (秒)，默认 0.05s

        Returns:
            True 表示操作成功
        """
        result = self._adb.tap(x, y)
        if delay > 0:
            time.sleep(delay)
        return result

    def long_press(self, x: int, y: int, duration: int = 1000) -> bool:
        """长按指定坐标。

        通过起始坐标和终点坐标相同的滑动模拟长按。

        Args:
            x: 横坐标
            y: 纵坐标
            duration: 按压持续时间 (毫秒)，默认 1000ms

        Returns:
            True 表示操作成功
        """
        return self._adb.swipe(x, y, x, y, duration)

    def swipe(
        self, x1: int, y1: int, x2: int, y2: int, duration: int = 300
    ) -> bool:
        """滑动操作。

        Args:
            x1, y1: 起始坐标
            x2, y2: 终点坐标
            duration: 滑动时间 (毫秒)，默认 300ms

        Returns:
            True 表示操作成功
        """
        return self._adb.swipe(x1, y1, x2, y2, duration)

    def back(self) -> bool:
        """按下返回键，操作后等待 0.3s。"""
        result = self._adb.back()
        time.sleep(0.3)
        return result

    def home(self) -> bool:
        """按下主页键，操作后等待 0.3s。"""
        result = self._adb.home()
        time.sleep(0.3)
        return result
