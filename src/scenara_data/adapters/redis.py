"""Redis 适配器：分布式锁与临时状态（规范 30；指南 4）。

Redis 只承载锁、队列和临时状态，禁止保存 Dataset、Sample、Annotation 或发布状态事实。
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

LOCK_PREFIX = "scenara-data:lock:"
DEFAULT_ACQUIRE_TIMEOUT_SECONDS = 10.0
POLL_INTERVAL_SECONDS = 0.05

# 只有锁持有者才能释放锁，避免误删他人锁。
RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


class LockAcquisitionError(RuntimeError):
    """在超时时间内没有获得锁。"""


class RedisLockProvider:
    def __init__(
        self,
        redis_url: str,
        *,
        client: Any | None = None,
        acquire_timeout_seconds: float = DEFAULT_ACQUIRE_TIMEOUT_SECONDS,
    ) -> None:
        if client is not None:
            self._client = client
        else:
            try:
                import redis  # 延迟导入：Redis 是可选运行依赖
            except ImportError as exc:  # pragma: no cover - 依赖缺失时给出明确指引
                raise RuntimeError("Redis 锁需要安装 scenara-data[redis]") from exc
            self._client = redis.Redis.from_url(redis_url)
        self._acquire_timeout_seconds = acquire_timeout_seconds

    def ping(self) -> bool:
        try:
            return bool(self._client.ping())
        except Exception:
            return False

    @contextmanager
    def lock(self, name: str, *, ttl_seconds: int = 30) -> Iterator[None]:
        if ttl_seconds <= 0:
            raise ValueError("lock ttl must be positive")
        key = f"{LOCK_PREFIX}{name}"
        token = secrets.token_hex(16)
        deadline = time.monotonic() + self._acquire_timeout_seconds
        while True:
            if self._client.set(key, token, nx=True, ex=ttl_seconds):
                break
            if time.monotonic() >= deadline:
                raise LockAcquisitionError(f"未能在 {self._acquire_timeout_seconds}s 内获得锁 {name}")
            time.sleep(POLL_INTERVAL_SECONDS)
        try:
            yield
        finally:
            try:
                self._client.eval(RELEASE_SCRIPT, 1, key, token)
            except Exception:  # 释放失败由 TTL 兜底，不掩盖业务异常
                pass
