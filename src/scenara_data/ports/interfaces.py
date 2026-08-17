from __future__ import annotations

from collections.abc import Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from scenara_data.domain.models import (
    Annotation,
    AnnotationAssignment,
    AnnotationProvider,
    AnnotationReview,
    AnnotationRevision,
    AnnotationSnapshot,
    AnnotationTask,
    AuditRecord,
    DataQualityReport,
    Dataset,
    DatasetAccessGrant,
    DatasetVersion,
    HardSampleImport,
    LineageLink,
    LineageSnapshot,
    MigrationReport,
    ObjectReference,
    OutboxEvent,
    QualityIssue,
    QualityRule,
    QualityRun,
    Sample,
)


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Core 签发并透传的身份上下文；数据平台不保存用户、角色和 API 密钥事实。"""

    tenant_id: str
    project_id: str
    principal_id: str
    permission_scopes: tuple[str, ...]
    request_id: str
    trace_id: str
    principal_type: str = "user"
    product_entitlements: tuple[str, ...] = ()
    idempotency_key: str | None = None

    @property
    def organization_id(self) -> str:
        return self.tenant_id

    def has(self, permission: str) -> bool:
        return permission in self.permission_scopes


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    scope: str
    key: str
    request_hash: str
    status_code: int
    response_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PendingEvent:
    event: OutboxEvent
    attempt_count: int


class UnitOfWork(Protocol):
    """事务边界端口；同一上下文内嵌套调用必须复用外层事务。"""

    def transaction(self) -> AbstractContextManager[None]: ...


class DatasetRepository(Protocol):
    def add_dataset(self, value: Dataset) -> None: ...

    def get_dataset(self, dataset_id: str, organization_id: str, project_id: str) -> Dataset: ...

    def list_datasets(
        self, organization_id: str, project_id: str, *, limit: int, offset: int
    ) -> tuple[list[Dataset], int]: ...

    def update_dataset(self, value: Dataset) -> None: ...

    def add_dataset_version(self, value: DatasetVersion, organization_id: str, project_id: str) -> None: ...

    def get_dataset_version(
        self, dataset_version_id: str, organization_id: str, project_id: str
    ) -> DatasetVersion: ...

    def list_dataset_versions(
        self, dataset_id: str, organization_id: str, project_id: str, *, limit: int, offset: int
    ) -> tuple[list[DatasetVersion], int]: ...

    def update_dataset_version(self, value: DatasetVersion, organization_id: str, project_id: str) -> None: ...

    def add_access_grant(self, value: DatasetAccessGrant, organization_id: str, project_id: str) -> None: ...

    def get_access_grant(self, grant_id: str, organization_id: str, project_id: str) -> DatasetAccessGrant: ...

    def list_access_grants(
        self, dataset_version_id: str, organization_id: str, project_id: str
    ) -> list[DatasetAccessGrant]: ...


class SampleRepository(Protocol):
    def add_sample(self, value: Sample, created_by: str) -> None: ...

    def get_sample(self, sample_id: str, organization_id: str, project_id: str) -> Sample: ...

    def update_sample(self, value: Sample) -> None: ...

    def list_samples(
        self, organization_id: str, project_id: str, *, limit: int, offset: int, dataset_split: str | None = None
    ) -> tuple[list[Sample], int]: ...

    def add_sample_to_version(
        self, dataset_version_id: str, sample_id: str, organization_id: str, project_id: str
    ) -> None: ...

    def restore_sample_to_version(
        self, dataset_version_id: str, sample_id: str, organization_id: str, project_id: str
    ) -> None: ...

    def list_version_samples(
        self, dataset_version_id: str, organization_id: str, project_id: str
    ) -> list[Sample]: ...


class AnnotationRepository(Protocol):
    def add_annotation(self, value: Annotation, organization_id: str, project_id: str) -> None: ...

    def get_annotation(self, annotation_id: str, organization_id: str, project_id: str) -> Annotation: ...

    def update_annotation(self, value: Annotation, organization_id: str, project_id: str) -> None: ...

    def list_annotations(
        self, sample_id: str, organization_id: str, project_id: str, *, limit: int, offset: int
    ) -> tuple[list[Annotation], int]: ...

    def list_sample_annotations(
        self, sample_ids: Iterable[str], organization_id: str, project_id: str
    ) -> list[Annotation]: ...

    def add_revision(self, value: AnnotationRevision, organization_id: str, project_id: str) -> None: ...

    def list_revisions(
        self, annotation_id: str, organization_id: str, project_id: str
    ) -> list[AnnotationRevision]: ...

    def get_revision(self, revision_id: str, organization_id: str, project_id: str) -> AnnotationRevision: ...

    def add_task(self, value: AnnotationTask) -> None: ...

    def get_task(self, task_id: str, organization_id: str, project_id: str) -> AnnotationTask: ...

    def update_task(self, value: AnnotationTask) -> None: ...

    def list_tasks(
        self,
        organization_id: str,
        project_id: str,
        *,
        limit: int,
        offset: int,
        dataset_id: str | None = None,
        status: str | None = None,
    ) -> tuple[list[AnnotationTask], int]: ...

    def add_assignment(self, value: AnnotationAssignment, organization_id: str, project_id: str) -> None: ...

    def list_assignments(
        self, task_id: str, organization_id: str, project_id: str
    ) -> list[AnnotationAssignment]: ...

    def add_review(self, value: AnnotationReview, organization_id: str, project_id: str) -> None: ...

    def list_reviews(self, task_id: str, organization_id: str, project_id: str) -> list[AnnotationReview]: ...

    def add_provider(self, value: AnnotationProvider, organization_id: str, project_id: str) -> None: ...

    def get_provider(self, provider_id: str, organization_id: str, project_id: str) -> AnnotationProvider: ...

    def update_provider(
        self, value: AnnotationProvider, organization_id: str, project_id: str
    ) -> None: ...

    def list_providers(
        self, organization_id: str, project_id: str, *, limit: int, offset: int
    ) -> tuple[list[AnnotationProvider], int]: ...

    def add_annotation_snapshot(
        self, value: AnnotationSnapshot, organization_id: str, project_id: str
    ) -> None: ...

    def get_annotation_snapshot(
        self, snapshot_id: str, organization_id: str, project_id: str
    ) -> AnnotationSnapshot: ...


class QualityRepository(Protocol):
    def add_quality_rule(self, value: QualityRule, organization_id: str, project_id: str) -> None: ...

    def get_quality_rule(self, rule_id: str, organization_id: str, project_id: str) -> QualityRule: ...

    def list_quality_rules(
        self, organization_id: str, project_id: str, *, limit: int, offset: int
    ) -> tuple[list[QualityRule], int]: ...

    def add_quality_run(self, value: QualityRun, organization_id: str, project_id: str) -> None: ...

    def get_quality_run(self, run_id: str, organization_id: str, project_id: str) -> QualityRun: ...

    def update_quality_run(self, value: QualityRun, organization_id: str, project_id: str) -> None: ...

    def list_quality_runs(
        self, dataset_version_id: str, organization_id: str, project_id: str, *, limit: int, offset: int
    ) -> tuple[list[QualityRun], int]: ...

    def add_quality_issue(self, value: QualityIssue, organization_id: str, project_id: str) -> None: ...

    def list_quality_issues(
        self, quality_run_id: str, organization_id: str, project_id: str
    ) -> list[QualityIssue]: ...

    def add_quality_report(
        self, value: DataQualityReport, organization_id: str, project_id: str
    ) -> None: ...

    def get_quality_report(
        self, report_id: str, organization_id: str, project_id: str
    ) -> DataQualityReport: ...


class LineageRepository(Protocol):
    def add_lineage_link(self, value: LineageLink, organization_id: str, project_id: str) -> None: ...

    def list_lineage(self, entity_id: str, organization_id: str, project_id: str) -> list[LineageLink]: ...

    def add_lineage_snapshot(
        self, value: LineageSnapshot, organization_id: str, project_id: str
    ) -> None: ...

    def get_lineage_snapshot(
        self, snapshot_id: str, organization_id: str, project_id: str
    ) -> LineageSnapshot: ...


class HardSampleRepository(Protocol):
    def add_hard_sample_import(
        self, value: HardSampleImport, organization_id: str, project_id: str
    ) -> None: ...

    def get_hard_sample_import(
        self, import_id: str, organization_id: str, project_id: str
    ) -> HardSampleImport: ...

    def find_hard_sample_import_by_manifest(
        self, manifest_id: str, organization_id: str, project_id: str
    ) -> HardSampleImport | None: ...

    def update_hard_sample_import(
        self, value: HardSampleImport, organization_id: str, project_id: str
    ) -> None: ...


class MigrationRepository(Protocol):
    def add_migration_report(
        self, value: MigrationReport, organization_id: str, project_id: str
    ) -> None: ...

    def get_migration_report(
        self, migration_id: str, organization_id: str, project_id: str
    ) -> MigrationReport: ...

    def find_migration_report_by_checksum(
        self, package_checksum: str, organization_id: str, project_id: str
    ) -> MigrationReport | None: ...

    def update_migration_report(
        self, value: MigrationReport, organization_id: str, project_id: str
    ) -> None: ...


class DataRepository(
    UnitOfWork,
    DatasetRepository,
    SampleRepository,
    AnnotationRepository,
    QualityRepository,
    LineageRepository,
    HardSampleRepository,
    MigrationRepository,
    Protocol,
):
    """完整数据仓储端口；适配器必须实现全部领域子端口。"""


class ObjectStorageProvider(Protocol):
    def put_immutable(
        self, key: str, content: bytes, content_type: str, *, bucket: str | None = None
    ) -> ObjectReference: ...

    def read_verified(self, reference: ObjectReference) -> bytes: ...

    def presign_read(self, reference: ObjectReference, expires_in_seconds: int) -> str: ...


class AuditPort(Protocol):
    def record(self, record: AuditRecord) -> None: ...


class OutboxPort(Protocol):
    def append(self, event: OutboxEvent) -> None: ...


class OutboxDispatchPort(Protocol):
    """Outbox 投递端口：至少一次投递，消费方按 event_id 幂等。"""

    def claim_pending(self, *, limit: int, now: datetime) -> list[PendingEvent]: ...

    def mark_delivered(self, event_id: str, delivered_at: datetime) -> None: ...

    def mark_failed(self, event_id: str, *, error: str, available_at: datetime) -> None: ...


class EventPublisher(Protocol):
    """事件传输实现（Webhook、消息队列或轮询）；不得改变事件契约。"""

    def publish(self, event: OutboxEvent) -> None: ...


class IdempotencyStore(Protocol):
    def get(self, scope: str, key: str) -> IdempotencyRecord | None: ...

    def save(self, record: IdempotencyRecord) -> None: ...


class LockProvider(Protocol):
    """分布式锁端口；Redis 只承载锁和临时状态，不保存领域事实。"""

    def lock(self, name: str, *, ttl_seconds: int = 30) -> AbstractContextManager[None]: ...


class MigrationPackageSource(Protocol):
    """Core 生成的迁移包读取端口；数据平台不连接 Core 数据库（指南 13）。"""

    @property
    def package_name(self) -> str: ...

    def names(self) -> tuple[str, ...]: ...

    def read(self, name: str) -> bytes: ...

    def exists(self, name: str) -> bool: ...
