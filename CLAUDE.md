# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此仓库中工作时提供指导。

## 项目概述

模拟器脚本自助 是一个雷电模拟器 (LDPlayer) 的 Python 自动化框架。提供基于 ADB 的设备控制（截图、触摸、应用管理）、OpenCV 模板匹配、easyocr 文字识别、JSON 节点图流水线引擎、定时任务调度，以及带积木式 (Scratch 风格) 脚本编辑器的 Flask Web 面板。

## 常用命令

```powershell
# 安装依赖（无 requirements.txt）
pip install pyyaml flask opencv-python numpy easyocr

# 启动 Web 面板（主入口，端口 5890）
python panel.py

# CLI — 执行每日任务
python main.py

# CLI — 运行 pipelines/ 中的单个脚本
python main.py run <脚本名>

# CLI — 列出可用脚本 / 检查模拟器状态 / 截图
python main.py list
python main.py check
python main.py cap
```

没有测试套件、lint 配置或构建系统。运行环境为 Windows + Python 3.13。

## 分层架构

```
Web 层         auto_ld/web/          Flask 应用工厂，30+ REST 接口，SSE 流式推送
调度层         auto_ld/scheduler/    每日定时任务 + 后台轮询 worker
流水线层       auto_ld/pipeline/     JSON 节点图引擎（10 种动作类型）
运行时层       auto_ld/runtime/      ScriptContext（用户脚本 API）+ ScriptLoader（动态导入）
控制层         auto_ld/controller/   ADB、Touch、OpenCV 匹配、easyocr OCR、坐标/包名/模板注册管理
模拟器层       auto_ld/emulator/     LDPlayer ldconsole.exe 封装（启动/停止/状态/串口）
```

**入口文件：** `panel.py`（Web）、`main.py`（CLI）。两个入口首行都执行 `sys.path.insert(0, ...)`，确保项目根目录始终在 `sys.path` 中。所有内部导入使用绝对路径（`from auto_ld.controller.adb import Adb`）。

## 模板文件

| 文件 | 用途 |
|------|------|
| `templates/panel.html` | 控制面板主页 — 实例状态、截图、脚本执行、坐标选取 |
| `templates/editor.html` | 积木脚本编辑器 — Scratch 风格拖拽搭建自动化流程 |
| `templates/settings.html` | 设置页面 — 定时任务、连接配置、启动行为 |
| `templates/setup.html` | 首次初始化向导 — 三步检测（模拟器路径 → ADB → 设备连接） |

## 关键模式

- **首次启动检测：** `page_index("/")` 检查 `settings.json` 中 `setup_completed` 字段，未完成时展示 setup.html 向导页。向导调用 `/api/settings/autodetect` 扫描系统进程（wmic 查找 dnplayer.exe/ldconsole.exe）和常见安装路径，填完后调用 `/api/setup/complete` 标记完成。
- **设置生效链路：** `panel.py` 启动时读取 `settings.json`，将 `launch.emulator_path` 和 `launch.instance_index` 传给 `LDPlayer()`，连接设置 (`connection.adb_path`/`connection.address`) 在 `_get_adb_touch()` 中覆盖默认值。`ScheduleWorker._execute_task()` 同样读取这些设置。
- **重量级依赖惰性加载：** `matcher.py` 和 `ocr.py` 使用 `_get_cv2()` / `_get_reader()` 包装器，OpenCV 和 easyocr 仅在首次实际使用时才导入，保证 `panel.py` 快速启动。
- **管道截图（无临时文件）：** `Adb.cap()` 使用 `adb exec-out screencap -p`，通过 stdout 管道直接流式获取 PNG 字节。设备和主机均不产生临时文件。
- **ADB 重试机制：** `Adb._run()` 对所有命令自动重试最多 3 次，间隔 500ms，超时 10 秒。
- **实例列表缓存：** `LDPlayer.list_cached()` 将实例列表读写到 `configs/instances.json`，避免每次调用都弹出雷电多开管理器窗口。使用 `refresh_cache()` 强制刷新。
- **依赖注入：** `web/__init__.py` 中的 `create_app()` 接收 `ld`、`loader`、`scheduler`、`worker`、`settings` 实例并存入 `app.config` 的 `AUTOLD_*` 键下。路由通过 `current_app.config.get(...)` 获取依赖，不使用全局单例。
- **SSE 流式推送：** `/api/run/<name>` 端点创建内联的 `logging.Handler`，在后台线程执行脚本时将日志记录放入队列。主线程轮询队列并通过 `stream_with_context()` 推送事件。支持四种事件类型：`start`、`log`、`screencap`（截图节点触发时推送 base64 图像）、`done`。
- **路径兼容：** `auto_ld/_compat.py` → `get_project_root()` 在脚本模式（基于 `__file__`）和 PyInstaller 打包模式（基于 `sys.executable`）下均能正确返回项目根目录。
- **日志系统：** `auto_ld/log.py` 提供 `get_logger(name)`。由 `AUTOLD_LOG_LEVEL`（默认 `INFO`）和 `AUTOLD_LOG_DIR`（默认 `logs`）控制。包含控制台 handler 和滚动文件 handler。
- **JSON 持久化：** 坐标、包名、模板注册表、设置均以 JSON 文件存储在 `configs/` 目录。调度器是唯一使用 YAML 格式（`configs/daily.yaml`）的模块。

