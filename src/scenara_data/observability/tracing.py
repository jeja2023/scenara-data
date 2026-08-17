"""W3C 追踪上下文传播（规范 40）。

Data 从 Core 透传的 `traceparent` 中提取可检索的 `trace_id`，不只记录原始头。
"""

from __future__ import annotations

import re

TRACEPARENT = re.compile(r"^(?P<version>[0-9a-f]{2})-(?P<trace>[0-9a-f]{32})-(?P<span>[0-9a-f]{16})-(?P<flags>[0-9a-f]{2})$")
INVALID_TRACE_ID = "0" * 32
INVALID_SPAN_ID = "0" * 16


def extract_trace_id(traceparent: str | None) -> str | None:
    """从合法 traceparent 提取 trace_id；非法或全零值返回 None。"""
    if not traceparent:
        return None
    match = TRACEPARENT.fullmatch(traceparent.strip())
    if match is None:
        return None
    if match.group("version") == "ff":
        return None
    trace_id = match.group("trace")
    if trace_id == INVALID_TRACE_ID or match.group("span") == INVALID_SPAN_ID:
        return None
    return trace_id


def format_traceparent(trace_id: str, span_id: str, *, sampled: bool = True) -> str:
    """构造下游调用使用的 traceparent 头。"""
    if len(trace_id) != 32 or trace_id == INVALID_TRACE_ID:
        raise ValueError("trace_id 必须是 32 位小写十六进制字符")
    if len(span_id) != 16 or span_id == INVALID_SPAN_ID:
        raise ValueError("span_id 必须是 16 位小写十六进制字符")
    return f"00-{trace_id}-{span_id}-{'01' if sampled else '00'}"
