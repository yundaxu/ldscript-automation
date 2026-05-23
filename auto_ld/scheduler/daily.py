"""每日任务调度器 — 读取 YAML 配置并按顺序执行任务。

从 configs/daily.yaml 加载任务列表，依次执行启用的任务。
支持两种任务类型:
  - script:   Python 用户脚本
  - pipeline: JSON 流水线
"""
import os

import yaml

from auto_ld.controller.adb import Adb
from auto_ld.controller.touch import Touch
from auto_ld.log import get_logger


class DailyScheduler:
    """每日任务调度器。

    读取 configs/daily.yaml 配置，按顺序执行启用的任务。
    执行前确保模拟器已运行并建立 ADB 连接。

    YAML 配置格式:
        ldplayer:
          index: 1
        tasks:
          - name: "任务名"
            type: script
            file: "start_app"
            enabled: true
            config:
              package: "com.example.app"
    """

    def __init__(
        self, config_path: str, ld, loader, adb_provider=None
    ) -> None:
        """初始化调度器。

        Args:
            config_path: YAML 配置文件路径
            ld: auto_ld.emulator.ldplayer.LDPlayer 实例
            loader: auto_ld.runtime.loader.ScriptLoader 实例
            adb_provider: 可选的回调函数，返回 (adb, touch) 元组
        """
        self._config_path = config_path
        self._ld = ld
        self._loader = loader
        self._adb_provider = adb_provider
        self._log = get_logger("Scheduler")

    def load_config(self) -> dict:
        """加载 YAML 配置文件。

        Returns:
            配置字典，文件不存在时返回空任务列表
        """
        if not os.path.exists(self._config_path):
            self._log.warning("Config not found: %s", self._config_path)
            return {"tasks": []}
        with open(self._config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def run(self) -> bool:
        """执行所有已启用的每日任务。

        执行流程:
        1. 加载配置
        2. 确保模拟器运行
        3. 建立 ADB 连接
        4. 顺序执行任务

        Returns:
            True 表示所有启用任务均成功
        """
        config = self.load_config()
        tasks = config.get("tasks", [])

        if not tasks:
            self._log.warning("No tasks configured")
            return True

        # 确保模拟器运行
        if not self._ld.running():
            self._log.info("Emulator not running, launching ...")
            if not self._ld.launch():
                self._log.error("Failed to launch emulator")
                return False

        # 创建 ADB / Touch 连接
        if self._adb_provider:
            adb, touch = self._adb_provider()
        else:
            adb_path = self._ld.adb_path()
            serial = self._ld.serial()
            adb = Adb(adb_path, serial)
            touch = Touch(adb)

        if not adb.ok():
            self._log.error("ADB connection failed")
            return False

        w, h = adb.res()
        self._log.info("Device ready: %dx%d", w, h)

        # 执行任务
        success = 0
        fail = 0
        total = 0

        for task in tasks:
            if not task.get("enabled", True):
                self._log.info(
                    "Task skipped (disabled): %s", task.get("name", "?")
                )
                continue
            total += 1
            self._log.info(
                "--- Task %d: %s ---", total, task.get("name", "?")
            )
            if self.run_task(task, adb, touch):
                success += 1
            else:
                fail += 1

        self._log.info(
            "Daily tasks complete: %d success, %d failed, %d total",
            success, fail, total,
        )
        return fail == 0

    def run_task(self, task: dict, adb, touch) -> bool:
        """执行单个任务。

        Args:
            task: 任务配置字典 (含 type, file, config 字段)
            adb: Adb 控制器实例
            touch: Touch 控制器实例

        Returns:
            True 表示任务执行成功
        """
        file_name = task.get("file", "")
        task_config = task.get("config", {})

        if not file_name:
            self._log.error("Task has no file field: %s", task)
            return False

        return self._loader.run(file_name, adb, touch, config=task_config)

    def get_tasks(self) -> dict:
        """获取当前任务配置。

        Returns:
            完整的 YAML 配置字典
        """
        return self.load_config()

    def save_tasks(self, config: dict) -> bool:
        """保存任务配置到 YAML 文件。

        Args:
            config: 完整配置字典

        Returns:
            True 表示保存成功
        """
        config_dir = os.path.dirname(self._config_path)
        if config_dir:
            os.makedirs(config_dir, exist_ok=True)
        with open(self._config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                config, f, allow_unicode=True, default_flow_style=False
            )
        self._log.info("Tasks saved to %s", self._config_path)
        return True
