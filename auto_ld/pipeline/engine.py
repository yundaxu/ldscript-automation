"""Pipeline 动作流水线引擎 — 基于 JSON 节点图的自动化工作流执行。

MAA 框架模式参考:
  - 节点图驱动: 每个节点包含 action 和 next 转换
  - 支持多种动作类型: Click, Swipe, Wait, StartApp, Shell 等
  - 自动保存截图到指定目录
"""
import json
import os
import threading
import time
from datetime import datetime

from auto_ld.log import get_logger
from auto_ld.runtime.context import ScriptStopped

SUPPORTED_ACTIONS = frozenset({
    "Click", "LongPress", "Swipe", "Wait",
    "StartApp", "StopApp", "Shell",
    "Back", "Home", "Screencap",
})


class PipelineEngine:
    """Pipeline 动作流水线引擎。

    基于 JSON 节点图执行自动化工作流。
    每个节点定义一种动作 (action) 和后续节点列表 (next)。
    解析从 "Start" 节点开始，按 next 指针遍历执行。

    JSON 格式示例:
        {
          "name": "任务名",
          "nodes": {
            "Start": {
              "next": ["ClickBtn"],
              "action": {"type": "Wait", "param": {"sec": 3}}
            },
            "ClickBtn": {
              "action": {"type": "Click", "param": {"x": 500, "y": 300}}
            }
          }
        }
    """

    def __init__(
        self, adb, touch, screenshot_dir: str = "screenshots",
        screencap_hook=None, stop_event: threading.Event | None = None,
    ) -> None:
        """初始化流水线引擎。

        Args:
            adb: auto_ld.controller.adb.Adb 实例
            touch: auto_ld.controller.touch.Touch 实例
            screenshot_dir: 截图保存目录
            screencap_hook: 截图回调 (接收 PNG bytes)
            stop_event: 停止信号，设置后中断流水线执行
        """
        self._adb = adb
        self._touch = touch
        self._screenshot_dir = screenshot_dir
        self._screencap_hook = screencap_hook
        self._stop_event = stop_event
        self._log = get_logger("Pipeline")
        os.makedirs(screenshot_dir, exist_ok=True)

    def _check_stop(self) -> None:
        """检查停止信号，若已设置则抛出 ScriptStopped。"""
        if self._stop_event and self._stop_event.is_set():
            raise ScriptStopped("流水线已被用户停止")

    def run_file(self, json_path: str) -> bool:
        """从 JSON 文件加载并执行流水线。

        Args:
            json_path: JSON 流水线配置文件路径

        Returns:
            True 表示流水线执行成功
        """
        if not os.path.exists(json_path):
            self._log.error("Pipeline file not found: %s", json_path)
            return False

        with open(json_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        return self.run_dict(config)

    def run_dict(self, config: dict) -> bool:
        """从字典配置执行流水线。

        Args:
            config: 包含 "name" 和 "nodes" 的字典

        Returns:
            True 表示流水线执行成功
        """
        name = config.get("name", "Unnamed")
        nodes = config.get("nodes", {})

        if "Start" not in nodes:
            self._log.error("Pipeline '%s': no Start node", name)
            return False

        self._log.info("Pipeline started: %s", name)

        try:
            self._run_node("Start", nodes, set())
            self._log.info("Pipeline completed: %s", name)
            return True
        except ScriptStopped as e:
            self._log.info("Pipeline stopped: %s — %s", name, e)
            return False
        except Exception as e:
            self._log.error("Pipeline failed: %s — %s", name, e)
            return False

    def _run_node(
        self, node_name: str, nodes: dict, visited: set
    ) -> None:
        """递归执行指定节点及其后续节点。

        Args:
            node_name: 当前节点名称
            nodes: 节点字典
            visited: 已访问节点集合 (防止死循环)
        """
        if node_name in visited:
            self._log.warning("Loop detected at node: %s", node_name)
            return
        if node_name not in nodes:
            return

        visited.add(node_name)
        node = nodes[node_name]
        action = node.get("action", {})
        action_type = action.get("type", "")
        params = action.get("param", {})

        self._check_stop()
        self._log.info("  [%s] %s: %s", node_name, action_type, params)
        self._execute_action(action_type, params, node_name)

        next_nodes = node.get("next", [])
        for n in next_nodes:
            self._run_node(n, nodes, visited)

    def _execute_action(
        self, action_type: str, params: dict, node_name: str
    ) -> None:
        """执行单个动作。

        Args:
            action_type: 动作类型
            params: 动作参数
            node_name: 所属节点名 (用于截图文件命名)
        """
        if action_type == "Click":
            self._touch.click(
                params.get("x", 0), params.get("y", 0), delay=0.3
            )
        elif action_type == "LongPress":
            self._touch.long_press(
                params.get("x", 0), params.get("y", 0),
                params.get("duration", 1000),
            )
        elif action_type == "Swipe":
            self._adb.swipe(
                params.get("x1", 0), params.get("y1", 0),
                params.get("x2", 0), params.get("y2", 0),
                params.get("duration", 300),
            )
        elif action_type == "Wait":
            sec = params.get("sec", 1)
            self._log.info("  Waiting %.1fs ...", sec)
            elapsed = 0.0
            while elapsed < sec:
                self._check_stop()
                chunk = min(0.3, sec - elapsed)
                time.sleep(chunk)
                elapsed += chunk
        elif action_type == "StartApp":
            self._adb.start(params.get("package", ""))
            time.sleep(2)
        elif action_type == "StopApp":
            self._adb.stop(params.get("package", ""))
        elif action_type == "Shell":
            output = self._adb.shell(params.get("command", ""))
            self._log.info("  Shell output: %s", output[:200])
        elif action_type == "Back":
            self._touch.back()
        elif action_type == "Home":
            self._touch.home()
        elif action_type == "Screencap":
            img = self._adb.cap()
            if self._screencap_hook:
                self._screencap_hook(img)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(
                self._screenshot_dir, f"{node_name}_{ts}.png"
            )
            with open(filename, "wb") as f:
                f.write(img)
            self._log.info("  Screenshot saved: %s", filename)
        else:
            self._log.warning(
                "  Unknown action: %s (supported: %s)",
                action_type, sorted(SUPPORTED_ACTIONS),
            )
