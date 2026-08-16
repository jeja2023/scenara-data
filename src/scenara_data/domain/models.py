from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SEMVER = r"^\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?$"
BUSINESS_ID = r"^[a-z][a-z0-9_.-]{1,127}$"
CHECKSUM = r"^sha256:[0-9a-f]{64}$"


class DomainModel(BaseModel):
    """Immutable domain values shared by the Data service."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("*", check_fields=False)
    @classmethod
    def utc_timezone_required(cls, value: Any) -> Any:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                raise ValueError("timestamps must include a timezone")
            if value.utcoffset() != UTC.utcoffset(value):
                raise ValueError("timestamps must use UTC")
        return value


class DatasetStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class DatasetVersionStatus(StrEnum):
    DRAFT = "draft"
    BUILDING = "building"
    READY = "ready"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    FAILED = "failed"


class AnnotationStatus(StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class QualityStatus(StrEnum):
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"


class AnnotationTaskStatus(StrEnum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


JOB_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.QUEUED: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
    JobStatus.RUNNING: frozenset({JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}),
    JobStatus.SUCCEEDED: frozenset(),
    JobStatus.FAILED: frozenset(),
    JobStatus.CANCELLED: frozenset(),
}



class ObjectReference(DomainModel):
    """Portable, checksum-addressable object storage reference."""

    bucket: str = Field(min_length=1, max_length=255)
    key: str = Field(min_length=1, max_length=1024)
    version: str | None = Field(default=None, max_length=256)
    checksum: str = Field(pattern=CHECKSUM)
    size_bytes: int = Field(ge=0)
    content_type: str = Field(min_length=1, max_length=255)

    @field_validator("bucket")
    @classmethod
    def portable_bucket(cls, value: str) -> str:
        if "/" in value or "\\" in value or value.strip() != value:
            raise ValueError("object references must use a portable bucket name")
        return value

    @field_validator("key")
    @classmethod
    def portable_key(cls, value: str) -> str:
        parts = value.split("/")
        if (
            value.startswith(("/", "\\"))
            or "\\" in value
            or ":" in value
            or any(part in {"", ".", ".."} for part in parts)
        ):
            raise ValueError("object references must use a portable object key")
        return value


class Dataset(DomainModel):
    dataset_id: str = Field(pattern=BUSINESS_ID)
    name: str = Field(min_length=1, max_length=256)
    description: str = Field(default="", max_length=2000)
    tenant_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    created_by: str = Field(min_length=1, max_length=128)
    created_at: datetime
    status: DatasetStatus = DatasetStatus.DRAFT
    owner_principal_id: str | None = Field(default=None, min_length=1, max_length=128)
    labels: tuple[str, ...] = Field(default_factory=tuple, max_length=100)
    dataset_metadata: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime | None = None
    archived_at: datetime | None = None

    @model_validator(mode="after")
    def archived_dataset_has_timestamp(self) -> Dataset:
        if self.status == DatasetStatus.ARCHIVED and self.archived_at is None:
            raise ValueError("archived datasets require archived_at")
        if self.status != DatasetStatus.ARCHIVED and self.archived_at is not None:
            raise ValueError("only archived datasets can have archived_at")
        return self

    def activate(self, occurred_at: datetime) -> Dataset:
        if self.status != DatasetStatus.DRAFT:
            raise ValueError(f"illegal dataset transition: {self.status} -> active")
        return self.model_copy(update={"status": DatasetStatus.ACTIVE, "updated_at": occurred_at})

    def archive(self, occurred_at: datetime) -> Dataset:
        if self.status not in {DatasetStatus.DRAFT, DatasetStatus.ACTIVE}:
            raise ValueError(f"illegal dataset transition: {self.status} -> archived")
        return self.model_copy(
            update={"status": DatasetStatus.ARCHIVED, "updated_at": occurred_at, "archived_at": occurred_at}
        )


class Sample(DomainModel):
    sample_id: str = Field(pattern=BUSINESS_ID)
    tenant_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    source_ref: ObjectReference
    media_type: str = Field(min_length=1, max_length=128)
    source_lineage: tuple[str, ...] = Field(min_length=1, max_length=100)
    sample_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    content_ref: ObjectReference | None = None
    media_kind: str | None = Field(default=None, min_length=1, max_length=128)
    content_sha256: str | None = Field(default=None, pattern=CHECKSUM)
    source_system: str | None = Field(default=None, min_length=1, max_length=128)
    source_resource_type: str | None = Field(default=None, min_length=1, max_length=128)
    source_resource_id: str | None = Field(default=None, min_length=1, max_length=128)
    person_id: str | None = Field(default=None, max_length=128)
    camera_id: str | None = Field(default=None, max_length=128)
    bbox: tuple[float, float, float, float] | None = None
    dataset_split: Literal["train", "query", "gallery"] | None = None
    captured_at: datetime | None = None

    @model_validator(mode="after")
    def content_fields_match_reference(self) -> Sample:
        if self.content_sha256 is not None and self.content_sha256 != self.source_ref.checksum:
            raise ValueError("content_sha256 must match source_ref checksum")
        if self.media_kind is not None and self.media_kind != self.media_type:
            raise ValueError("media_kind must match media_type")
        if self.bbox is not None:
            left, top, width, height = self.bbox
            if width <= 0 or height <= 0 or left < 0 or top < 0:
                raise ValueError("bbox must use non-negative origin and positive width/height")
        return self

    def materialize(self, content_ref: ObjectReference) -> Sample:
        """绑定 Data 自有不可变对象空间中的副本，用于发布不再依赖 Core 对象 key。"""
        if content_ref.checksum != self.source_ref.checksum:
            raise ValueError("materialized content checksum must match the source checksum")
        if content_ref.version is None:
            raise ValueError("materialized content requires a versioned immutable reference")
        return self.model_copy(update={"content_ref": content_ref})



class Annotation(DomainModel):
    annotation_id: str = Field(pattern=BUSINESS_ID)
    sample_id: str = Field(pattern=BUSINESS_ID)
    schema_id: str = Field(min_length=1, max_length=256)
    payload: dict[str, Any]
    status: AnnotationStatus = AnnotationStatus.DRAFT
    created_by: str = Field(min_length=1, max_length=128)
    created_at: datetime
    reviewed_by: str | None = Field(default=None, min_length=1, max_length=128)
    reviewed_at: datetime | None = None
    task_id: str | None = Field(default=None, pattern=BUSINESS_ID)
    current_revision_id: str | None = Field(default=None, pattern=BUSINESS_ID)
    accepted_revision_id: str | None = Field(default=None, pattern=BUSINESS_ID)
    revision_number: int = Field(default=1, ge=1)
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def review_fields_match_status(self) -> Annotation:
        reviewed = self.status in {AnnotationStatus.ACCEPTED, AnnotationStatus.REJECTED}
        if reviewed and (self.reviewed_by is None or self.reviewed_at is None):
            raise ValueError("reviewed annotations require reviewer and reviewed_at")
        if self.status == AnnotationStatus.ACCEPTED and self.accepted_revision_id is None:
            raise ValueError("accepted annotations require accepted_revision_id")
        return self

    def submit_for_review(self) -> Annotation:
        if self.status != AnnotationStatus.DRAFT:
            raise ValueError(f"illegal annotation transition: {self.status} -> in_review")
        return self.model_copy(update={"status": AnnotationStatus.IN_REVIEW})

    def review(self, target: AnnotationStatus, *, reviewer: str, occurred_at: datetime) -> Annotation:
        if self.status != AnnotationStatus.IN_REVIEW or target not in {
            AnnotationStatus.ACCEPTED,
            AnnotationStatus.REJECTED,
        }:
            raise ValueError(f"illegal annotation transition: {self.status} -> {target}")
        changes: dict[str, Any] = {
            "status": target,
            "reviewed_by": reviewer,
            "reviewed_at": occurred_at,
            "updated_at": occurred_at,
        }
        if target == AnnotationStatus.ACCEPTED:
            if self.current_revision_id is None:
                raise ValueError("accepting an annotation requires a current revision")
            changes["accepted_revision_id"] = self.current_revision_id
        return self.model_copy(update=changes)

    def append_revision(self, *, revision_id: str, payload: dict[str, Any], occurred_at: datetime) -> Annotation:
        """追加式修订：已审核的历史修订保留，新修订必须重新进入审核。"""
        return self.model_copy(
            update={
                "payload": payload,
                "status": AnnotationStatus.DRAFT,
                "current_revision_id": revision_id,
                "revision_number": self.revision_number + 1,
                "reviewed_by": None,
                "reviewed_at": None,
                "updated_at": occurred_at,
            }
        )



class DatasetManifest(DomainModel):
    manifest_id: str = Field(pattern=BUSINESS_ID)
    dataset_id: str = Field(pattern=BUSINESS_ID)
    version: str = Field(pattern=SEMVER)
    sample_ids: tuple[str, ...] = Field(min_length=1)
    split_counts: dict[str, int]
    manifest_ref: ObjectReference
    created_at: datetime
    dataset_version_id: str | None = Field(default=None, pattern=BUSINESS_ID)

    @model_validator(mode="after")
    def valid_counts(self) -> DatasetManifest:
        if any(value < 0 for value in self.split_counts.values()):
            raise ValueError("manifest split counts cannot be negative")
        if sum(self.split_counts.values()) != len(self.sample_ids):
            raise ValueError("manifest split counts must equal the number of samples")
        if len(set(self.sample_ids)) != len(self.sample_ids):
            raise ValueError("manifest sample IDs must be unique")
        return self


class DatasetVersion(DomainModel):
    dataset_version_id: str = Field(pattern=BUSINESS_ID)
    dataset_id: str = Field(pattern=BUSINESS_ID)
    version: str = Field(pattern=SEMVER)
    status: DatasetVersionStatus = DatasetVersionStatus.DRAFT
    manifest_ref: ObjectReference | None = None
    created_by: str = Field(min_length=1, max_length=128)
    created_at: datetime
    published_at: datetime | None = None
    archived_at: datetime | None = None
    manifest_sha256: str | None = Field(default=None, pattern=CHECKSUM)
    sample_count: int | None = Field(default=None, ge=1)
    quality_report_id: str | None = Field(default=None, pattern=BUSINESS_ID)
    lineage_snapshot_id: str | None = Field(default=None, pattern=BUSINESS_ID)
    annotation_snapshot_id: str | None = Field(default=None, pattern=BUSINESS_ID)
    failure_reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def published_version_has_manifest(self) -> DatasetVersion:
        published_states = {DatasetVersionStatus.PUBLISHED, DatasetVersionStatus.ARCHIVED}
        if self.status in published_states and (self.manifest_ref is None or self.published_at is None):
            raise ValueError("published dataset versions require an immutable manifest and published_at")
        if self.status in published_states and (self.manifest_sha256 is None or self.sample_count is None):
            raise ValueError("published dataset versions require manifest_sha256 and sample_count")
        if self.manifest_ref is not None and self.manifest_sha256 is not None:
            if self.manifest_ref.checksum != self.manifest_sha256:
                raise ValueError("manifest_sha256 must match manifest_ref checksum")
        if self.status not in published_states and (self.manifest_ref is not None or self.published_at is not None):
            raise ValueError("unpublished dataset versions cannot have a manifest or published_at")
        if (self.status == DatasetVersionStatus.ARCHIVED) != (self.archived_at is not None):
            raise ValueError("only archived dataset versions can have archived_at")
        if self.failure_reason is not None and self.status != DatasetVersionStatus.FAILED:
            raise ValueError("only failed dataset versions can have failure_reason")
        return self

    def transition(
        self,
        target: DatasetVersionStatus,
        *,
        manifest_ref: ObjectReference | None = None,
        occurred_at: datetime | None = None,
        sample_count: int | None = None,
        quality_report_id: str | None = None,
        lineage_snapshot_id: str | None = None,
        annotation_snapshot_id: str | None = None,
        failure_reason: str | None = None,
    ) -> DatasetVersion:
        allowed = {
            DatasetVersionStatus.DRAFT: {DatasetVersionStatus.BUILDING},
            DatasetVersionStatus.BUILDING: {DatasetVersionStatus.READY, DatasetVersionStatus.FAILED},
            DatasetVersionStatus.READY: {DatasetVersionStatus.PUBLISHED, DatasetVersionStatus.FAILED},
            DatasetVersionStatus.PUBLISHED: {DatasetVersionStatus.ARCHIVED},
            DatasetVersionStatus.ARCHIVED: set(),
            DatasetVersionStatus.FAILED: {DatasetVersionStatus.BUILDING},
        }
        if target not in allowed[self.status]:
            raise ValueError(f"illegal dataset version transition: {self.status} -> {target}")
        if target == DatasetVersionStatus.PUBLISHED:
            if manifest_ref is None or occurred_at is None:
                raise ValueError("publishing requires manifest_ref and occurred_at")
            if manifest_ref.version is None:
                raise ValueError("publishing requires a versioned immutable manifest reference")
            if sample_count is None or sample_count < 1:
                raise ValueError("publishing requires a positive sample_count")
            return self.model_copy(
                update={
                    "status": target,
                    "manifest_ref": manifest_ref,
                    "manifest_sha256": manifest_ref.checksum,
                    "sample_count": sample_count,
                    "quality_report_id": quality_report_id or self.quality_report_id,
                    "lineage_snapshot_id": lineage_snapshot_id or self.lineage_snapshot_id,
                    "annotation_snapshot_id": annotation_snapshot_id or self.annotation_snapshot_id,
                    "published_at": occurred_at,
                }
            )
        if target == DatasetVersionStatus.ARCHIVED:
            if occurred_at is None:
                raise ValueError("archiving requires occurred_at")
            return self.model_copy(update={"status": target, "archived_at": occurred_at})
        if target == DatasetVersionStatus.READY:
            return self.model_copy(
                update={
                    "status": target,
                    "quality_report_id": quality_report_id or self.quality_report_id,
                    "failure_reason": None,
                }
            )
        if target == DatasetVersionStatus.FAILED:
            return self.model_copy(
                update={
                    "status": target,
                    "quality_report_id": quality_report_id or self.quality_report_id,
                    "failure_reason": failure_reason or "构建失败",
                }
            )
        return self.model_copy(update={"status": target, "failure_reason": None})



class QualityCheck(DomainModel):
    check_id: str = Field(min_length=1, max_length=128)
    status: QualityStatus
    message: str = Field(min_length=1, max_length=1000)
    measured_value: float | int | str | None = None


class DataQualityReport(DomainModel):
    report_id: str = Field(pattern=BUSINESS_ID)
    dataset_version_id: str = Field(pattern=BUSINESS_ID)
    status: QualityStatus
    checks: tuple[QualityCheck, ...] = Field(min_length=1)
    created_by: str = Field(min_length=1, max_length=128)
    created_at: datetime
    quality_run_id: str | None = Field(default=None, pattern=BUSINESS_ID)
    quality_score: float | None = Field(default=None, ge=0, le=100)
    issue_ids: tuple[str, ...] = Field(default_factory=tuple)


class LineageLink(DomainModel):
    lineage_id: str = Field(pattern=BUSINESS_ID)
    source_entity_type: str = Field(min_length=1, max_length=128)
    source_entity_id: str = Field(pattern=BUSINESS_ID)
    target_entity_type: str = Field(min_length=1, max_length=128)
    target_entity_id: str = Field(pattern=BUSINESS_ID)
    relation: str = Field(min_length=1, max_length=128)
    created_at: datetime

    @model_validator(mode="after")
    def no_self_reference(self) -> LineageLink:
        if self.source_entity_type == self.target_entity_type and self.source_entity_id == self.target_entity_id:
            raise ValueError("lineage links cannot point to the same entity")
        return self


class HardSampleHandoff(DomainModel):
    """Validated Core handoff that can be converted into a Data Sample."""

    handoff_id: str = Field(pattern=BUSINESS_ID)
    source_result_id: str = Field(pattern=BUSINESS_ID)
    source_ref: ObjectReference
    reason: str = Field(min_length=1, max_length=1000)
    approved: bool
    authorized: bool
    deidentified: bool
    occurred_at: datetime
    source_system: str = Field(default="scenara", min_length=1, max_length=128)
    source_resource_type: str | None = Field(default=None, min_length=1, max_length=128)
    media_type: str | None = Field(default=None, min_length=1, max_length=128)
    person_id: str | None = Field(default=None, max_length=128)
    camera_id: str | None = Field(default=None, max_length=128)
    bbox: tuple[float, float, float, float] | None = None
    dataset_split: Literal["train", "query", "gallery"] | None = None
    captured_at: datetime | None = None
    handoff_metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def handoff_is_safe_to_receive(self) -> HardSampleHandoff:
        if not (self.approved and self.authorized and self.deidentified):
            raise ValueError("hard sample handoff must be approved, authorized, and deidentified")
        return self

    @property
    def resolved_media_type(self) -> str:
        return self.media_type or self.source_ref.content_type


class HardSampleManifest(DomainModel):
    """Core 投递的难例清单：整体授权声明加逐条已校验的交接记录。"""

    manifest_id: str = Field(pattern=BUSINESS_ID)
    source_system: str = Field(min_length=1, max_length=128)
    generated_at: datetime
    items: tuple[HardSampleHandoff, ...] = Field(min_length=1, max_length=1000)
    dataset_id: str | None = Field(default=None, pattern=BUSINESS_ID)
    approved: bool = True
    authorized: bool = True
    deidentified: bool = True
    contract_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def manifest_is_safe_to_receive(self) -> HardSampleManifest:
        if not (self.approved and self.authorized and self.deidentified):
            raise ValueError("hard sample manifest must be approved, authorized, and deidentified")
        handoff_ids = [item.handoff_id for item in self.items]
        if len(set(handoff_ids)) != len(handoff_ids):
            raise ValueError("hard sample manifest cannot repeat a handoff_id")
        foreign = sorted({item.source_system for item in self.items if item.source_system != self.source_system})
        if foreign:
            raise ValueError(f"hard sample items must originate from {self.source_system}: {foreign}")
        return self

    def content_checksum(self) -> str:
        if self.contract_sha256 is not None:
            return f"sha256:{self.contract_sha256}"
        payload = json.dumps(self.model_dump(mode="json"), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"



class AuditRecord(DomainModel):
    audit_id: str = Field(pattern=BUSINESS_ID)
    action: str = Field(min_length=1, max_length=256)
    entity_type: str = Field(min_length=1, max_length=128)
    entity_id: str = Field(pattern=BUSINESS_ID)
    organization_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    principal_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    trace_id: str = Field(min_length=1, max_length=128)
    occurred_at: datetime
    result: str = Field(min_length=1, max_length=64)
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


class OutboxEvent(DomainModel):
    event_id: str = Field(pattern=BUSINESS_ID)
    event_type: str = Field(pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
    event_version: str = Field(pattern=r"^\d+\.\d+$")
    occurred_at: datetime
    producer: str = "scenara-data"
    tenant_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    trace_id: str = Field(min_length=1, max_length=128)
    data: dict[str, Any]


class AnnotationProvider(DomainModel):
    provider_id: str = Field(pattern=BUSINESS_ID)
    name: str = Field(min_length=1, max_length=256)
    provider_type: str = Field(min_length=1, max_length=128)
    config_ref: ObjectReference | None = None
    endpoint: str | None = Field(default=None, max_length=2048)
    active: bool = True
    health: str = Field(default="unknown", max_length=64)
    created_at: datetime
    updated_at: datetime | None = None


class AnnotationTask(DomainModel):
    task_id: str = Field(pattern=BUSINESS_ID)
    tenant_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    dataset_id: str = Field(pattern=BUSINESS_ID)
    schema_id: str = Field(min_length=1, max_length=256)
    sample_ids: tuple[str, ...] = Field(min_length=1)
    status: AnnotationTaskStatus = AnnotationTaskStatus.PENDING
    provider_id: str | None = Field(default=None, pattern=BUSINESS_ID)
    assigned_to: str | None = Field(default=None, max_length=128)
    task_metadata: dict[str, Any] = Field(default_factory=dict)
    consistency_score: float | None = Field(default=None, ge=0, le=1)
    review_comment: str = Field(default="", max_length=2000)
    created_by: str = Field(min_length=1, max_length=128)
    created_at: datetime
    updated_at: datetime

    def transition(
        self,
        target: AnnotationTaskStatus,
        *,
        occurred_at: datetime,
        assigned_to: str | None = None,
    ) -> AnnotationTask:
        allowed = {
            AnnotationTaskStatus.PENDING: {AnnotationTaskStatus.ASSIGNED, AnnotationTaskStatus.CANCELLED},
            AnnotationTaskStatus.ASSIGNED: {AnnotationTaskStatus.IN_PROGRESS, AnnotationTaskStatus.CANCELLED},
            AnnotationTaskStatus.IN_PROGRESS: {AnnotationTaskStatus.SUBMITTED, AnnotationTaskStatus.CANCELLED},
            AnnotationTaskStatus.SUBMITTED: {AnnotationTaskStatus.APPROVED, AnnotationTaskStatus.REJECTED},
            AnnotationTaskStatus.REJECTED: {AnnotationTaskStatus.IN_PROGRESS, AnnotationTaskStatus.CANCELLED},
            AnnotationTaskStatus.APPROVED: set(),
            AnnotationTaskStatus.CANCELLED: set(),
        }
        if target not in allowed[self.status]:
            raise ValueError(f"illegal annotation task transition: {self.status} -> {target}")
        if target == AnnotationTaskStatus.ASSIGNED and not assigned_to:
            raise ValueError("assigning an annotation task requires assigned_to")
        return self.model_copy(
            update={
                "status": target,
                "assigned_to": assigned_to or self.assigned_to,
                "updated_at": occurred_at,
            }
        )


class AnnotationRevision(DomainModel):
    """追加式标注修订：已登记的修订不得覆盖或删除。"""

    revision_id: str = Field(pattern=BUSINESS_ID)
    annotation_id: str = Field(pattern=BUSINESS_ID)
    revision_number: int = Field(ge=1)
    payload: dict[str, Any]
    created_by: str = Field(min_length=1, max_length=128)
    created_at: datetime
    task_id: str | None = Field(default=None, pattern=BUSINESS_ID)


class AnnotationAssignment(DomainModel):
    assignment_id: str = Field(pattern=BUSINESS_ID)
    task_id: str = Field(pattern=BUSINESS_ID)
    assignee_principal_id: str = Field(min_length=1, max_length=128)
    assigned_by: str = Field(min_length=1, max_length=128)
    assigned_at: datetime
    provider_id: str | None = Field(default=None, pattern=BUSINESS_ID)
    released_at: datetime | None = None

    @model_validator(mode="after")
    def release_after_assignment(self) -> AnnotationAssignment:
        if self.released_at is not None and self.released_at < self.assigned_at:
            raise ValueError("assignment released_at cannot precede assigned_at")
        return self


class AnnotationSnapshot(DomainModel):
    """Dataset Version 发布时冻结的标注修订集合。"""

    snapshot_id: str = Field(pattern=BUSINESS_ID)
    dataset_version_id: str = Field(pattern=BUSINESS_ID)
    entries: tuple[tuple[str, str], ...] = Field(default_factory=tuple)
    checksum: str = Field(pattern=CHECKSUM)
    created_at: datetime

    @model_validator(mode="after")
    def unique_annotations(self) -> AnnotationSnapshot:
        annotation_ids = [item[0] for item in self.entries]
        if len(set(annotation_ids)) != len(annotation_ids):
            raise ValueError("annotation snapshot cannot freeze the same annotation twice")
        return self



class AnnotationReview(DomainModel):
    review_id: str = Field(pattern=BUSINESS_ID)
    task_id: str = Field(pattern=BUSINESS_ID)
    revision_id: str = Field(pattern=BUSINESS_ID)
    decision: Literal["approved", "rejected"]
    comment: str = Field(default="", max_length=2000)
    consistency_score: float | None = Field(default=None, ge=0, le=1)
    reviewed_by: str = Field(min_length=1, max_length=128)
    reviewed_at: datetime


class QualityRule(DomainModel):
    rule_id: str = Field(pattern=BUSINESS_ID)
    name: str = Field(min_length=1, max_length=256)
    rule_type: str = Field(min_length=1, max_length=128)
    parameters: dict[str, Any] = Field(default_factory=dict)
    active: bool = True


class QualityRun(DomainModel):
    run_id: str = Field(pattern=BUSINESS_ID)
    dataset_version_id: str = Field(pattern=BUSINESS_ID)
    status: JobStatus
    rule_ids: tuple[str, ...] = Field(min_length=1)
    created_by: str = Field(min_length=1, max_length=128)
    created_at: datetime
    completed_at: datetime | None = None
    report_id: str | None = Field(default=None, pattern=BUSINESS_ID)
    error_message: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def terminal_run_is_consistent(self) -> QualityRun:
        terminal = {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}
        if (self.status in terminal) != (self.completed_at is not None):
            raise ValueError("terminal quality runs require completed_at")
        if self.status == JobStatus.SUCCEEDED and self.report_id is None:
            raise ValueError("succeeded quality runs require a report_id")
        return self

    def transition(
        self,
        target: JobStatus,
        *,
        occurred_at: datetime,
        report_id: str | None = None,
        error_message: str | None = None,
    ) -> QualityRun:
        if target not in JOB_TRANSITIONS[self.status]:
            raise ValueError(f"illegal quality run transition: {self.status} -> {target}")
        changes: dict[str, Any] = {"status": target}
        if target in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}:
            changes["completed_at"] = occurred_at
        if report_id is not None:
            changes["report_id"] = report_id
        if error_message is not None:
            changes["error_message"] = error_message
        return self.model_copy(update=changes)



class QualityIssue(DomainModel):
    issue_id: str = Field(pattern=BUSINESS_ID)
    quality_run_id: str = Field(pattern=BUSINESS_ID)
    rule_id: str = Field(pattern=BUSINESS_ID)
    sample_id: str | None = Field(default=None, pattern=BUSINESS_ID)
    severity: Literal["info", "warning", "error"]
    message: str = Field(min_length=1, max_length=1000)


class LineageSnapshot(DomainModel):
    snapshot_id: str = Field(pattern=BUSINESS_ID)
    dataset_version_id: str = Field(pattern=BUSINESS_ID)
    lineage_ids: tuple[str, ...] = Field(min_length=1)
    checksum: str = Field(pattern=CHECKSUM)
    created_at: datetime


class HardSampleImport(DomainModel):
    import_id: str = Field(pattern=BUSINESS_ID)
    manifest_id: str = Field(pattern=BUSINESS_ID)
    manifest_checksum: str = Field(pattern=CHECKSUM)
    status: JobStatus
    accepted_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)
    skipped_count: int = Field(default=0, ge=0)
    sample_ids: tuple[str, ...] = Field(default_factory=tuple)
    annotation_task_ids: tuple[str, ...] = Field(default_factory=tuple)
    created_at: datetime
    completed_at: datetime | None = None
    error_code: str | None = Field(default=None, max_length=128)
    error_message: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def terminal_status_is_consistent(self) -> HardSampleImport:
        terminal = {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}
        if (self.status in terminal) != (self.completed_at is not None):
            raise ValueError("terminal hard sample imports require completed_at")
        if self.status == JobStatus.FAILED and self.error_code is None:
            raise ValueError("failed hard sample imports require an error_code")
        if self.status != JobStatus.FAILED and self.error_code is not None:
            raise ValueError("only failed hard sample imports can carry an error_code")
        if len(self.sample_ids) != self.accepted_count:
            raise ValueError("accepted_count must match the materialized sample count")
        return self



class DatasetAccessGrant(DomainModel):
    grant_id: str = Field(pattern=BUSINESS_ID)
    dataset_version_id: str = Field(pattern=BUSINESS_ID)
    service_account_id: str = Field(min_length=1, max_length=128)
    permissions: tuple[Literal["manifest.read", "objects.read"], ...] = Field(min_length=1)
    expires_at: datetime
    created_by: str = Field(min_length=1, max_length=128)
    created_at: datetime

    @model_validator(mode="after")
    def expires_after_creation(self) -> DatasetAccessGrant:
        if self.expires_at <= self.created_at:
            raise ValueError("access grant expires_at must be after created_at")
        return self


class MigrationReport(DomainModel):
    migration_id: str = Field(pattern=BUSINESS_ID)
    package_checksum: str = Field(pattern=CHECKSUM)
    status: JobStatus
    imported_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    conflict_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    details_ref: ObjectReference | None = None
    created_at: datetime
    completed_at: datetime | None = None
    source_repository: str = Field(default="scenara", min_length=1, max_length=128)
    source_version: str | None = Field(default=None, max_length=64)
    failures: tuple[str, ...] = Field(default_factory=tuple, max_length=200)

    @model_validator(mode="after")
    def terminal_report_is_consistent(self) -> MigrationReport:
        terminal = {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}
        if (self.status in terminal) != (self.completed_at is not None):
            raise ValueError("terminal migration reports require completed_at")
        return self


class MigrationFileEntry(DomainModel):
    """迁移包 `migration-manifest.json` 中单个文件的记录数与摘要。"""

    file: str = Field(min_length=1, max_length=256)
    record_count: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("file")
    @classmethod
    def portable_relative_file(cls, value: str) -> str:
        parts = value.split("/")
        if value.startswith(("/", "\\")) or "\\" in value or ":" in value or any(part in {"", ".", ".."} for part in parts):
            raise ValueError("migration package entries must use portable relative paths")
        return value


class MigrationPackageManifest(DomainModel):
    """指南 13 定义的迁移包清单；Data 只导入 Core 生成的包，不连接 Core 数据库。"""

    schema_version: Literal["1.0"]
    source_repository: str = Field(min_length=1, max_length=128)
    source_version: str = Field(min_length=1, max_length=64)
    generated_at: datetime
    tenant_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    files: tuple[MigrationFileEntry, ...] = Field(min_length=1)
    exporter_version: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def unique_files(self) -> MigrationPackageManifest:
        names = [entry.file for entry in self.files]
        if len(set(names)) != len(names):
            raise ValueError("migration package manifest cannot list the same file twice")
        return self

    def entry(self, name: str) -> MigrationFileEntry | None:
        for candidate in self.files:
            if candidate.file == name:
                return candidate
        return None


# 指南 7：Core 旧状态到 Data 目标状态的显式映射，禁止静默同义状态。
CORE_DATASET_STATUS_MAP: dict[str, DatasetStatus] = {
    "draft": DatasetStatus.DRAFT,
    "active": DatasetStatus.ACTIVE,
    "archived": DatasetStatus.ARCHIVED,
}

CORE_DATASET_VERSION_STATUS_MAP: dict[str, DatasetVersionStatus] = {
    "draft": DatasetVersionStatus.DRAFT,
    "validated": DatasetVersionStatus.READY,
    "ready": DatasetVersionStatus.READY,
    "published": DatasetVersionStatus.PUBLISHED,
    "retired": DatasetVersionStatus.ARCHIVED,
    "archived": DatasetVersionStatus.ARCHIVED,
}
