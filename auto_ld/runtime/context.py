"""ScriptContext — 用户脚本运行时 API。

用户编写自动化脚本时通过 ctx 对象访问所有控制能力。
这是用户脚本与框架之间的核心接口。
"""
import random
import time

from auto_ld.log import get_logger


class ScriptContext:
    """用户脚本运行时上下文。

    脚本通过 ctx 实例访问:
    - ctx.adb   — ADB 控制器 (截图/按键/应用启动)
    - ctx.touch — 触控控制器 (点击/滑动/长按)
    - ctx.log   — 日志对象
    - ctx.config — 任务配置参数

    Usage in user scripts:
        def run(ctx):
            ctx.wait(2)
            ctx.touch.click(500, 300)
            ctx.adb.start("com.android.settings")
            ctx.log.info("完成")
            return True
    """

    def __init__(
        self, adb, touch, log=None, config: dict | None = None,
        on_screencap=None,
    ) -> None:
        self.adb = adb
        self.touch = touch
        self.log = log or get_logger("Script")
        self.config = config or {}
        self._on_screencap = on_screencap
        self._start_time: float | None = None
        self._steps = 0

    def wait(self, sec: float) -> None:
        """等待指定秒数。

        Args:
            sec: 等待时长 (秒)，支持小数
        """
        self._steps += 1
        self.log.debug("Waiting %.1fs (step #%d)", sec, self._steps)
        time.sleep(sec)

    def cap(self) -> bytes:
        """截取当前屏幕画面。

        Returns:
            PNG 格式截图字节数据
        """
        self._steps += 1
        self.log.debug("Screenshot (step #%d)", self._steps)
        img = self.adb.cap()
        if self._on_screencap:
            self._on_screencap(img)
        return img

    def rand_tap(self, x1: int, x2: int, y1: int, y2: int) -> None:
        """在指定矩形区域内随机点击。

        Args:
            x1, x2: 横坐标范围 (min, max)
            y1, y2: 纵坐标范围 (min, max)
        """
        x = random.randint(x1, x2)
        y = random.randint(y1, y2)
        self._steps += 1
        self.log.debug(
            "Random tap at (%d, %d) in rect [%d-%d, %d-%d] (step #%d)",
            x, y, x1, x2, y1, y2, self._steps,
        )
        self.touch.click(x, y)

    def swipe_area(
        self,
        x1: int, x2: int,
        y1: int, y2: int,
        distance: int = 300,
        times: int = 1,
    ) -> None:
        """在区域内多次随机滑动。

        Args:
            x1, x2: 横坐标范围
            y1, y2: 纵坐标范围
            distance: 滑动最大距离 (像素)
            times: 滑动次数
        """
        for i in range(times):
            sx = random.randint(x1, x2)
            sy = random.randint(y1, y2)
            ex = max(x1, min(x2, sx + random.randint(-distance, distance)))
            ey = max(y1, min(y2, sy + random.randint(-distance, distance)))
            self._steps += 1
            self.log.debug(
                "Swipe area [%d/%d]: (%d,%d)->(%d,%d) (step #%d)",
                i + 1, times, sx, sy, ex, ey, self._steps,
            )
            self.touch.swipe(sx, sy, ex, ey)

    def start_timing(self) -> None:
        """开始计时 (用于测量脚本执行时长)。"""
        self._start_time = time.time()

    def elapsed(self) -> float:
        """获取从 start_timing() 到现在的时间。

        Returns:
            已经过的时间 (秒)
        """
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time

    def step_count(self) -> int:
        """获取当前已执行的动作步数。"""
        return self._steps
