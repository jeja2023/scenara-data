"""依赖装配：按运行模式选择适配器，向 API 暴露领域服务。

内存模式只用于开发与单元测试；postgres 模式是唯一的事实存储运行模式。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scenara_data.adapters.memory import (
    InMemoryAuditPort,
    InMemoryDataRepository,
    InMemoryIdempotencyStore,
    InMemoryObjectStorage,
    InMemoryOutbox,
    InProcessLockProvider,
    LoggingEventPublisher,
)
from scenara_data.application.annotations import AnnotationService
from scenara_data.application.builder import DatasetBuilderService
from scenara_data.application.datasets import DatasetService
from scenara_data.application.hard_samples import HardSampleService
from scenara_data.application.idempotency import IdempotencyService
from scenara_data.application.lineage import LineageService
from scenara_data.application.migration import MigrationImportService
from scenara_data.application.outbox import OutboxDispatcher
from scenara_data.application.quality import QualityService
from scenara_data.application.samples import SampleService
from scenara_data.config import Settings
from scenara_data.observability.metrics import MetricsRegistry
from scenara_data.ports.interfaces import (
    AuditPort,
    DataRepository,
    EventPublisher,
    IdempotencyStore,
    LockProvider,
    ObjectStorageProvider,
    OutboxDispatchPort,
    OutboxPort,
)

METRIC_DEFINITIONS = (
    ("scenara_data_http_requests_total", "按方法、路由和状态码统计的 API 请求数"),
    ("scenara_data_http_request_duration_ms", "API 请求耗时（毫秒）"),
    ("scenara_data_http_errors_total", "按错误码统计的 API 失败数"),
    ("outbox_delivered_total", "成功投递的 Outbox 事件数"),
    ("outbox_delivery_failure_total", "投递失败并进入退避的事件数"),
    ("outbox_dead_letter_total", "超过最大尝试次数进入死信的事件数"),
)


@dataclass(slots=True)
class ApplicationContainer:
    settings: Settings
    repository: DataRepository
    object_storage: ObjectStorageProvider
    audit: AuditPort
    outbox: OutboxPort
    outbox_dispatch: OutboxDispatchPort
    idempotency_store: IdempotencyStore
    lock: LockProvider
    event_publisher: EventPublisher
    metrics: MetricsRegistry
    datasets: DatasetService
    samples: SampleService
    annotations: AnnotationService
    quality: QualityService
    lineage: LineageService
    hard_samples: HardSampleService
    builder: DatasetBuilderService
    migrations: MigrationImportService
    idempotency: IdempotencyService
    dispatcher: OutboxDispatcher

    def readiness(self) -> dict[str, bool]:
        """真实探测必需依赖；不得始终返回成功（指南 11.3）。"""
        checks: dict[str, bool] = {
            "repository": _ping(self.repository),
            "object_storage": _ping(self.object_storage),
        }
        if self.settings.redis_url:
            checks["lock"] = _ping(self.lock)
        return checks


def _ping(dependency: Any) -> bool:
    probe = getattr(dependency, "ping", None)
    if probe is None:
        return False
    try:
        return bool(probe())
    except Exception:
        return False


def build_container(settings: Settings) -> ApplicationContainer:
    if settings.runtime_mode == "memory":
        repository: Any = InMemoryDataRepository()
        object_storage: Any = InMemoryObjectStorage(settings.dataset_bucket)
        audit: Any = InMemoryAuditPort()
        outbox: Any = InMemoryOutbox()
        outbox_dispatch: Any = outbox
        idempotency_store: Any = InMemoryIdempotencyStore()
    elif settings.runtime_mode == "postgres":
        from scenara_data.adapters.postgres import PostgresDataAdapter
        from scenara_data.adapters.s3 import S3ObjectStorage

        repository = PostgresDataAdapter(settings.database_url)
        object_storage = S3ObjectStorage(settings)
        audit = repository
        outbox = repository
        outbox_dispatch = repository
        idempotency_store = repository
    else:  # pragma: no cover - load_settings 已拒绝未知模式
        raise RuntimeError(f"不支持的 SCENARA_DATA_RUNTIME_MODE：{settings.runtime_mode}")

    lock: Any
    if settings.redis_url:
        from scenara_data.adapters.redis import RedisLockProvider

        lock = RedisLockProvider(settings.redis_url)
    else:
        lock = InProcessLockProvider()

    event_publisher: Any
    if settings.core_event_endpoint and settings.core_event_token:
        from scenara_data.adapters.events import EventTransportSettings, HttpEventPublisher

        event_publisher = HttpEventPublisher(
            EventTransportSettings(
                endpoint=settings.core_event_endpoint,
                token=settings.core_event_token,
                timeout_seconds=settings.core_event_timeout_seconds,
            )
        )
    else:
        event_publisher = LoggingEventPublisher(service_name=settings.service_name)

    metrics = MetricsRegistry()
    for name, help_text in METRIC_DEFINITIONS:
        metrics.describe(name, help_text)

    if settings.runtime_mode == "memory":
        repository.register_transaction_participant(audit)
        repository.register_transaction_participant(outbox)
        repository.register_transaction_participant(idempotency_store)

    shared = {"unit_of_work": repository, "audit": audit, "outbox": outbox}
    samples = SampleService(
        samples=repository,
        object_storage=object_storage,
        allowed_source_systems=settings.allowed_source_systems,
        **shared,
    )
    annotations = AnnotationService(
        annotations=repository, samples=repository, datasets=repository, **shared
    )
    quality = QualityService(
        quality=repository,
        datasets=repository,
        samples=repository,
        annotations=repository,
        object_storage=object_storage,
        **shared,
    )
    lineage = LineageService(lineage=repository, **shared)
    datasets = DatasetService(
        datasets=repository,
        samples=repository,
        annotations=annotations,
        lineage=lineage,
        quality=quality,
        object_storage=object_storage,
        dataset_bucket=settings.dataset_bucket,
        manifest_bucket=settings.manifest_bucket,
        access_grant_max_ttl_seconds=settings.access_grant_max_ttl_seconds,
        **shared,
    )
    builder = DatasetBuilderService(datasets=datasets)
    hard_samples = HardSampleService(
        hard_samples=repository,
        samples=samples,
        annotations=annotations,
        builder=builder,
        object_storage=object_storage,
        allowed_source_systems=settings.allowed_source_systems,
        **shared,
    )
    migrations = MigrationImportService(
        datasets=repository,
        samples=repository,
        annotations=repository,
        migrations=repository,
        object_storage=object_storage,
        import_bucket=settings.import_bucket,
        **shared,
    )
    dispatcher = OutboxDispatcher(
        dispatch=outbox_dispatch,
        publisher=event_publisher,
        batch_size=settings.outbox_batch_size,
        max_attempts=settings.outbox_max_attempts,
        metrics=metrics,
        service_name=settings.service_name,
    )
    return ApplicationContainer(
        settings=settings,
        repository=repository,
        object_storage=object_storage,
        audit=audit,
        outbox=outbox,
        outbox_dispatch=outbox_dispatch,
        idempotency_store=idempotency_store,
        lock=lock,
        event_publisher=event_publisher,
        metrics=metrics,
        datasets=datasets,
        samples=samples,
        annotations=annotations,
        quality=quality,
        lineage=lineage,
        hard_samples=hard_samples,
        builder=builder,
        migrations=migrations,
        idempotency=IdempotencyService(idempotency_store, unit_of_work=repository),
        dispatcher=dispatcher,
    )