## 配置文件

| 文件 | 用途 |
|------|------|
| `configs/default.yaml` | 框架默认配置（雷电路径/索引、ADB 路径、流水线超时、Web 主机/端口、日志级别） |
| `configs/daily.yaml` | 每日任务调度配置 — 模拟器索引 + 有序任务列表 |
| `configs/settings.json` | Web 设置面板持久化（`setup_completed` 标记、计划任务、连接配置、启动行为） |
| `configs/instances.json` | 自动生成的模拟器实例缓存 |
| `configs/coordinates.json` | 命名坐标点和矩形区域 |
| `configs/packages.json` | 已保存的 Android 包名列表 |
| `configs/templates.json` | 模板名称 → 图片文件路径映射 |

## 积木编辑器拖拽系统

编辑器 `templates/editor.html` 使用**鼠标驱动拖拽**（非 HTML5 原生拖拽 API）实现工作区积木排序：

- `mousedown` 在 `.wsb` 元素上记录起点和偏移量，超过 4px 阈值激活拖拽
- 激活后创建 `position:fixed` 的不透明克隆体跟随光标，原位置元素变暗 (opacity 0.25)
- `updateInsertLine(e)` + `resolveDropTarget(e)` 实时计算目标位置并绘制白色插入线
  - **原位（拖回原位）：** 双白线夹住原位置
  - **非原位：** 单白线标记插入点
- `mouseup` 时执行数据层重排：从 `findParentList` 定位的原数组中 `splice` 移除，插入到目标数组
- 嵌套容器 (`.ws-children` / `.branch-col`) 有 `min-height` 确保空容器也可作为拖放目标
- 左侧面板使用 HTML5 原生 `dragstart/dragover/drop`，`onDrop` 复用 `resolveDropTarget` 确定精确插入位置
- 防止循环引用：`isDescendant()` 阻止将父块拖入其子块

## 流水线 JSON 格式

```json
{
  "name": "任务名称",
  "nodes": {
    "Start": {
      "next": ["Step1"],
      "action": { "type": "Wait", "param": { "sec": 3 } }
    },
    "Step1": {
      "action": { "type": "Click", "param": { "x": 500, "y": 300 } }
    }
  }
}
```

支持的动作类型：`Click`、`LongPress`、`Swipe`、`Wait`、`StartApp`、`StopApp`、`Shell`、`Back`、`Home`、`Screencap`。从 `"Start"` 节点开始执行，沿 `"next"` 指针遍历，通过 `visited` 集合检测循环。

## 每日调度 YAML 格式

```yaml
ldplayer:
  index: 1
tasks:
  - name: "任务名称"
    type: script # 或 "pipeline"
    file: "脚本文件名"
    enabled: true
    config:
      package: "com.example.app"
```
