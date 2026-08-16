"""内存审计、Outbox、幂等与锁适配器。"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import RLock

from scenara_data.domain.models import AuditRecord, OutboxEvent
from scenara_data.observability.logging import log_event
from scenara_data.ports.interfaces import IdempotencyRecord, PendingEvent

LOGGER = logging.getLogger("scenara_data.events")
OUTBOX_CLAIM_LEASE_SECONDS = 30


class InMemoryAuditPort:
    """本地不可变领域审计记录；平台统一审计查询由 Core 提供。"""

    def __init__(self) -> None:
        self._lock = RLock()
        self.records: list[AuditRecord] = []

    def record(self, record: AuditRecord) -> None:
        with self._lock:
            self.records.append(record)

    def actions(self) -> list[str]:
        return [item.action for item in self.records]

    def _transaction_snapshot(self) -> list[AuditRecord]:
        return list(self.records)

    def _transaction_restore(self, snapshot: list[AuditRecord]) -> None:
        self.records = list(snapshot)


@dataclass(slots=True)
class _OutboxRow:
    event: OutboxEvent
    attempt_count: int = 0
    available_at: datetime | None = None
    delivered_at: datetime | None = None
    last_error: str | None = None


@dataclass(slots=True)
class InMemoryOutbox:
    """Outbox 登记与投递端口的内存实现。"""

    _lock: RLock = field(default_factory=RLock)
    _rows: dict[str, _OutboxRow] = field(default_factory=dict)

    def append(self, event: OutboxEvent) -> None:
        with self._lock:
            if event.event_id in self._rows:
                raise ValueError("duplicate outbox event")
            self._rows[event.event_id] = _OutboxRow(event=event)

    @property
    def events(self) -> list[OutboxEvent]:
        with self._lock:
            return [row.event for row in self._rows.values()]

    def event_types(self) -> list[str]:
        return [event.event_type for event in self.events]

    def claim_pending(self, *, limit: int, now: datetime) -> list[PendingEvent]:
        with self._lock:
            pending = [
                row
                for row in self._rows.values()
                if row.delivered_at is None and (row.available_at is None or row.available_at <= now)
            ]
            pending.sort(key=lambda row: (row.event.occurred_at, row.event.event_id))
            claimed = pending[:limit]
            for row in claimed:
                row.available_at = now + timedelta(seconds=OUTBOX_CLAIM_LEASE_SECONDS)
            return [PendingEvent(event=row.event, attempt_count=row.attempt_count) for row in claimed]

    def mark_delivered(self, event_id: str, delivered_at: datetime) -> None:
        with self._lock:
            row = self._rows.get(event_id)
            if row is None:
                raise KeyError(event_id)
            row.delivered_at = delivered_at
            row.last_error = None

    def mark_failed(self, event_id: str, *, error: str, available_at: datetime) -> None:
        with self._lock:
            row = self._rows.get(event_id)
            if row is None:
                raise KeyError(event_id)
            row.attempt_count += 1
            row.available_at = available_at
            row.last_error = error

    def undelivered(self) -> list[OutboxEvent]:
        with self._lock:
            return [row.event for row in self._rows.values() if row.delivered_at is None]

    def _transaction_snapshot(self) -> dict[str, _OutboxRow]:
        return {
            key: _OutboxRow(
                event=row.event,
                attempt_count=row.attempt_count,
                available_at=row.available_at,
                delivered_at=row.delivered_at,
                last_error=row.last_error,
            )
            for key, row in self._rows.items()
        }

    def _transaction_restore(self, snapshot: dict[str, _OutboxRow]) -> None:
        self._rows = {
            key: _OutboxRow(
                event=row.event,
                attempt_count=row.attempt_count,
                available_at=row.available_at,
                delivered_at=row.delivered_at,
                last_error=row.last_error,
            )
            for key, row in snapshot.items()
        }


class InMemoryIdempotencyStore:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str], IdempotencyRecord] = {}
        self._lock = RLock()

    def get(self, scope: str, key: str) -> IdempotencyRecord | None:
        with self._lock:
            return self._records.get((scope, key))

    def save(self, record: IdempotencyRecord) -> None:
        with self._lock:
            identity = (record.scope, record.key)
            if identity in self._records:
                raise ValueError("duplicate idempotency record")
            self._records[identity] = record

    def _transaction_snapshot(self) -> dict[tuple[str, str], IdempotencyRecord]:
        return dict(self._records)

    def _transaction_restore(self, snapshot: dict[tuple[str, str], IdempotencyRecord]) -> None:
        self._records = dict(snapshot)


class InProcessLockProvider:
    """单进程锁；多副本部署必须换用 Redis 适配器。"""

    def __init__(self) -> None:
        self._guard = RLock()
        self._locks: dict[str, RLock] = {}

    @contextmanager
    def lock(self, name: str, *, ttl_seconds: int = 30) -> Iterator[None]:
        if ttl_seconds <= 0:
            raise ValueError("lock ttl must be positive")
        with self._guard:
            handle = self._locks.setdefault(name, RLock())
        with handle:
            yield


class LoggingEventPublisher:
    """把事件写入结构化日志的传输实现；不改变事件契约（指南 12）。"""

    def __init__(self, *, service_name: str = "scenara-data") -> None:
        self._service_name = service_name
        self.published: list[OutboxEvent] = []

    def publish(self, event: OutboxEvent) -> None:
        self.published.append(event)
        log_event(
            LOGGER,
            service=self._service_name,
            module="events",
            message="outbox.event.published",
            request_id=event.request_id,
            trace_id=event.trace_id,
            event_id=event.event_id,
            event_type=event.event_type,
            event_version=event.event_version,
            tenant_id=event.tenant_id,
            project_id=event.project_id,
        )
