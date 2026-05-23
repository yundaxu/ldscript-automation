"""ADB 控制器 — 封装 Android Debug Bridge 协议进行设备交互。

MAA 框架模式参考:
  - 截图使用 exec-out pipe 方法 (adb exec-out screencap -p)，无临时文件
  - 所有命令内置自动重试 (3 次)
  - 支持触控、应用管理、Shell 命令
"""
import re
import subprocess
import time

from auto_ld.log import get_logger


class Adb:
    """ADB 设备控制器。

    封装 ADB 命令行协议，提供截图、触控、应用管理等功能。
    所有命令均通过 subprocess 执行并内置重试机制。

    Attributes:
        serial: 设备串口号
    """

    def __init__(self, adb_path: str, serial: str) -> None:
        self._adb = adb_path
        self._serial = serial
        self._log = get_logger("Adb")

    def _run(self, *args: str, timeout: int = 10, retries: int = 3) -> str:
        """执行 ADB 命令并返回 stdout。

        Args:
            *args: ADB 子命令参数
            timeout: 单次执行超时 (秒)
            retries: 失败重试次数

        Returns:
            命令 stdout 输出 (去除首尾空白)

        Raises:
            RuntimeError: 所有重试均失败
        """
        cmd = [self._adb, "-s", self._serial] + list(args)
        self._log.debug("ADB: %s", " ".join(cmd))

        last_error = ""
        for attempt in range(retries):
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=timeout
                )
                if result.returncode != 0 and result.stderr:
                    last_error = result.stderr.strip()
                    self._log.debug(
                        "ADB attempt %d/%d stderr: %s",
                        attempt + 1, retries, last_error,
                    )
                    if attempt < retries - 1:
                        time.sleep(0.5)
                        continue
                return result.stdout.strip()
            except subprocess.TimeoutExpired:
                last_error = f"Timeout after {timeout}s"
                if attempt < retries - 1:
                    time.sleep(0.5)
                    continue
            except Exception as e:
                last_error = str(e)
                if attempt < retries - 1:
                    time.sleep(0.5)
                    continue

        raise RuntimeError(
            f"ADB command failed after {retries} attempts: {last_error}"
        )

    # ---- connection ----

    def ok(self) -> bool:
        """检查设备连接是否正常。"""
        try:
            out = self._run("shell", "echo", "ok", timeout=5)
            return "ok" in out.lower()
        except Exception:
            return False

    # ---- screenshot ----

    def cap(self) -> bytes:
        """通过 exec-out pipe 截图。

        使用 MAA 框架同款方案: adb exec-out screencap -p
        直接在管道中获取 PNG，无需在设备上创建临时文件。

        Returns:
            PNG 格式的截图字节数据

        Raises:
            RuntimeError: 截图失败
        """
        cmd = [self._adb, "-s", self._serial, "exec-out", "screencap", "-p"]
        self._log.debug("Screenshot via exec-out pipe")
        result = subprocess.run(cmd, capture_output=True, timeout=10)
        if result.returncode != 0:
            msg = result.stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"Screenshot failed: {msg}")
        return result.stdout

    # ---- touch ----

    def tap(self, x: int, y: int) -> bool:
        """点击屏幕坐标。

        Args:
            x: 横坐标
            y: 纵坐标

        Returns:
            True 表示操作成功
        """
        try:
            self._run("shell", "input", "tap", str(x), str(y))
            self._log.debug("Tap: (%d, %d)", x, y)
            return True
        except Exception as e:
            self._log.error("Tap failed: %s", e)
            return False

    def swipe(
        self, x1: int, y1: int, x2: int, y2: int, duration: int = 300
    ) -> bool:
        """滑动操作。

        Args:
            x1, y1: 起始坐标
            x2, y2: 终点坐标
            duration: 滑动持续时间 (毫秒)

        Returns:
            True 表示操作成功
        """
        try:
            self._run(
                "shell", "input", "swipe",
                str(x1), str(y1), str(x2), str(y2), str(duration),
            )
            self._log.debug(
                "Swipe: (%d,%d) -> (%d,%d) dur=%d",
                x1, y1, x2, y2, duration,
            )
            return True
        except Exception as e:
            self._log.error("Swipe failed: %s", e)
            return False

    # ---- application ----

    def start(self, package: str) -> bool:
        """启动应用。

        Args:
            package: 应用包名

        Returns:
            True 表示操作成功
        """
        try:
            self._run(
                "shell", "monkey", "-p", package,
                "-c", "android.intent.category.LAUNCHER", "1",
            )
            self._log.info("Started: %s", package)
            return True
        except Exception as e:
            self._log.error("Start app failed: %s", e)
            return False

    def stop(self, package: str) -> bool:
        """强制停止应用。

        Args:
            package: 应用包名

        Returns:
            True 表示操作成功
        """
        try:
            self._run("shell", "am", "force-stop", package)
            self._log.info("Stopped: %s", package)
            return True
        except Exception as e:
            self._log.error("Stop app failed: %s", e)
            return False

    # ---- key events ----

    def key(self, keycode: int) -> bool:
        """发送按键事件。

        Args:
            keycode: Android 按键码 (3=Home, 4=Back, 26=Power)

        Returns:
            True 表示操作成功
        """
        try:
            self._run("shell", "input", "keyevent", str(keycode))
            self._log.debug("Key: %d", keycode)
            return True
        except Exception as e:
            self._log.error("Key failed: %s", e)
            return False

    def back(self) -> bool:
        """按下返回键。"""
        return self.key(4)

    def home(self) -> bool:
        """按下主页键。"""
        return self.key(3)

    # ---- screen info ----

    def res(self) -> tuple[int, int]:
        """获取屏幕分辨率。

        Returns:
            (宽度, 高度) 像素值，默认 1080x1920
        """
        output = self._run("shell", "wm", "size")
        match = re.search(r"(\d+)x(\d+)", output)
        if match:
            w, h = int(match.group(1)), int(match.group(2))
            self._log.debug("Resolution: %dx%d", w, h)
            return w, h
        self._log.warning("Cannot parse screen size, using default 1080x1920")
        return 1080, 1920

    # ---- shell / text ----

    def shell(self, cmd: str) -> str:
        """在设备上执行任意 Shell 命令。

        Args:
            cmd: Shell 命令

        Returns:
            命令 stdout 输出
        """
        return self._run("shell", cmd)

    def input_text(self, text: str) -> bool:
        """输入文本到当前焦点输入框。

        Args:
            text: 要输入的文本

        Returns:
            True 表示操作成功
        """
        try:
            escaped = text.replace(" ", r"%s").replace('"', r"\"")
            self._run("shell", "input", "text", escaped)
            self._log.debug("Input: %s", text)
            return True
        except Exception as e:
            self._log.error("Input text failed: %s", e)
            return False

    # ---- package queries ----

    def packages_running(self) -> str:
        """获取前台运行应用的包名。

        Returns:
            包名字符串，获取失败返回空字符串
        """
        output = self._run("shell", "dumpsys", "activity", "activities")
        match = re.search(r"mResumedActivity.*?(\S+?)/(\S+?)\s", output)
        if match:
            return match.group(1)
        return ""

    def packages_search(self, query: str) -> list[str]:
        """搜索已安装的应用包。

        Args:
            query: 搜索关键词

        Returns:
            匹配的包名列表
        """
        output = self._run("shell", "pm", "list", "packages")
        packages: list[str] = []
        for line in output.split("\n"):
            line = line.strip()
            if line.startswith("package:"):
                pkg = line[8:]
                if query.lower() in pkg.lower():
                    packages.append(pkg)
        return packages
