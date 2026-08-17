"""结构化日志（规范 40）。

必填字段：timestamp、level、service、module、request_id、trace_id、message。
禁止字段：密码、访问令牌、API Key、私钥、完整人脸特征和未脱敏个人数据。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

LOG_FIELDS = (
    "timestamp",
    "level",
    "service",
    "module",
    "request_id",
    "trace_id",
    "message",
)

#: 这些请求头/字段名一律不写入日志。
SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "x-scenara-service-token",
        "password",
        "secret",
        "token",
        "access_key",
        "secret_key",
        "private_key",
        "embedding",
        "feature_vector",
    }
)
REDACTED = "[redacted]"


def configure_logging(level: int = logging.INFO) -> None:
    """安装单行 JSON 处理器；重复调用保持幂等。"""
    root = logging.getLogger()
    for handler in root.handlers:
        if getattr(handler, "_scenara_data_json", False):
            root.setLevel(level)
            return
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    handler._scenara_data_json = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(level)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = getattr(record, "scenara_payload", None)
        if isinstance(payload, dict):
            return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        body = {
            "timestamp": utc_rfc3339(),
            "level": record.levelname.lower(),
            "service": "scenara-data",
            "module": record.name,
            "request_id": getattr(record, "request_id", "unassigned"),
            "trace_id": getattr(record, "trace_id", "unassigned"),
            "message": record.getMessage(),
        }
        if record.exc_info:
            body["error_type"] = record.exc_info[0].__name__ if record.exc_info[0] else "未知"
        return json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def utc_rfc3339(moment: datetime | None = None) -> str:
    value = moment or datetime.now(UTC)
    if value.tzinfo is None:
        raise ValueError("日志时间戳必须包含时区")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: (REDACTED if str(key).lower() in SENSITIVE_KEYS else redact(item))
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact(item) for item in value]
    return value


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {key: (REDACTED if key.lower() in SENSITIVE_KEYS else value) for key, value in headers.items()}


def log_event(
    logger: logging.Logger,
    *,
    level: int = logging.INFO,
    service: str,
    module: str,
    message: str,
    request_id: str = "unassigned",
    trace_id: str = "unassigned",
    **fields: Any,
) -> None:
    """写一条满足规范 40 必填字段的结构化日志。"""
    payload: dict[str, Any] = {
        "timestamp": utc_rfc3339(),
        "level": logging.getLevelName(level).lower(),
        "service": service,
        "module": module,
        "request_id": request_id,
        "trace_id": trace_id,
        "message": message,
    }
    payload.update({key: redact(value) for key, value in fields.items() if key not in SENSITIVE_KEYS})
    logger.log(level, message, extra={"scenara_payload": payload})
