"""应用层：按领域拆分的编排服务。

每个服务只声明自己需要的仓储端口和 Provider，事务边界由 `UnitOfWork` 统一表达。
"""

from __future__ import annotations

from scenara_data.application.annotations import AnnotationService
from scenara_data.application.builder import BuildResult, DatasetBuilderService
from scenara_data.application.datasets import DatasetService
from scenara_data.application.hard_samples import HardSampleService, IntakeResult
from scenara_data.application.idempotency import IdempotencyService, request_digest
from scenara_data.application.lineage import LineageService
from scenara_data.application.migration import MigrationImportService
from scenara_data.application.outbox import DispatchSummary, OutboxDispatcher
from scenara_data.application.quality import QualityService
from scenara_data.application.samples import SampleService

__all__ = [
    "AnnotationService",
    "BuildResult",
    "DatasetBuilderService",
    "DatasetService",
    "DispatchSummary",
    "HardSampleService",
    "IdempotencyService",
    "IntakeResult",
    "LineageService",
    "MigrationImportService",
    "OutboxDispatcher",
    "QualityService",
    "SampleService",
    "request_digest",
]
