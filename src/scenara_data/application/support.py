"""应用层共享支撑：ID 生成、权限检查、审计与事件登记。"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from scenara_data import contracts
from scenara_data.application.errors import AuthorizationError
from scenara_data.domain.models import AuditRecord, OutboxEvent
from scenara_data.ports.interfaces import AuditPort, OutboxPort, RequestContext, UnitOfWork

Clock = Callable[[], datetime]
def utc_now() -> datetime:
    return datetime.now(UTC)


def uuid7() -> UUID:
    """RFC 9562 UUIDv7：48 位毫秒时间戳 + 74 位随机，天然按时间排序。

    Python 3.12 标准库尚未提供 `uuid.uuid7`，这里按规范 36 自行实现，供高写入量实体使用。
    """
    timestamp_ms = time.time_ns() // 1_000_000
    random_bytes = bytearray(os.urandom(10))
    value = bytearray(timestamp_ms.to_bytes(6, "big")) + random_bytes
    value[6] = 0x70 | (value[6] & 0x0F)  # version 7
    value[8] = 0x80 | (value[8] & 0x3F)  # RFC 4122 variant
    return UUID(bytes=bytes(value))


def new_id(prefix: str, *, time_ordered: bool = True) -> str:
    """`<entity_prefix>_<uuid>` 形式的不透明业务 ID（规范 36）。"""
    if not prefix or not prefix.isalnum() or not prefix.islower():
        raise ValueError("实体前缀只能包含小写字母和数字")
    value = uuid7() if time_ordered else uuid4()
    return f"{prefix}_{value.hex}"


def transactional[**P, R](method: Callable[P, R]) -> Callable[P, R]:
    """在服务事务边界内执行；嵌套调用复用外层事务。"""

    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        service = args[0]
        with service._unit_of_work.transaction():  # noqa: SLF001 - 装饰器专用于本包服务
            return method(*args, **kwargs)

    wrapped.__name__ = method.__name__
    wrapped.__doc__ = method.__doc__
    wrapped.__wrapped__ = method  # type: ignore[attr-defined]
    return wrapped


class ApplicationService:
    """所有应用服务的共同基类：统一权限、审计和事件登记路径。"""

    def __init__(
        self,
        *,
        unit_of_work: UnitOfWork,
        audit: AuditPort,
        outbox: OutboxPort,
        clock: Clock = utc_now,
        producer: str = contracts.EVENT_PRODUCER,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._audit = audit
        self._outbox = outbox
        self._clock = clock
        self._producer = producer

    @staticmethod
    def _require(context: RequestContext, permission: str) -> None:
        contracts.assert_registered_permission(permission)
        if not context.has(permission):
            raise AuthorizationError(permission)

    def _record_audit(
        self,
        action: str,
        entity_type: str,
        entity_id: str,
        context: RequestContext,
        *,
        before: Any | None = None,
        after: Any | None = None,
        result: str = "succeeded",
    ) -> AuditRecord:
        record = AuditRecord(
            audit_id=new_id("aud"),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            organization_id=context.organization_id,
            project_id=context.project_id,
            principal_id=context.principal_id,
            request_id=context.request_id,
            trace_id=context.trace_id,
            occurred_at=self._clock(),
            result=result,
            before=_dump(before),
            after=_dump(after),
        )
        self._audit.record(record)
        return record

    def _emit(
        self,
        event_type: str,
        context: RequestContext,
        occurred_at: datetime,
        data: dict[str, Any],
    ) -> OutboxEvent:
        event = OutboxEvent(
            event_id=new_id("evt"),
            event_type=contracts.assert_registered_event(event_type),
            event_version=contracts.EVENT_ENVELOPE_VERSION,
            occurred_at=occurred_at,
            producer=self._producer,
            tenant_id=context.organization_id,
            project_id=context.project_id,
            request_id=context.request_id,
            trace_id=context.trace_id,
            data=data,
        )
        self._outbox.append(event)
        return event


def _dump(value: Any | None) -> dict[str, Any] | None:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    raise TypeError("审计 before/after 必须是领域模型或映射")
