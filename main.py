"""模拟器脚本自助 CLI 入口。

用法:
    python main.py              执行每日任务
    python main.py run <脚本名>  执行指定脚本
    python main.py list         列出可用脚本
    python main.py check        检查雷电模拟器状态
    python main.py cap          截图并保存
"""
import sys
import os
from datetime import datetime

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def cmd_run(args: list[str]) -> int:
    """执行指定脚本。"""
    if len(args) < 2:
        print("用法: python main.py run <脚本名>")
        return 1

    name = args[1]
    from auto_ld.emulator.ldplayer import LDPlayer
    from auto_ld.controller.adb import Adb
    from auto_ld.controller.touch import Touch
    from auto_ld.runtime.loader import ScriptLoader

    ld = LDPlayer()
    if not ld.running():
        print("模拟器未运行，正在启动...")
        ld.launch()

    serial = ld.serial()
    adb = Adb(ld.adb_path(), serial)
    touch = Touch(adb)

    if not adb.ok():
        print("ADB 连接失败")
        return 1

    print(f"设备就绪: {serial}, {adb.res()[0]}x{adb.res()[1]}")
    print(f"执行脚本: {name}")

    loader = ScriptLoader()
    success = loader.run(name, adb, touch)
    print("执行成功" if success else "执行失败")
    return 0 if success else 1


def cmd_list(args: list[str]) -> int:
    """列出所有可用脚本。"""
    from auto_ld.runtime.loader import ScriptLoader

    loader = ScriptLoader()
    scripts = loader.list()

    if not scripts:
        print("没有找到脚本 (pipelines/ 目录为空)")
        return 0

    for s in scripts:
        tag = f"[{s['type']}]"
        print(f"  {tag:12s} {s['name']}")
    return 0


def cmd_check(args: list[str]) -> int:
    """检查雷电模拟器状态。"""
    from auto_ld.emulator.ldplayer import LDPlayer

    try:
        ld = LDPlayer()
    except FileNotFoundError as e:
        print(f"错误: {e}")
        return 1

    print(f"雷电路径: {ld.path}")
    print(f"当前实例: {ld.index}")

    instances = ld.list()
    print(f"已安装实例: {len(instances)} 个")
    for inst in instances:
        print(f"  [{inst['index']}] {inst['name']}")

    running = ld.running()
    print(f"运行状态: {'运行中' if running else '未运行'}")

    if running:
        serial = ld.serial()
        print(f"ADB 串口: {serial}")

        from auto_ld.controller.adb import Adb
        adb = Adb(ld.adb_path(), serial)
        if adb.ok():
            w, h = adb.res()
            print(f"分辨率: {w}x{h}")
            pkg = adb.packages_running()
            print(f"前台应用: {pkg or '无法获取'}")
        else:
            print("ADB 连接失败")
    return 0


def cmd_cap(args: list[str]) -> int:
    """截图并保存。"""
    from auto_ld.emulator.ldplayer import LDPlayer
    from auto_ld.controller.adb import Adb

    ld = LDPlayer()
    if not ld.running():
        print("模拟器未运行")
        return 1

    serial = ld.serial()
    adb = Adb(ld.adb_path(), serial)

    if not adb.ok():
        print("ADB 连接失败")
        return 1

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"screenshot_{ts}.png"

    os.makedirs("screenshots", exist_ok=True)
    filepath = os.path.join("screenshots", filename)

    img = adb.cap()
    with open(filepath, "wb") as f:
        f.write(img)
    print(f"截图已保存: {filepath}")
    return 0


def cmd_default(args: list[str]) -> int:
    """执行每日任务。"""
    from auto_ld.emulator.ldplayer import LDPlayer
    from auto_ld.runtime.loader import ScriptLoader
    from auto_ld.scheduler.daily import DailyScheduler

    ld = LDPlayer()
    loader = ScriptLoader()
    scheduler = DailyScheduler("configs/daily.yaml", ld, loader)

    success = scheduler.run()
    print("每日任务完成" if success else "每日任务失败")
    return 0 if success else 1


COMMANDS = {
    "run": cmd_run,
    "list": cmd_list,
    "check": cmd_check,
    "cap": cmd_cap,
}


def main() -> int:
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd in COMMANDS:
            return COMMANDS[cmd](sys.argv[1:])
        else:
            print(f"未知命令: {cmd}")
            print("可用命令: run, list, check, cap")
            return 1
    return cmd_default(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
