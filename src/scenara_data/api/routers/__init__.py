"""API 路由模块：按领域划分，统一 `/internal/v1` 前缀与运维探针。

`annotation` 模块使用单数命名，避免与 `from __future__ import annotations` 绑定的名字冲突。
"""

from __future__ import annotations

from scenara_data.api.routers import (
    annotation,
    dataset_versions,
    datasets,
    hard_samples,
    lineage,
    operations,
    quality,
    samples,
)

#: 注册顺序即 OpenAPI 文档顺序。
ROUTERS = (
    operations.router,
    datasets.router,
    dataset_versions.router,
    samples.router,
    annotation.router,
    quality.router,
    lineage.router,
    hard_samples.router,
)

__all__ = ["ROUTERS"]
