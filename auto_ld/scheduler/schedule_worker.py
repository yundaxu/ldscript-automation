"""定时任务后台调度器 — 从 settings.json 读取定时配置并在后台执行。

每半分钟检查一次当前时间，匹配到启用的定时任务后:
1. 检查目标模拟器实例是否运行，若未运行且启用自动启动则拉起实例
2. 等待 ADB 就绪后执行脚本
3. 若勾选了"完成后关闭"，脚本结束后关闭模拟器
"""
import json
import os
import threading
import time
from datetime import datetime

from auto_ld._compat import get_project_root
from auto_ld.log import get_logger

_POLL_SEC = 60  # 轮询间隔（秒）
_CACHE_TTL = 30  # 缓存刷新间隔（秒）


class ScheduleWorker:
    """定时任务后台工作器。"""

    def __init__(self) -> None:
        self._log = get_logger("ScheduleWorker")
        self._settings_path = os.path.join(
            get_project_root(), "configs", "settings.json"
        )
        self._lock = threading.Lock()
        self._running = False
        self._fired_minute = ""      # 本轮已触发的 HH:MM，防止同分钟重复
        self._last_check_date = ""

        self._schedules: list[dict] = []
        self._cache_ts: float = 0.0
        self._tick_count: int = 0

    # ---- 公开接口 ----

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._refresh_cache()
        self._log.info("ScheduleWorker 已启动 (轮询 %ds)", _POLL_SEC)
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self) -> None:
        self._running = False
        self._log.info("ScheduleWorker 正在停止...")

    def refresh(self) -> None:
        """强制刷新调度缓存，重置本轮触发标记以允许立即重试。"""
        self._refresh_cache()
        self._fired_minute = ""
        self._log.info("缓存已刷新，触发标记已重置")

    def status(self) -> dict:
        with self._lock:
            scheds = list(self._schedules)
        enabled_count = sum(1 for s in scheds if s.get("enabled"))
        return {
            "running": self._running,
            "current_time": datetime.now().strftime("%H:%M:%S"),
            "total_tasks": len(scheds),
            "enabled_tasks": enabled_count,
            "tasks": scheds,
        }

    def trigger_now(self) -> dict:
        """手动立即触发所有已启用的定时任务（测试用）。"""
        with self._lock:
            enabled = [s for s in self._schedules if s.get("enabled") and s.get("script")]
        if not enabled:
            return {"triggered": 0, "message": "没有启用的定时任务"}
        for s in enabled:
            self._log.info("手动触发: %s", s.get("script"))
            threading.Thread(target=self._execute_task, args=(dict(s),), daemon=True).start()
        return {"triggered": len(enabled), "tasks": [s.get("script") for s in enabled]}

    # ---- 磁盘读写 ----

    def _load_from_disk(self) -> list[dict]:
        if not os.path.exists(self._settings_path):
            return []
        try:
            with open(self._settings_path, "r", encoding="utf-8") as f:
                return json.load(f).get("schedule", [])
        except (json.JSONDecodeError, OSError) as e:
            self._log.error("读取 settings.json 失败: %s", e)
            return []

    def _refresh_cache(self) -> None:
        with self._lock:
            self._schedules = self._load_from_disk()
            self._cache_ts = time.time()

    # ---- 主循环 ----

    def _loop(self) -> None:
        while self._running:
            try:
                self._refresh_cache()
                self._tick()
                self._tick_count += 1
            except Exception as e:
                self._log.error("ScheduleWorker 异常: %s", e)
            time.sleep(_POLL_SEC)

    def _tick(self) -> None:
        """检查当前时间是否匹配定时任务并触发。"""
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        current_date = now.strftime("%Y-%m-%d")

        # 日期翻转 — 重置所有状态
        if current_date != self._last_check_date:
            self._fired_minute = ""
            self._last_check_date = current_date
            self._log.info("日期切换: %s", current_date)

        # 本分钟已触发过 - 跳过
        if self._fired_minute == current_time:
            return

        with self._lock:
            schedules = self._schedules

        matched = [
            s for s in schedules
            if s.get("enabled") and s.get("script") and s.get("time") == current_time
        ]

        if not matched:
            return

        # 标记本轮已触发，防止同分钟重复
        self._fired_minute = current_time

        self._log.info(">>> 时间匹配 %s: %d 个任务", current_time, len(matched))

        for s in matched:
            script = s.get("script", "?")
            repeat = s.get("repeat", "daily")
            self._log.info(">>> 触发: %s (重复=%s, 实例=%s)", script, repeat, s.get("instance_index", 1))

            if repeat == "once":
                self._disable_in_cache(s)

            threading.Thread(
                target=self._execute_task,
                args=(dict(s),),
                daemon=True,
            ).start()

    # ---- 任务执行（独立线程） ----

    def _execute_task(self, schedule: dict) -> None:
        script = schedule.get("script", "")
        instance_index = schedule.get("instance_index", 1)
        auto_launch = schedule.get("auto_launch", False)
        auto_quit = schedule.get("auto_quit", False)

        self._log.info("[%s] 开始: 实例=%d auto_launch=%s auto_quit=%s", script, instance_index, auto_launch, auto_quit)

        try:
            from auto_ld.emulator.ldplayer import LDPlayer
            from auto_ld.controller.adb import Adb
            from auto_ld.controller.touch import Touch
            from auto_ld.runtime.loader import ScriptLoader

            # 读取连接设置和启动设置
            conn = {}
            emulator_path = None
            try:
                if os.path.exists(self._settings_path):
                    with open(self._settings_path, "r", encoding="utf-8") as f:
                        full = json.load(f)
                        conn = full.get("connection", {})
                        emulator_path = full.get("launch", {}).get("emulator_path") or None
            except (json.JSONDecodeError, OSError):
                pass

            ld = LDPlayer(ld_path=emulator_path, index=instance_index)
            self._log.info("[%s] LDPlayer: %s", script, ld.path)

            if not ld.running():
                if auto_launch:
                    self._log.info("[%s] 实例 %d 未运行，启动中...", script, instance_index)
                    if not ld.launch():
                        self._log.error("[%s] 启动实例 %d 失败", script, instance_index)
                        return
                    self._log.info("[%s] 实例 %d 启动成功，等待 20s 稳定...", script, instance_index)
                    time.sleep(20)
                else:
                    self._log.error("[%s] 实例 %d 未运行且未启用自动启动", script, instance_index)
                    return
            else:
                self._log.info("[%s] 实例 %d 已运行", script, instance_index)

            # 优先使用设置中的 ADB 路径和连接地址
            adb_path = conn.get("adb_path") or ld.adb_path()
            serial = conn.get("address") or ld.serial()
            adb = Adb(adb_path, serial)
            touch = Touch(adb)

            if not adb.ok():
                self._log.error("[%s] ADB 连接失败: %s", script, serial)
                return

            w, h = adb.res()
            self._log.info("[%s] 设备就绪: %s %dx%d", script, serial, w, h)

            loader = ScriptLoader()
            success = loader.run(script, adb, touch)
            self._log.info("[%s] 脚本执行%s", script, "成功" if success else "失败")

            if auto_quit:
                self._log.info("[%s] 关闭实例 %d...", script, instance_index)
                ld.quit()

        except FileNotFoundError as e:
            self._log.error("[%s] LDPlayer 未找到: %s", script, e)
        except ImportError as e:
            self._log.error("[%s] 依赖导入失败: %s", script, e)
        except Exception as e:
            self._log.error("[%s] 异常: %s", script, e, exc_info=True)

    # ---- once 模式 ----

    def _disable_in_cache(self, schedule: dict) -> None:
        script = schedule.get("script", "")
        sched_time = schedule.get("time", "")
        with self._lock:
            for s in self._schedules:
                if s.get("script") == script and s.get("time") == sched_time and s.get("enabled"):
                    s["enabled"] = False
                    break
        self._write_disable(schedule)

    def _write_disable(self, schedule: dict) -> None:
        try:
            script = schedule.get("script", "")
            sched_time = schedule.get("time", "")
            with open(self._settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for s in data.get("schedule", []):
                if s.get("script") == script and s.get("time") == sched_time:
                    s["enabled"] = False
                    break
            with open(self._settings_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._log.info("once 任务已禁用: %s @ %s", script, sched_time)
        except (json.JSONDecodeError, OSError) as e:
            self._log.error("写回禁用失败: %s", e)
