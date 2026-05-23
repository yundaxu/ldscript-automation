# 模拟器脚本自助

雷电模拟器自动化框架 — 基于 Python 的 Android 模拟器脚本工具，提供积木式脚本编辑器、YAML 定时任务调度和 Flask Web 控制面板。

## 功能特性

- **Web 控制面板** — Flask 驱动的管理界面（端口 5890），支持脚本编辑、执行监控、设置管理
- **积木式脚本编辑器** — 拖拽搭建自动化流程，无需编写代码，10 种动作类型（点击、滑动、等待、启动应用等）
- **定时任务调度** — YAML 驱动每日任务，支持脚本和流水线两种执行类型
- **精准控制** — ADB 截图/触摸/应用管理，OpenCV 模板匹配，easyocr 中英文文字识别
- **首次引导** — 首次启动自动进入设置向导，检测模拟器路径和 ADB 连接
- **SSE 实时推送** — 脚本执行日志和截图实时同步到面板

## 系统要求

| 依赖 | 说明 |
|------|------|
| Windows 10+ | 仅支持 Windows（雷电模拟器限制） |
| Python 3.10+ | 脚本模式运行需要 |
| 雷电模拟器 9.x | [ldmnq.com](https://www.ldmnq.com) 下载 |

## 快速开始

### 方式一：下载 .exe（推荐）

从 [Releases](https://github.com/moerbediqingkong/ldscript-automation/releases) 下载最新版 `模拟器脚本自助.exe`，双击运行，浏览器访问 `http://localhost:5890`。

> .exe 已内置 easyocr 模型，无需下载额外文件。

### 方式二：源码运行

```bash
# 克隆仓库
git clone https://github.com/moerbediqingkong/ldscript-automation.git
cd ldscript-automation

# 安装依赖
pip install pyyaml flask opencv-python numpy easyocr

# 启动 Web 面板
python panel.py
```

浏览器访问 `http://localhost:5890`，首次进入会引导完成初始化设置。

### CLI 模式

```bash
python main.py          # 执行每日任务
python main.py run 脚本名  # 运行单个脚本
python main.py list       # 列出可用脚本
python main.py check      # 检查模拟器状态
python main.py cap        # 截图测试
```

## 项目结构

```
├── panel.py                  # Web 面板入口
├── main.py                   # CLI 入口
├── auto_ld/                  # 核心框架
│   ├── web/                  # Flask 应用（路由、SSE）
│   ├── scheduler/            # YAML 定时任务调度
│   ├── pipeline/             # JSON 节点图流水线引擎
│   ├── runtime/              # 脚本运行时（上下文 + 加载器）
│   ├── controller/           # ADB、触摸、模板匹配、OCR
│   ├── emulator/             # 雷电模拟器进程管理
│   ├── _compat.py            # PyInstaller 路径兼容
│   └── log.py                # 日志系统
├── configs/                  # 配置文件
│   ├── default.yaml          # 默认框架配置
│   ├── daily.yaml            # 每日任务定义
│   └── settings.json         # Web 面板持久化设置
├── templates/                # Jinja2 前端页面
├── pipelines/                # 用户流水线脚本
├── images/                   # 模板匹配图片
├── screenshots/              # 截图输出目录
└── release/                  # 打包相关
    └── app.spec              # PyInstaller 配置
```

## 架构设计

```
Web 层          auto_ld/web/          Flask 应用工厂，SSE 流式推送
调度层          auto_ld/scheduler/    YAML 驱动的每日任务执行器
流水线层        auto_ld/pipeline/     JSON 节点图引擎（10 种动作类型）
运行时层        auto_ld/runtime/      ScriptContext + ScriptLoader
控制层          auto_ld/controller/   ADB、Touch、OpenCV、easyocr OCR
模拟器层        auto_ld/emulator/     LDPlayer ldconsole.exe 封装
```

核心设计原则：
- 依赖注入（Flask 路由通过 `app.config` 获取依赖，无全局单例）
- 惰性加载（OpenCV/easyocr 仅在首次使用时导入）
- 零临时文件（ADB 截图通过管道传输）
- 路径兼容（脚本模式与 PyInstaller 打包模式自动适配）

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

支持的动作类型：`Click`、`LongPress`、`Swipe`、`Wait`、`StartApp`、`StopApp`、`Shell`、`Back`、`Home`、`Screencap`。

## 每日调度 YAML 格式

```yaml
ldplayer:
  index: 1
tasks:
  - name: "签到任务"
    type: script
    file: "checkin"
    enabled: true
    config:
      package: "com.example.app"
```

## 自行打包

```bash
pip install pyinstaller
python -m PyInstaller --distpath release/dist --workpath release/build release/app.spec
```

输出文件：`release/dist/模拟器脚本自助.exe`

## 技术栈

Python · Flask · easyocr · OpenCV · NumPy · PyYAML · PyInstaller · ADB

## 开源许可

MIT License

Copyright (c) 2026 墨尔本的晴空
