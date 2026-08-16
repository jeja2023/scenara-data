"""基础设施适配器：实现 `scenara_data.ports` 端口，业务层不直接依赖具体实现。

- `memory`：开发与单元测试适配器，不是生产事实存储。
- `postgres`：PostgreSQL 仓储、审计、Outbox 与幂等适配器。
- `s3`：S3-compatible 对象存储 Provider（MinIO 为第一阶段基线）。
- `redis`：分布式锁与临时状态。
- `events`：事件传输实现。
- `migration_package`：Core 迁移包读取。
"""

from __future__ import annotations

__all__ = [
    "events",
    "memory",
    "migration_package",
    "postgres",
    "redis",
    "s3",
]
