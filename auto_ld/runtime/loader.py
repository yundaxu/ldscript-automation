"""动态脚本加载器 — 加载和管理 pipelines/ 目录中的用户脚本。"""
import importlib.util
import json
import os
import sys

from auto_ld.log import get_logger


class ScriptLoader:
    """用户脚本加载器。

    管理 pipelines/ 目录中的 Python 脚本和 JSON 流水线配置。
    支持动态导入、列出、创建、修改和删除脚本文件。
    """

    def __init__(self, pipelines_dir: str = "pipelines") -> None:
        self._dir = pipelines_dir
        self._log = get_logger("Loader")
        os.makedirs(pipelines_dir, exist_ok=True)

        # 确保 pipelines 目录在 sys.path 中以便动态导入
        abs_dir = os.path.abspath(pipelines_dir)
        if abs_dir not in sys.path:
            sys.path.insert(0, abs_dir)

    def list(self) -> list[dict]:
        """列出所有可用脚本。

        Returns:
            脚本信息列表，每项包含 name / type / file / path
        """
        scripts: list[dict] = []
        if not os.path.exists(self._dir):
            return scripts

        entries = sorted(
            [e for e in os.listdir(self._dir)
             if os.path.isfile(os.path.join(self._dir, e))]
        )
        for fname in entries:
            fpath = os.path.join(self._dir, fname)
            name = os.path.splitext(fname)[0]

            if fname.endswith(".py") and not fname.startswith("_"):
                scripts.append({
                    "name": name,
                    "type": "script",
                    "file": fname,
                    "path": fpath,
                })
            elif fname.endswith(".json") and not fname.endswith(".blocks.json"):
                scripts.append({
                    "name": name,
                    "type": "pipeline",
                    "file": fname,
                    "path": fpath,
                })

        return scripts

    def load(self, name: str):
        """动态加载一个 Python 脚本模块。

        Args:
            name: 脚本名称 (不含 .py 扩展名)

        Returns:
            已加载的模块对象 (必须包含 run 函数)

        Raises:
            FileNotFoundError: 脚本文件不存在
            AttributeError: 脚本中无 run 函数
        """
        fpath = os.path.join(self._dir, f"{name}.py")
        if not os.path.exists(fpath):
            raise FileNotFoundError(f"Script not found: {fpath}")

        mod_name = f"pipeline_{name}"
        spec = importlib.util.spec_from_file_location(mod_name, fpath)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load script: {fpath}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if not hasattr(module, "run"):
            raise AttributeError(
                f"Script '{name}' has no run(ctx) function"
            )
        return module

    def run(
        self, name: str, adb, touch, log=None, config: dict | None = None,
        screencap_hook=None,
    ) -> bool:
        """加载并执行脚本。

        支持:
        - Python 脚本: 动态导入并调用 run(ctx)
        - JSON 流水线: 使用 PipelineEngine 执行

        Args:
            name: 脚本名称
            adb: Adb 控制器实例
            touch: Touch 控制器实例
            log: 可选的 Logger 实例
            config: 可选的配置参数字典 (传给 ctx.config)
            screencap_hook: 截图回调 (接收 PNG bytes)

        Returns:
            True 表示脚本执行成功
        """
        try:
            json_path = os.path.join(self._dir, f"{name}.json")
            if os.path.exists(json_path):
                from auto_ld.pipeline.engine import PipelineEngine
                engine = PipelineEngine(adb, touch, screencap_hook=screencap_hook)
                return engine.run_file(json_path)

            module = self.load(name)
            from auto_ld.runtime.context import ScriptContext

            ctx = ScriptContext(adb, touch, log, config, screencap_hook)
            ctx.start_timing()

            result = module.run(ctx)

            elapsed = ctx.elapsed()
            self._log.info(
                "Script '%s' completed in %.1fs, %d steps",
                name, elapsed, ctx.step_count(),
            )
            return result if isinstance(result, bool) else True
        except Exception as e:
            self._log.error("Script '%s' failed: %s", name, e)
            return False

    def read_file(self, name: str) -> str:
        """读取脚本文件内容。

        Args:
            name: 脚本名称

        Returns:
            文件内容字符串
        """
        fpath = os.path.join(self._dir, f"{name}.py")
        if not os.path.exists(fpath):
            raise FileNotFoundError(f"Script not found: {fpath}")
        with open(fpath, "r", encoding="utf-8") as f:
            return f.read()

    def write_file(self, name: str, content: str) -> bool:
        """创建或覆盖脚本文件。

        Args:
            name: 脚本名称
            content: 脚本内容

        Returns:
            True 表示写入成功
        """
        os.makedirs(self._dir, exist_ok=True)
        fpath = os.path.join(self._dir, f"{name}.py")
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        self._log.info("Script saved: %s", name)
        return True

    def delete_file(self, name: str) -> bool:
        """删除脚本文件 (包括 .blocks.json)。

        Args:
            name: 脚本名称

        Returns:
            True 表示删除成功
        """
        for ext in [".py", ".blocks.json"]:
            fpath = os.path.join(self._dir, f"{name}{ext}")
            if os.path.exists(fpath):
                os.remove(fpath)
                self._log.info("Deleted: %s", fpath)
        return True

    def read_blocks(self, name: str) -> list:
        """读取脚本的积木编辑数据 (.blocks.json)。

        Args:
            name: 脚本名称

        Returns:
            积木块列表，文件不存在时返回空列表
        """
        blocks_path = os.path.join(self._dir, f"{name}.blocks.json")
        if not os.path.exists(blocks_path):
            return []
        with open(blocks_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def write_blocks(self, name: str, blocks: list) -> bool:
        """保存脚本的积木编辑数据。

        Args:
            name: 脚本名称
            blocks: 积木块数据列表

        Returns:
            True 表示保存成功
        """
        blocks_path = os.path.join(self._dir, f"{name}.blocks.json")
        with open(blocks_path, "w", encoding="utf-8") as f:
            json.dump(blocks, f, ensure_ascii=False, indent=2)
        self._log.info("Blocks saved: %s", name)
        return True
