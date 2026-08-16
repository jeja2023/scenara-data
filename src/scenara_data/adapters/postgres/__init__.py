"""PostgreSQL 适配器：仓储、审计、Outbox 与幂等的单一实现入口。

`data_*` 表全部带 `tenant_id`/`project_id`，不存在到 Core 数据库的外键、视图或跨库查询
（指南 8；规范 61）。
"""

from __future__ import annotations

from scenara_data.adapters.postgres._sql import SqlSupport
from scenara_data.adapters.postgres.annotations import AnnotationSqlMixin
from scenara_data.adapters.postgres.datasets import DatasetSqlMixin
from scenara_data.adapters.postgres.intake import IntakeSqlMixin, SupportSqlMixin
from scenara_data.adapters.postgres.quality import LineageSqlMixin, QualitySqlMixin
from scenara_data.adapters.postgres.samples import SampleSqlMixin


class PostgresDataAdapter(
    DatasetSqlMixin,
    SampleSqlMixin,
    AnnotationSqlMixin,
    QualitySqlMixin,
    LineageSqlMixin,
    IntakeSqlMixin,
    SupportSqlMixin,
    SqlSupport,
):
    """实现 `DataRepository`、`AuditPort`、`OutboxPort`、`OutboxDispatchPort` 与 `IdempotencyStore`。"""


__all__ = ["PostgresDataAdapter"]
