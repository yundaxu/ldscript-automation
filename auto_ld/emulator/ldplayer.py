"""雷电模拟器管理器 — 通过 ldconsole.exe CLI 控制模拟器实例。

MAA 框架模式参考:
  - 通过 ldconsole.exe 管理模拟器生命周期 (list/launch/quit/isrunning)
  - ADB 串口通过指纹匹配或端口计算 (base 5554 + index*2)
  - 支持自动检测多版本安装路径
  - 实例信息缓存到 configs/instances.json，避免每次调起雷电多开器
"""
from __future__ import annotations

import glob as _glob
import json
import os
import subprocess
import time

from auto_ld.log import get_logger

COMMON_PATHS: list[str] = [
    r"D:\leidian\LDPlayer9",
    r"C:\leidian\LDPlayer9",
    r"D:\LDPlayer\LDPlayer9",
    r"C:\LDPlayer\LDPlayer9",
]


class LDPlayer:
    """雷电模拟器管理器。

    通过 ldconsole.exe 命令行工具管理模拟器实例的启动、关闭、状态查询。
    支持自动检测安装路径和 ADB 串口匹配。

    Attributes:
        index: 当前管理的模拟器实例序号 (从 1 开始)
        path: 雷电模拟器安装目录
    """

    def __init__(self, ld_path: str | None = None, index: int = 1) -> None:
        self._index = index
        self._log = get_logger("LDPlayer")

        if ld_path and os.path.exists(os.path.join(ld_path, "ldconsole.exe")):
            self._ld_path = ld_path
        else:
            self._ld_path = self._detect_path()

        self._ldconsole = os.path.join(self._ld_path, "ldconsole.exe")
        if not os.path.exists(self._ldconsole):
            raise FileNotFoundError(
                f"ldconsole.exe not found at {self._ldconsole}"
            )

        self._log.info("LDPlayer path: %s, index: %d", self._ld_path, index)

    # ---- path detection ----

    def _detect_path(self) -> str:
        """自动检测雷电模拟器安装路径。

        按优先级查找:
        1. 常见固定路径
        2. Program Files 目录下含有 leidian/LDPlayer 的子目录
        """
        for p in COMMON_PATHS:
            if os.path.exists(os.path.join(p, "ldconsole.exe")):
                return p

        for base in [
            r"C:\Program Files",
            r"D:\Program Files",
            r"C:\Program Files (x86)",
        ]:
            if not os.path.exists(base):
                continue
            for pattern in ["*leidian*", "*LDPlayer*"]:
                for item in _glob.glob(os.path.join(base, pattern)):
                    if os.path.exists(os.path.join(item, "ldconsole.exe")):
                        return item

        raise FileNotFoundError(
            "Cannot find LDPlayer installation. Please set ld_path manually.\n"
            f"Searched: {COMMON_PATHS}"
        )

    # ---- ldconsole wrapper ----

    def ldconsole(self, *args: str) -> str:
        """调用 ldconsole.exe 并返回 stdout。

        Args:
            *args: 传递给 ldconsole 的参数 (如 "list", "launch --index 1")

        Returns:
            stdout 输出字符串 (去除首尾空白)
        """
        cmd = [self._ldconsole] + list(args)
        self._log.debug("ldconsole: %s", " ".join(cmd))
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15
            )
            if result.returncode != 0 and result.stderr:
                self._log.debug("ldconsole stderr: %s", result.stderr.strip())
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            self._log.error("ldconsole timeout: %s", " ".join(cmd))
            return ""
        except Exception as e:
            self._log.error("ldconsole error: %s", e)
            return ""

    # ---- instance management ----

    def list(self) -> list[dict]:
        """列出所有已安装的模拟器实例。

        Returns:
            实例列表，每项包含 index / name / top_window

        LDPlayer 9+ 输出格式: 每行一个实例名，索引按行号 (从 0 开始)。
        """
        output = self.ldconsole("list")
        self._log.debug("ldconsole list raw output: %r", output)
        if not output:
            self._log.warning("ldconsole list returned empty output")
            return []

        instances: list[dict] = []
        lines = output.split("\n")

        # LDPlayer 9+ simple format: one name per line
        # Index is 0-based by line position
        if not any("," in line for line in lines if line.strip()):
            for idx, line in enumerate(lines):
                name = line.strip()
                if name:
                    instances.append({
                        "index": idx,
                        "name": name,
                        "top_window": "",
                    })
            self._log.info("Found %d instance(s) (simple format)", len(instances))
            return instances

        # Legacy comma-separated format: "index,name,top_window"
        for line in lines:
            line = line.strip()
            if not line:
                continue
            parts = line.replace("\t", ",").split(",")
            if len(parts) >= 2:
                try:
                    idx = int(parts[0].strip())
                    name = parts[1].strip()
                    top_window = parts[2].strip() if len(parts) > 2 else ""
                    instances.append({
                        "index": idx,
                        "name": name,
                        "top_window": top_window,
                    })
                except ValueError:
                    self._log.debug("Unparseable instance line: %r", line)

        self._log.info("Found %d instance(s) (CSV format): %s", len(instances), instances)
        return instances

    def list_cached(self) -> list[dict]:
        """从缓存文件读取实例列表，避免调起雷电多开器。

        缓存文件: configs/instances.json
        """
        cache_path = os.path.join("configs", "instances.json")
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                    if cached:
                        self._log.debug("Loaded %d cached instance(s)", len(cached))
                        return cached
            except (json.JSONDecodeError, OSError) as e:
                self._log.warning("Cache read error: %s", e)

        # Fallback: query ldconsole and cache
        instances = self.list()
        if instances:
            self._save_cache(instances)
        return instances

    def _save_cache(self, instances: list[dict]) -> None:
        """保存实例列表到缓存。"""
        os.makedirs("configs", exist_ok=True)
        cache_path = os.path.join("configs", "instances.json")
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(instances, f, ensure_ascii=False, indent=2)
            self._log.debug("Instance cache saved: %s", cache_path)
        except OSError as e:
            self._log.warning("Cache write error: %s", e)

    def refresh_cache(self) -> list[dict]:
        """强制刷新实例缓存。"""
        instances = self.list()
        if instances:
            self._save_cache(instances)
        return instances

    def instance_status(self, index: int | None = None) -> dict:
        """查询实例运行状态。返回 {running: bool, ...}"""
        idx = index if index is not None else self._index
        output = self.ldconsole("isrunning", "--index", str(idx))
        return {
            "index": idx,
            "running": "running" in output.lower(),
            "raw": output,
        }

    def running(self) -> bool:
        """检查当前实例是否正在运行。"""
        output = self.ldconsole("isrunning", "--index", str(self._index))
        return "running" in output.lower()

    def launch(self) -> bool:
        """启动模拟器实例并等待 ADB 就绪。

        Returns:
            True 表示启动成功
        """
        if self.running():
            self._log.info("Emulator already running")
            return True

        self._log.info("Launching instance %d ...", self._index)
        self.ldconsole("launch", "--index", str(self._index))

        for i in range(30):
            time.sleep(1)
            if self.running():
                self._log.info("Emulator launched successfully")
                return True

        self._log.error("Emulator launch timeout")
        return False

    def quit(self) -> bool:
        """关闭模拟器实例。

        Returns:
            True 表示关闭成功
        """
        self._log.info("Quitting instance %d ...", self._index)
        self.ldconsole("quit", "--index", str(self._index))
        time.sleep(1)
        return not self.running()

    # ---- ADB ----

    def serial(self) -> str:
        """获取当前实例的 ADB 串口号。

        检测策略 (按优先级):
        1. 通过 ldconsole adb 命令直接获取
        2. 按 LDPlayer 端口规则计算: emulator-5554 + index*2
        3. 从配置文件读取

        Returns:
            ADB 串口字符串，如 "emulator-5556"
        """
        # 方法 1: ldconsole adb 命令
        output = self.ldconsole(
            "adb", "--index", str(self._index), "--command", "get-serialno"
        )
        if output and "error" not in output.lower() and output.strip():
            serial = output.strip()
            self._log.info("ADB serial (from adb): %s", serial)
            return serial

        # 方法 2: 端口计算 (雷电默认规则)
        port = 5554 + self._index * 2
        serial = f"emulator-{port}"
        self._log.info("ADB serial (calculated): %s", serial)
        return serial

    def adb_path(self) -> str:
        """返回雷电模拟器自带的 adb.exe 路径。"""
        return os.path.join(self._ld_path, "adb.exe")

    # ---- properties ----

    @property
    def index(self) -> int:
        return self._index

    @index.setter
    def index(self, value: int) -> None:
        self._index = value

    @property
    def path(self) -> str:
        return self._ld_path
