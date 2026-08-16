"""Outbox 投递（规范 34；指南 12）。

业务提交与事件登记在同一事务内完成，投递独立进行：允许至少一次，消费方按 `event_id` 幂等。
超过最大尝试次数的事件进入死信状态，等待人工处理，不再自动重试。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from scenara_data.application.support import Clock, utc_now
from scenara_data.observability.logging import log_event
from scenara_data.observability.metrics import MetricsRegistry
from scenara_data.ports.interfaces import EventPublisher, OutboxDispatchPort

LOGGER = logging.getLogger("scenara_data.outbox")

DEAD_LETTER_PREFIX = "DEAD_LETTER"
BASE_BACKOFF_SECONDS = 5
MAX_BACKOFF_SECONDS = 900
DEAD_LETTER_BACKOFF_SECONDS = 86_400


@dataclass(frozen=True, slots=True)
class DispatchSummary:
    claimed: int
    delivered: int
    failed: int
    dead_lettered: int

    @property
    def has_work(self) -> bool:
        return self.claimed > 0


def backoff_seconds(attempt_count: int) -> int:
    """指数退避；attempt_count 为本次之前的失败次数。"""
    if attempt_count < 0:
        raise ValueError("attempt_count cannot be negative")
    return min(BASE_BACKOFF_SECONDS * (2**attempt_count), MAX_BACKOFF_SECONDS)


class OutboxDispatcher:
    def __init__(
        self,
        *,
        dispatch: OutboxDispatchPort,
        publisher: EventPublisher,
        clock: Clock = utc_now,
        batch_size: int = 100,
        max_attempts: int = 8,
        metrics: MetricsRegistry | None = None,
        service_name: str = "scenara-data",
    ) -> None:
        if batch_size <= 0 or max_attempts <= 0:
            raise ValueError("batch_size and max_attempts must be positive")
        self._dispatch = dispatch
        self._publisher = publisher
        self._clock = clock
        self._batch_size = batch_size
        self._max_attempts = max_attempts
        self._metrics = metrics
        self._service_name = service_name

    def dispatch_once(self) -> DispatchSummary:
        now = self._clock()
        pending = self._dispatch.claim_pending(limit=self._batch_size, now=now)
        delivered = 0
        failed = 0
        dead_lettered = 0
        for item in pending:
            try:
                self._publisher.publish(item.event)
            except Exception as exc:  # 传输失败不得影响已提交业务事实
                attempts = item.attempt_count + 1
                if attempts >= self._max_attempts:
                    dead_lettered += 1
                    self._dispatch.mark_failed(
                        item.event.event_id,
                        error=f"{DEAD_LETTER_PREFIX}: {type(exc).__name__}: {exc}"[:1000],
                        available_at=now + timedelta(seconds=DEAD_LETTER_BACKOFF_SECONDS),
                    )
                    self._observe("outbox_dead_letter_total", item.event.event_type)
                    self._log(
                        logging.ERROR,
                        "outbox.event.dead_lettered",
                        item,
                        attempts=attempts,
                        error_type=type(exc).__name__,
                    )
                    continue
                failed += 1
                self._dispatch.mark_failed(
                    item.event.event_id,
                    error=f"{type(exc).__name__}: {exc}"[:1000],
                    available_at=now + timedelta(seconds=backoff_seconds(item.attempt_count)),
                )
                self._observe("outbox_delivery_failure_total", item.event.event_type)
                self._log(
                    logging.WARNING,
                    "outbox.event.retry_scheduled",
                    item,
                    attempts=attempts,
                    error_type=type(exc).__name__,
                )
                continue
            delivered += 1
            self._dispatch.mark_delivered(item.event.event_id, self._clock())
            self._observe("outbox_delivered_total", item.event.event_type)
        return DispatchSummary(
            claimed=len(pending), delivered=delivered, failed=failed, dead_lettered=dead_lettered
        )

    def drain(self, *, max_batches: int = 100) -> DispatchSummary:
        """连续投递直到没有到期事件或达到批次上限。"""
        totals = [0, 0, 0, 0]
        for _ in range(max_batches):
            summary = self.dispatch_once()
            totals[0] += summary.claimed
            totals[1] += summary.delivered
            totals[2] += summary.failed
            totals[3] += summary.dead_lettered
            if not summary.has_work:
                break
        return DispatchSummary(claimed=totals[0], delivered=totals[1], failed=totals[2], dead_lettered=totals[3])

    def _observe(self, metric: str, event_type: str) -> None:
        if self._metrics is not None:
            self._metrics.increment(metric, labels={"event_type": event_type})

    def _log(self, level: int, message: str, item: object, **fields: object) -> None:
        event = getattr(item, "event", None)
        log_event(
            LOGGER,
            level=level,
            service=self._service_name,
            module="outbox",
            message=message,
            request_id=getattr(event, "request_id", "unassigned"),
            trace_id=getattr(event, "trace_id", "unassigned"),
            event_id=getattr(event, "event_id", None),
            event_type=getattr(event, "event_type", None),
            **fields,
        )


def next_available_at(now: datetime, attempt_count: int) -> datetime:
    return now + timedelta(seconds=backoff_seconds(attempt_count))
