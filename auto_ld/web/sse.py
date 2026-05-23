"""SSE 辅助工具 — Server-Sent Events 流式推送。

为 Web 面板提供实时日志推送能力。
"""
import json
import logging


class SSELogHandler(logging.Handler):
    """自定义日志处理器，将日志记录转发为 SSE 事件。

    配合 Flask SSE 端点使用，将 Python logging 消息
    转换为 SSE event: log 格式的事件。

    Usage:
        handler = SSELogHandler(callback)
        logging.getLogger().addHandler(handler)
        # ... 执行任务 ...
        logging.getLogger().removeHandler(handler)
    """

    def __init__(self, callback) -> None:
        """初始化 SSE 日志处理器。

        Args:
            callback: 回调函数，接收 {"event": "log", "data": {...}} 字典
        """
        super().__init__()
        self._callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        """处理日志记录。

        Args:
            record: Python logging.LogRecord 实例
        """
        msg = self.format(record)
        self._callback({
            "event": "log",
            "data": {
                "message": msg,
                "level": record.levelname.lower(),
            },
        })


def sse_format(event: str, data: dict) -> str:
    """将事件转换为 SSE 格式字符串。

    Args:
        event: 事件名称 (如 "log", "start", "done")
        data: 事件数据字典

    Returns:
        SSE 格式字符串，含 "event:" 和 "data:" 行
    """
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
