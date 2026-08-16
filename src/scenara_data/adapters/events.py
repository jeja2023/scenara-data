"""事件传输适配器（规范 34、57；指南 12）。

跨仓库 Client 必须显式配置基础地址、认证、超时、重试、幂等、熔断、追踪和错误映射。
传输失败只影响投递，不影响已提交的业务事实。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from scenara_data.domain.models import OutboxEvent
from scenara_data.observability.tracing import format_traceparent

RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


class EventDeliveryError(RuntimeError):
    """事件投递失败；由 Outbox 调度器决定退避与死信。"""


class CircuitOpenError(EventDeliveryError):
    """熔断打开期间拒绝继续投递。"""


@dataclass(frozen=True, slots=True)
class EventTransportSettings:
    endpoint: str
    token: str
    timeout_seconds: float = 5.0
    max_attempts: int = 3
    backoff_seconds: float = 0.2
    circuit_failure_threshold: int = 5
    circuit_reset_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not self.endpoint.startswith("https://") and not self.endpoint.startswith("http://"):
            raise ValueError("事件投递地址必须是 http(s) URL")
        if not self.token:
            raise ValueError("事件投递必须配置服务间凭据")
        if self.timeout_seconds <= 0 or self.max_attempts <= 0:
            raise ValueError("超时和重试次数必须为正")


class HttpEventPublisher:
    """把统一事件信封投递到 Core 的审计/事件接收端点。"""

    def __init__(
        self,
        settings: EventTransportSettings,
        *,
        client: Any | None = None,
        monotonic: Any = time.monotonic,
        sleep: Any = time.sleep,
    ) -> None:
        self._settings = settings
        self._monotonic = monotonic
        self._sleep = sleep
        self._failures = 0
        self._opened_at: float | None = None
        if client is not None:
            self._client = client
        else:
            try:
                import httpx  # 延迟导入：HTTP 传输是可选运行依赖
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("HTTP 事件投递需要安装 scenara-data[http]") from exc
            self._client = httpx.Client(timeout=settings.timeout_seconds)

    def publish(self, event: OutboxEvent) -> None:
        self._assert_circuit_closed()
        payload = event.model_dump(mode="json")
        headers = {
            "authorization": f"Bearer {self._settings.token}",
            "content-type": "application/json",
            "idempotency-key": event.event_id,
            "x-request-id": event.request_id,
            "x-trace-id": event.trace_id,
            "x-scenara-tenant-id": event.tenant_id,
            "x-scenara-project-id": event.project_id,
        }
        if len(event.trace_id) == 32:
            headers["traceparent"] = format_traceparent(event.trace_id, event.event_id[-16:].rjust(16, "0"))
        last_error: str = "unknown"
        for attempt in range(self._settings.max_attempts):
            try:
                response = self._client.post(self._settings.endpoint, json=payload, headers=headers)
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            else:
                status = int(getattr(response, "status_code", 0))
                if 200 <= status < 300:
                    self._record_success()
                    return
                last_error = f"HTTP {status}"
                if status not in RETRYABLE_STATUS:
                    self._record_failure()
                    raise EventDeliveryError(f"事件投递被拒绝：{last_error}")
            if attempt + 1 < self._settings.max_attempts:
                self._sleep(self._settings.backoff_seconds * (2**attempt))
        self._record_failure()
        raise EventDeliveryError(f"事件投递重试耗尽：{last_error}")

    def _assert_circuit_closed(self) -> None:
        if self._opened_at is None:
            return
        if self._monotonic() - self._opened_at < self._settings.circuit_reset_seconds:
            raise CircuitOpenError("事件投递熔断打开，等待恢复窗口")
        self._opened_at = None
        self._failures = self._settings.circuit_failure_threshold - 1

    def _record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def _record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._settings.circuit_failure_threshold:
            self._opened_at = self._monotonic()
