"""模拟器脚本自助 REST API routes — Flask Blueprint.

所有 REST API 端点，含 SSE 流式脚本执行。
"""
import base64
import json
import logging
import os as _os
import threading
import time

from flask import (
    Blueprint, Response, current_app, jsonify, render_template,
    request, stream_with_context,
)

from auto_ld.log import get_logger

bp = Blueprint("api", __name__)
_web_log = get_logger("Web")

# 最近一次脚本截图缓存 (PNG bytes)
_last_screencap: bytes | None = None

# 脚本执行日志输出文件，前端通过 API 读取
def _get_script_log_path() -> str:
    from auto_ld._compat import get_project_root
    return _os.path.join(get_project_root(), "logs", "script_output.log")


def _write_script_log(line: str) -> None:
    """追加一行文本到脚本日志文件。"""
    try:
        with open(_get_script_log_path(), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _truncate_script_log() -> None:
    """清空脚本日志文件。"""
    path = _get_script_log_path()
    try:
        _os.makedirs(_os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("")
    except OSError:
        pass


# ====================== Helpers ======================

def _get_ld():
    """获取当前 LDPlayer 实例。"""
    return current_app.config.get("AUTOLD_LD")


def _get_loader():
    """获取 ScriptLoader 实例。"""
    return current_app.config.get("AUTOLD_LOADER")


def _get_scheduler():
    """获取 DailyScheduler 实例。"""
    return current_app.config.get("AUTOLD_SCHEDULER")


def _get_worker():
    """获取 ScheduleWorker 实例。"""
    return current_app.config.get("AUTOLD_WORKER")


def _get_adb_touch():
    """从当前 LDPlayer 状态创建 Adb + Touch 实例。

    连接设置优先级: 用户设置 > 自动检测
    """
    provider = current_app.config.get("AUTOLD_ADB_PROVIDER")
    if provider:
        return provider()

    ld = _get_ld()
    if ld is None:
        return None, None

    from auto_ld.controller.adb import Adb
    from auto_ld.controller.touch import Touch

    try:
        settings = current_app.config.get("AUTOLD_SETTINGS", {})
        conn = settings.get("connection", {})

        # 优先使用设置中保存的 ADB 路径和连接地址
        adb_path = conn.get("adb_path") or ld.adb_path()
        serial = conn.get("address") or ld.serial()

        adb = Adb(adb_path, serial)
        touch = Touch(adb)
        return adb, touch
    except Exception as e:
        _web_log.error("Failed to create ADB: %s", e)
        return None, None


def _ok(data, status: int = 200):
    return jsonify(data), status


def _err(msg: str, status: int = 500):
    return jsonify({"error": msg}), status


# ====================== Status & Instance ======================

@bp.route("/api/status")
def api_status():
    """获取模拟器状态、实例列表、连接信息。"""
    ld = _get_ld()
    if ld is None:
        return _ok({
            "connected": False, "serial": "", "running": False,
            "instances": [], "resolution": [0, 0], "index": 0,
        })

    try:
        running = ld.running()
        serial = ld.serial() if running else ""
        # Use cache to avoid launching console every time
        instances = ld.list_cached()
        res = [0, 0]

        if running and serial:
            from auto_ld.controller.adb import Adb
            adb = Adb(ld.adb_path(), serial)
            if adb.ok():
                res = list(adb.res())

        return _ok({
            "connected": running,
            "serial": serial,
            "running": running,
            "instances": instances,
            "resolution": res,
            "index": ld.index,
        })
    except Exception as e:
        return _ok({
            "connected": False, "serial": "", "running": False,
            "instances": [], "resolution": [0, 0], "index": 0,
            "error": str(e),
        })


@bp.route("/api/instance/select", methods=["POST"])
def api_instance_select():
    """切换活动模拟器实例。"""
    ld = _get_ld()
    if ld is None:
        return _err("No LDPlayer configured", 400)

    data = request.get_json(silent=True) or {}
    index = data.get("index", 1)
    try:
        ld.index = int(index)
        _web_log.info("Switched to instance %d", index)
        return _ok({"success": True, "index": ld.index})
    except Exception as e:
        return _err(str(e), 500)


@bp.route("/api/launch", methods=["POST"])
def api_launch():
    """启动模拟器。"""
    ld = _get_ld()
    if ld is None:
        return _err("No LDPlayer configured", 400)
    return _ok({"success": ld.launch()})


@bp.route("/api/quit", methods=["POST"])
def api_quit():
    """关闭模拟器。"""
    ld = _get_ld()
    if ld is None:
        return _err("No LDPlayer configured", 400)
    return _ok({"success": ld.quit()})


@bp.route("/api/connect", methods=["POST"])
def api_connect():
    """重连 ADB。"""
    adb, _ = _get_adb_touch()
    if adb is None:
        return _err("Cannot create ADB connection", 500)
    return _ok({"success": adb.ok()})


@bp.route("/api/instances/refresh", methods=["POST"])
def api_instances_refresh():
    """强制刷新实例缓存（调起雷电多开器查询）。"""
    ld = _get_ld()
    if ld is None:
        return _err("No LDPlayer configured", 400)
    try:
        instances = ld.refresh_cache()
        return _ok({"success": True, "instances": instances})
    except Exception as e:
        return _err(str(e), 500)


@bp.route("/api/instances/status")
def api_instances_status():
    """获取所有实例的运行状态。"""
    ld = _get_ld()
    if ld is None:
        return _err("No LDPlayer configured", 400)
    try:
        instances = ld.list_cached()
        statuses = []
        for inst in instances:
            s = ld.instance_status(inst["index"])
            statuses.append(s)
        return _ok({"instances": statuses})
    except Exception as e:
        return _err(str(e), 500)


# ====================== Screenshot ======================

@bp.route("/api/screenshot")
def api_screenshot():
    """截图并返回 base64 编码的 PNG。"""
    adb, _ = _get_adb_touch()
    if adb is None:
        return _err("ADB not available", 500)
    try:
        img = adb.cap()
        b64 = base64.b64encode(img).decode("utf-8")
        return _ok({"image": b64})
    except Exception as e:
        return _err(str(e), 500)


@bp.route("/api/screenshot/last")
def api_screenshot_last():
    """返回脚本执行期间最后一次截图。"""
    global _last_screencap
    if _last_screencap is None:
        return _err("No screenshot available", 404)
    b64 = base64.b64encode(_last_screencap).decode("utf-8")
    return _ok({"image": b64})


@bp.route("/api/logs/recent")
def api_logs_recent():
    """从脚本日志文件读取内容，支持 offset 增量读取。"""
    offset = request.args.get("offset", type=int, default=0)
    path = _get_script_log_path()
    try:
        if not _os.path.exists(path):
            return _ok({"lines": [], "offset": 0})
        with open(path, "r", encoding="utf-8") as f:
            if offset > 0:
                f.seek(offset)
            lines = f.read().splitlines()
            new_offset = f.tell()
        return _ok({"lines": lines, "offset": new_offset})
    except OSError as e:
        return _err(str(e), 500)


@bp.route("/api/logs/recent", methods=["DELETE"])
def api_logs_clear():
    """清空脚本日志文件。"""
    _truncate_script_log()
    return _ok({"success": True})


# ====================== Packages ======================

@bp.route("/api/packages/running")
def api_packages_running():
    """获取前台应用包名。"""
    adb, _ = _get_adb_touch()
    if adb is None:
        return _err("ADB not available", 500)
    try:
        return _ok({"package": adb.packages_running()})
    except Exception as e:
        return _err(str(e), 500)


@bp.route("/api/packages/list")
def api_packages_list():
    """搜索已安装的包。Query 参数: ?q=关键词"""
    adb, _ = _get_adb_touch()
    if adb is None:
        return _err("ADB not available", 500)
    q = request.args.get("q", "")
    try:
        return _ok({"packages": adb.packages_search(q)})
    except Exception as e:
        return _err(str(e), 500)


# ====================== Scripts CRUD ======================

@bp.route("/api/scripts")
def api_scripts():
    """列出所有脚本。"""
    loader = _get_loader()
    if loader is None:
        return _err("No loader configured", 500)
    return _ok({"scripts": loader.list()})


@bp.route("/api/scripts/files")
def api_scripts_files():
    """列出脚本文件及内容。"""
    loader = _get_loader()
    if loader is None:
        return _err("No loader configured", 500)

    files = []
    for s in loader.list():
        entry = dict(s)
        if s["type"] == "script":
            try:
                entry["content"] = loader.read_file(s["name"])
                entry["blocks"] = loader.read_blocks(s["name"])
            except Exception:
                entry["content"] = ""
                entry["blocks"] = []
        files.append(entry)
    return _ok({"files": files})


@bp.route("/api/scripts/create", methods=["POST"])
def api_scripts_create():
    """创建新脚本。Body: {"name": str, "content": str}"""
    loader = _get_loader()
    if loader is None:
        return _err("No loader configured", 500)

    data = request.get_json(silent=True) or {}
    name = data.get("name", "")
    content = data.get("content", "")

    if not name:
        return _err("name is required", 400)

    return _ok({"success": loader.write_file(name, content)})


@bp.route("/api/scripts/<name>", methods=["GET", "PUT", "DELETE"])
def api_scripts_detail(name):
    """脚本 CRUD。GET 读取, PUT 更新, DELETE 删除。"""
    loader = _get_loader()
    if loader is None:
        return _err("No loader configured", 500)

    if request.method == "GET":
        try:
            content = loader.read_file(name)
            blocks = loader.read_blocks(name)
            return _ok({"name": name, "content": content, "blocks": blocks})
        except FileNotFoundError:
            return _err(f"Script '{name}' not found", 404)

    elif request.method == "PUT":
        data = request.get_json(silent=True) or {}
        content = data.get("content", "")
        return _ok({"success": loader.write_file(name, content)})

    elif request.method == "DELETE":
        return _ok({"success": loader.delete_file(name)})

    return _err("Method not allowed", 405)


@bp.route("/api/scripts/<name>/blocks", methods=["GET", "PUT"])
def api_scripts_blocks(name):
    """积木编辑数据存取。GET 读取, PUT 保存。"""
    loader = _get_loader()
    if loader is None:
        return _err("No loader configured", 500)

    if request.method == "GET":
        blocks = loader.read_blocks(name)
        return _ok({"name": name, "blocks": blocks})
    elif request.method == "PUT":
        data = request.get_json(silent=True) or {}
        blocks = data.get("blocks", [])
        return _ok({"success": loader.write_blocks(name, blocks)})

    return _err("Method not allowed", 405)


# ====================== Tasks (Scheduler) ======================

@bp.route("/api/tasks")
def api_tasks():
    """获取每日任务配置。"""
    scheduler = _get_scheduler()
    if scheduler is None:
        return _err("No scheduler configured", 500)
    return _ok(scheduler.get_tasks())


@bp.route("/api/tasks/save", methods=["POST"])
def api_tasks_save():
    """保存每日任务配置。Body: 完整 YAML 配置的 JSON 字典"""
    scheduler = _get_scheduler()
    if scheduler is None:
        return _err("No scheduler configured", 500)
    data = request.get_json(silent=True) or {}
    return _ok({"success": scheduler.save_tasks(data)})


# ====================== Run (SSE) ======================

@bp.route("/api/run/<name>")
def api_run_script(name):
    """SSE 流式执行脚本。

    通过 Server-Sent Events 实时推送执行日志。
    事件类型:
      - start: 脚本开始
      - log:   日志消息 {message, level}
      - done:  执行完成 {success}
      - error: 执行错误 {error}
    """
    loader = _get_loader()
    if loader is None:
        return Response(
            "data: {\"event\":\"error\",\"data\":{\"error\":\"No loader configured\"}}\n\n",
            mimetype="text/event-stream",
        )

    def generate():
        adb, touch = _get_adb_touch()
        if adb is None:
            yield (
                "event: error\n"
                f"data: {json.dumps({'error': 'ADB not available'})}\n\n"
            )
            return

        _truncate_script_log()

        queue: list[dict] = []

        class _SSEHandler(logging.Handler):
            def emit(self, record):
                msg = self.format(record)
                _write_script_log(msg)
                queue.append({
                    "event": "log",
                    "data": {
                        "message": msg,
                        "level": record.levelname.lower(),
                    },
                })

        handler = _SSEHandler()
        handler.setFormatter(logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%H:%M:%S",
        ))
        root = logging.getLogger()
        root.addHandler(handler)

        try:
            _write_script_log(f">>> 开始执行: {name}")
            yield f"event: start\ndata: {json.dumps({'script': name})}\n\n"

            result: dict = {"success": False}

            def _on_screencap(img: bytes):
                global _last_screencap
                _last_screencap = img
                _write_script_log("[截图]")
                b64 = base64.b64encode(img).decode("utf-8")
                queue.append({
                    "event": "screencap",
                    "data": {"image": b64},
                })

            def _run():
                result["success"] = loader.run(
                    name, adb, touch, screencap_hook=_on_screencap,
                )

            t = threading.Thread(target=_run)
            t.start()

            last_idx = 0
            while t.is_alive():
                while last_idx < len(queue):
                    evt = queue[last_idx]
                    yield (
                        f"event: {evt['event']}\n"
                        f"data: {json.dumps(evt['data'], ensure_ascii=False)}\n\n"
                    )
                    last_idx += 1
                time.sleep(0.1)

            t.join()

            # 排空剩余日志
            while last_idx < len(queue):
                evt = queue[last_idx]
                yield (
                    f"event: {evt['event']}\n"
                    f"data: {json.dumps(evt['data'], ensure_ascii=False)}\n\n"
                )
                last_idx += 1

            _write_script_log(f"<<< 执行完成: {'成功' if result['success'] else '失败'}")
            yield f"event: done\ndata: {json.dumps({'success': result['success']})}\n\n"
        except Exception as e:
            _write_script_log(f"<<< 执行出错: {e}")
            yield (
                "event: error\n"
                f"data: {json.dumps({'error': str(e)})}\n\n"
            )
        finally:
            root.removeHandler(handler)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ====================== Run All Tasks ======================

@bp.route("/api/run_all", methods=["POST"])
def api_run_all():
    """执行全部每日任务。"""
    scheduler = _get_scheduler()
    if scheduler is None:
        return _err("No scheduler configured", 500)
    try:
        return _ok({"success": scheduler.run()})
    except Exception as e:
        return _ok({"success": False, "error": str(e)}, 500)


# ====================== Page Routes ======================

@bp.route("/")
def page_index():
    """Web 控制面板主页。首次访问时重定向到初始化设置。"""
    settings = _load_settings()
    if not settings.get("setup_completed"):
        return render_template("setup.html")
    return render_template("panel.html")


@bp.route("/editor")
def page_editor():
    """积木脚本编辑器页面。"""
    return render_template("editor.html")


@bp.route("/settings")
def page_settings():
    """设置页面。"""
    return render_template("settings.html")


@bp.route("/setup")
def page_setup():
    """首次初始化设置向导。"""
    return render_template("setup.html")


# ====================== Settings API ======================

import json as _json

from auto_ld._compat import get_project_root, get_resource_dir

_SETTINGS_PATH = _os.path.join(get_project_root(), "configs", "settings.json")


_SETTINGS_DEFAULTS = {
    "setup_completed": False,
    "schedule": [],
    "connection": {
        "provider": "ldplayer", "address": "",
        "adb_path": "", "touch_mode": "emulator",
    },
    "launch": {
        "auto_start": False, "minimize_on_start": False,
        "auto_run_script": False, "auto_run_script_name": "",
        "auto_launch_emulator": False, "emulator_path": "",
        "instance_index": 0,
    },
    "about": {
        "version": "1.0.0", "developer": "yundaxu",
        "description": "雷电模拟器自动化框架",
    },
}


def _load_settings() -> dict:
    data = dict(_SETTINGS_DEFAULTS)
    if _os.path.exists(_SETTINGS_PATH):
        try:
            with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
                saved = _json.load(f)
            for key in data:
                if key in saved:
                    if isinstance(saved[key], dict) and isinstance(data[key], dict):
                        data[key].update(saved[key])
                    else:
                        data[key] = saved[key]
        except (_json.JSONDecodeError, OSError):
            pass
    return data


def _save_settings(data: dict) -> None:
    existing = _load_settings()  # always starts from defaults
    for key in existing:
        if key in data:
            if isinstance(existing[key], dict):
                existing[key].update(data[key])
            else:
                existing[key] = data[key]
    _os.makedirs(_os.path.dirname(_SETTINGS_PATH), exist_ok=True)
    with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
        _json.dump(existing, f, ensure_ascii=False, indent=2)


@bp.route("/api/settings")
def api_settings_get():
    """获取全部设置。"""
    return _ok(_load_settings())


@bp.route("/api/settings", methods=["POST"])
def api_settings_save():
    """保存全部设置。"""
    data = request.get_json(silent=True) or {}
    try:
        _save_settings(data)
        # 通知调度器刷新缓存
        worker = _get_worker()
        if worker is not None:
            worker.refresh()
        return _ok({"success": True})
    except Exception as e:
        return _err(str(e), 500)


@bp.route("/api/settings/autodetect", methods=["POST"])
def api_settings_autodetect():
    """自动检测连接配置 — 扫描系统进程和常见路径。"""
    import subprocess

    result = {"success": False, "provider": "ldplayer"}

    # 1. 在系统进程中查找雷电模拟器进程的安装路径
    emu_path = ""
    # 尝试多个进程名: dnplayer.exe (模拟器主程序), ldconsole.exe (命令行工具)
    for proc_name in ["dnplayer.exe", "ldconsole.exe"]:
        try:
            r = subprocess.run(
                ["wmic", "process", "where", f"name='{proc_name}'",
                 "get", "ExecutablePath"],
                capture_output=True, text=True, timeout=8,
            )
            for line in r.stdout.splitlines():
                line = line.strip()
                if line.lower().endswith(proc_name.lower()):
                    emu_path = _os.path.dirname(line)
                    break
        except Exception:
            pass
        if emu_path:
            break

    # 2. 进程未找到时扫描常见安装路径
    if not emu_path:
        common = [
            r"D:\leidian\LDPlayer9",
            r"C:\leidian\LDPlayer9",
            r"D:\LDPlayer\LDPlayer9",
            r"C:\LDPlayer\LDPlayer9",
            r"D:\leidian\LDPlayer",
            r"C:\leidian\LDPlayer",
        ]
        for base in [r"C:\Program Files", r"D:\Program Files"]:
            if _os.path.exists(base):
                for p in _os.listdir(base):
                    full = _os.path.join(base, p)
                    if _os.path.isdir(full) and ("leidian" in p.lower() or "ldplayer" in p.lower()):
                        common.append(full)
        for p in common:
            if _os.path.exists(_os.path.join(p, "ldconsole.exe")):
                emu_path = p
                break

    # 3. 从安装路径推导 adb 路径
    if emu_path:
        result["emulator_path"] = emu_path
        adb_exe = _os.path.join(emu_path, "adb.exe")
        if _os.path.exists(adb_exe):
            result["adb_path"] = adb_exe
        result["success"] = True
    else:
        # 最后回退: 使用已配置的 LDPlayer 实例
        ld = _get_ld()
        if ld is not None:
            result["adb_path"] = ld.adb_path()
            result["emulator_path"] = ld.path
            result["success"] = True

    # 4. 通过 adb devices 检测已连接的设备串口
    address = ""
    adb_path = result.get("adb_path", "adb")
    try:
        r = subprocess.run(
            [adb_path, "devices"], capture_output=True, text=True, timeout=5,
        )
        for line in r.stdout.splitlines():
            if "\tdevice" in line and "List" not in line:
                address = line.split("\t")[0].strip()
                break
    except Exception:
        pass

    if not address:
        # 回退: 用 LDPlayer 检测
        ld = _get_ld()
        if ld is not None and ld.running():
            address = ld.serial()

    result["address"] = address
    return _ok(result)


# ====================== Setup ======================

@bp.route("/api/setup/complete", methods=["POST"])
def api_setup_complete():
    """标记初始化设置完成。"""
    try:
        _save_settings({"setup_completed": True})
        return _ok({"success": True})
    except Exception as e:
        return _err(str(e), 500)


# ====================== Schedule Worker ======================

@bp.route("/api/schedule/status")
def api_schedule_status():
    """获取定时调度器运行状态。"""
    worker = _get_worker()
    if worker is None:
        return _ok({"running": False, "total_tasks": 0, "enabled_tasks": 0, "tasks": []})
    return _ok(worker.status())


@bp.route("/api/schedule/trigger", methods=["POST"])
def api_schedule_trigger():
    """手动立即触发所有已启用的定时任务（测试用）。"""
    worker = _get_worker()
    if worker is None:
        return _err("调度器未启动", 500)
    try:
        result = worker.trigger_now()
        return _ok(result)
    except Exception as e:
        return _err(str(e), 500)


# ====================== Debug ======================

@bp.route("/api/debug/ldconsole")
def api_debug_ldconsole():
    """调试端点：直接返回 ldconsole list 原始输出。"""
    ld = _get_ld()
    if ld is None:
        return _err("No LDPlayer configured", 500)
    try:
        raw = ld.ldconsole("list")
        instances = ld.list()
        return _ok({
            "raw_output": raw,
            "parsed_instances": instances,
            "ld_path": ld.path,
            "ldconsole_path": ld._ldconsole,
        })
    except Exception as e:
        return _err(str(e), 500)


# ====================== Template Matching ======================

# Lazy matcher instance
_matcher = None


def _get_matcher():
    global _matcher
    if _matcher is None:
        from auto_ld.controller.matcher import TemplateMatcher
        _matcher = TemplateMatcher()
    return _matcher


@bp.route("/api/templates")
def api_templates_list():
    """列出所有模板图片（从注册表读取）。"""
    from auto_ld.controller.registry import list_all
    reg = list_all()
    templates = [{"name": n, "path": p} for n, p in reg.items()]
    return _ok({"templates": templates})


@bp.route("/api/templates/<name>", methods=["DELETE"])
def api_templates_delete(name):
    """删除模板。"""
    success = _get_matcher().remove_template(name)
    from auto_ld.controller.registry import unregister
    unregister(name)
    return _ok({"success": success})


@bp.route("/api/templates/img/<name>")
def api_templates_img(name):
    """获取模板图片。"""
    from flask import send_file
    import os as _os
    # Use images/ directory (NOT templates/ which is Flask's HTML template folder)
    base = _os.path.join(get_resource_dir(), "images")
    path = _os.path.join(base, f"{name}.png")
    if not _os.path.exists(path):
        return _err("Template not found", 404)
    return send_file(path, mimetype="image/png")


@bp.route("/api/templates/match/<name>")
def api_templates_match(name):
    """在屏幕中查找模板位置。"""
    adb, _ = _get_adb_touch()
    if adb is None:
        return _err("ADB not available", 500)
    try:
        img = adb.cap()
        result = _get_matcher().find(name, img)
        if result:
            return _ok({"found": True, **result})
        return _ok({"found": False})
    except Exception as e:
        return _err(str(e), 500)


@bp.route("/api/screenshot/crop", methods=["POST"])
def api_screenshot_crop():
    """截取屏幕指定区域并保存为模板。

    Body: {"name": "btn_icon", "x1": 100, "y1": 200, "x2": 160, "y2": 260}
    """
    adb, _ = _get_adb_touch()
    if adb is None:
        return _err("ADB not available", 500)

    data = request.get_json(silent=True) or {}
    name = data.get("name", "")
    x1, y1 = int(data.get("x1", 0)), int(data.get("y1", 0))
    x2, y2 = int(data.get("x2", 0)), int(data.get("y2", 0))

    if not name:
        return _err("name is required", 400)
    if x2 <= x1 or y2 <= y1:
        return _err("invalid crop region", 400)

    try:
        # Take full screenshot
        from auto_ld.controller.matcher import _get_cv2
        import numpy as np
        cv = _get_cv2()

        full = adb.cap()
        nparr = np.frombuffer(full, np.uint8)
        screen = cv.imdecode(nparr, cv.IMREAD_COLOR)
        if screen is None:
            return _err("Failed to decode screenshot", 500)

        # Crop region
        crop = screen[y1:y2, x1:x2]
        if crop.size == 0:
            return _err("Crop region is empty", 400)

        # Encode as PNG
        _, buf = cv.imencode(".png", crop)
        crop_bytes = buf.tobytes()

        path = _get_matcher().add_template(name, crop_bytes)
        # Register in JSON
        from auto_ld.controller.registry import register
        import os as _os
        register(name, path.replace("\\", "/"))
        return _ok({
            "success": True,
            "path": path,
            "width": x2 - x1,
            "height": y2 - y1,
        })
    except ImportError:
        return _err(
            "opencv-python not installed. Run: pip install opencv-python numpy",
            500,
        )
    except Exception as e:
        return _err(str(e), 500)


# ====================== OCR ======================

@bp.route("/api/ocr")
def api_ocr():
    """对当前屏幕执行 OCR 识别，返回所有文字。"""
    adb, _ = _get_adb_touch()
    if adb is None:
        return _err("ADB not available", 500)
    try:
        from auto_ld.controller.ocr import OCREngine
        img = adb.cap()
        ocr = OCREngine()
        results = ocr.read(img)
        return _ok({"results": results})
    except ImportError:
        return _err("easyocr not installed. Run: pip install easyocr", 500)
    except Exception as e:
        return _err(str(e), 500)


@bp.route("/api/ocr/find/<text>")
def api_ocr_find(text):
    """在屏幕中查找指定文字并返回坐标。"""
    adb, _ = _get_adb_touch()
    if adb is None:
        return _err("ADB not available", 500)
    try:
        from auto_ld.controller.ocr import OCREngine
        img = adb.cap()
        ocr = OCREngine()
        result = ocr.find(text, img)
        if result:
            return _ok({"found": True, **result})
        return _ok({"found": False})
    except ImportError:
        return _err("easyocr not installed", 500)
    except Exception as e:
        return _err(str(e), 500)


# ====================== Coordinates ======================

@bp.route("/api/coordinates")
def api_coordinates_list():
    """获取所有保存的坐标和区域。"""
    from auto_ld.controller.coords import list_coords
    return _ok(list_coords())


@bp.route("/api/coordinates/point", methods=["POST"])
def api_coordinates_save_point():
    """保存单点坐标。Body: {name, x, y}"""
    data = request.get_json(silent=True) or {}
    name = data.get("name", "")
    x, y = int(data.get("x", 0)), int(data.get("y", 0))
    if not name:
        return _err("name is required", 400)
    from auto_ld.controller.coords import save_point
    return _ok({"success": save_point(name, x, y)})


@bp.route("/api/coordinates/region", methods=["POST"])
def api_coordinates_save_region():
    """保存区域坐标。Body: {name, x1, y1, x2, y2}"""
    data = request.get_json(silent=True) or {}
    name = data.get("name", "")
    x1, y1 = int(data.get("x1", 0)), int(data.get("y1", 0))
    x2, y2 = int(data.get("x2", 0)), int(data.get("y2", 0))
    if not name:
        return _err("name is required", 400)
    from auto_ld.controller.coords import save_region
    return _ok({"success": save_region(name, x1, y1, x2, y2)})


@bp.route("/api/coordinates/<name>", methods=["DELETE"])
def api_coordinates_delete(name):
    """删除坐标。"""
    from auto_ld.controller.coords import delete_coord
    return _ok({"success": delete_coord(name)})


# ====================== Packages ======================

@bp.route("/api/packages/saved")
def api_packages_saved():
    """获取已保存的包名列表。"""
    from auto_ld.controller.packages import list_packages
    return _ok({"packages": list_packages()})


@bp.route("/api/packages/saved", methods=["POST"])
def api_packages_save():
    """保存包名。Body: {package: "com.example.app"}"""
    data = request.get_json(silent=True) or {}
    pkg = data.get("package", "")
    if not pkg:
        return _err("package is required", 400)
    from auto_ld.controller.packages import add_package
    return _ok({"success": add_package(pkg)})


@bp.route("/api/packages/saved/<package>", methods=["DELETE"])
def api_packages_delete(package):
    """删除保存的包名。"""
    from auto_ld.controller.packages import remove_package
    return _ok({"success": remove_package(package)})
