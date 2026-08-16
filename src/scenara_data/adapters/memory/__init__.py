"""内存适配器：开发与单元测试专用，永远不是生产事实存储。"""

from __future__ import annotations

from scenara_data.adapters.memory.repository import InMemoryDataRepository
from scenara_data.adapters.memory.storage import InMemoryObjectStorage, PresignedUrlError
from scenara_data.adapters.memory.support import (
    InMemoryAuditPort,
    InMemoryIdempotencyStore,
    InMemoryOutbox,
    InProcessLockProvider,
    LoggingEventPublisher,
)

__all__ = [
    "InMemoryAuditPort",
    "InMemoryDataRepository",
    "InMemoryIdempotencyStore",
    "InMemoryObjectStorage",
    "InMemoryOutbox",
    "InProcessLockProvider",
    "LoggingEventPublisher",
    "PresignedUrlError",
]
