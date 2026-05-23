"""模拟器脚本自助 Web Panel — 启动 Web 控制面板。

用法:
    python panel.py
    然后浏览器打开 http://localhost:5890
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from auto_ld._compat import get_project_root
from auto_ld.web import create_app
from auto_ld.emulator.ldplayer import LDPlayer
from auto_ld.runtime.loader import ScriptLoader
from auto_ld.scheduler.daily import DailyScheduler
from auto_ld.scheduler.schedule_worker import ScheduleWorker
from auto_ld.log import get_logger


def _load_settings() -> dict:
    """从 configs/settings.json 加载设置。"""
    path = os.path.join(get_project_root(), "configs", "settings.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def main() -> None:
    logger = get_logger("panel")

    logger.info("模拟器脚本自助 Web Panel 初始化...")

    # 加载设置
    settings = _load_settings()
    launch_cfg = settings.get("launch", {})
    conn_cfg = settings.get("connection", {})

    # 初始化核心组件 — 连接设置优先
    ld_path = launch_cfg.get("emulator_path") or None
    ld_index = launch_cfg.get("instance_index") or 1

    try:
        ld = LDPlayer(ld_path=ld_path, index=ld_index)
        logger.info("LDPlayer: %s (index=%d)", ld.path, ld.index)
    except FileNotFoundError:
        logger.warning("LDPlayer 未找到，部分功能不可用")
        ld = None

    loader = ScriptLoader(os.path.join(get_project_root(), "pipelines"))

    scheduler = DailyScheduler(
        os.path.join(get_project_root(), "configs", "daily.yaml"), ld, loader,
    )

    # 启动定时任务后台调度器
    worker = ScheduleWorker()
    worker.start()
    logger.info("定时调度器已启动")

    # 应用启动设置
    if ld and launch_cfg.get("auto_launch_emulator"):
        logger.info("启动设置: 自动启动模拟器实例 %d", ld.index)
        try:
            if ld.launch():
                logger.info("模拟器启动成功")
                # 等待 ADB 就绪
                time.sleep(5)
            else:
                logger.warning("模拟器启动超时")
        except Exception as e:
            logger.error("自动启动模拟器失败: %s", e)

    if launch_cfg.get("auto_run_script") and launch_cfg.get("auto_run_script_name"):
        script_name = launch_cfg["auto_run_script_name"]
        logger.info("启动设置: 自动执行脚本 '%s'", script_name)
        try:
            from auto_ld.controller.adb import Adb
            from auto_ld.controller.touch import Touch

            serial = ld.serial() if ld else ""
            adb_path = conn_cfg.get("adb_path") or (ld.adb_path() if ld else "adb")
            adb = Adb(adb_path, serial)
            touch = Touch(adb)

            if adb.ok():
                success = loader.run(script_name, adb, touch)
                logger.info("自动执行脚本 '%s': %s", script_name, "成功" if success else "失败")
            else:
                logger.warning("ADB 未就绪，跳过自动执行脚本")
        except Exception as e:
            logger.error("自动执行脚本失败: %s", e)

    app = create_app(
        ld=ld, loader=loader, scheduler=scheduler, worker=worker,
        settings=settings,
    )

    logger.info("面板已启动: http://localhost:5890")
    app.run(host="0.0.0.0", port=5890, debug=False, threaded=True)


if __name__ == "__main__":
    main()
