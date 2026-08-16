"""API 契约模型：请求、响应、分页与错误信封。

所有跨仓库结构以 `scenara-contracts` 已发布版本为准；此处只做本仓库的请求校验与响应组装。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from scenara_data import contracts
from scenara_data.domain.models import (
    Annotation,
    AnnotationAssignment,
    AnnotationProvider,
    AnnotationReview,
    AnnotationRevision,
    AnnotationSnapshot,
    AnnotationStatus,
    AnnotationTask,
    AnnotationTaskStatus,
    DataQualityReport,
    Dataset,
    DatasetAccessGrant,
    DatasetManifest,
    DatasetStatus,
    DatasetVersion,
    DatasetVersionStatus,
    HardSampleImport,
    LineageLink,
    LineageSnapshot,
    ObjectReference,
    QualityIssue,
    QualityRule,
    QualityRun,
    Sample,
)

DatasetSplit = Literal["train", "query", "gallery"]
GrantPermission = Literal["manifest.read", "objects.read"]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Page[T](ApiModel):
    items: list[T]
    total: int = Field(ge=0)
    next_cursor: str | None = None


# ---------------------------------------------------------------------- Dataset


class CreateDatasetRequest(ApiModel):
    dataset_id: str | None = None
    name: str = Field(min_length=1, max_length=256)
    description: str = Field(default="", max_length=2000)
    labels: tuple[str, ...] = Field(default=(), max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PatchDatasetRequest(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=2000)
    status: DatasetStatus | None = None
    labels: tuple[str, ...] | None = Field(default=None, max_length=100)
    metadata: dict[str, Any] | None = None


class CreateDatasetVersionRequest(ApiModel):
    dataset_version_id: str | None = None
    version: str


class TransitionDatasetVersionRequest(ApiModel):
    status: DatasetVersionStatus
    reason: str | None = Field(default=None, max_length=1000)
    rule_ids: tuple[str, ...] = Field(default=(), max_length=50)


class AddSampleRequest(ApiModel):
    sample_id: str


class ValidateDatasetVersionRequest(ApiModel):
    rule_ids: tuple[str, ...] = Field(default=(), max_length=50)


class CreateAccessGrantRequest(ApiModel):
    service_account_id: str = Field(min_length=1, max_length=128)
    permissions: tuple[GrantPermission, ...] = Field(min_length=1)
    ttl_seconds: int = Field(gt=0, le=86400)


class AccessGrantResponse(ApiModel):
    grant: DatasetAccessGrant
    manifest_url: str | None = None


class ValidationResponse(ApiModel):
    dataset_version: DatasetVersion
    quality_report: DataQualityReport


class PublicationResponse(ApiModel):
    dataset_version: DatasetVersion
    manifest: DatasetManifest


class DatasetVersionReference(ApiModel):
    """`@scenara/repository-contracts` 1.0.0 `dataset-version-input`."""

    schema_version: Literal["1.0"] = contracts.DATASET_VERSION_INPUT_SCHEMA_VERSION  # type: ignore[assignment]
    dataset_id: str
    version: str
    manifest_uri: str = Field(min_length=1, max_length=2048)
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    lineage_refs: tuple[str, ...] = Field(min_length=1, max_length=100)
    authorization_id: str = Field(min_length=1, max_length=256)
    authorized_consumer_repository_ids: tuple[str, ...] = Field(min_length=1, max_length=32)
    created_at: float

    @model_validator(mode="after")
    def immutable_references_match_digest(self) -> DatasetVersionReference:
        suffix = f"#sha256={self.manifest_sha256}"
        alternate = f"@sha256:{self.manifest_sha256}"
        if not self.manifest_uri.endswith((suffix, alternate)):
            raise ValueError("manifest_uri digest must match manifest_sha256")
        if any("#sha256=" not in item and "@sha256:" not in item for item in self.lineage_refs):
            raise ValueError("lineage_refs must be immutable digest references")
        return self


# ----------------------------------------------------------------------- Sample


class CreateSampleRequest(ApiModel):
    sample_id: str | None = None
    source_ref: ObjectReference
    media_type: str = Field(min_length=1, max_length=128)
    source_lineage: tuple[str, ...] = Field(min_length=1, max_length=100)
    sample_metadata: dict[str, Any] = Field(default_factory=dict)
    source_system: str | None = Field(default=None, min_length=1, max_length=128)
    source_resource_type: str | None = Field(default=None, min_length=1, max_length=128)
    source_resource_id: str | None = Field(default=None, min_length=1, max_length=128)
    person_id: str | None = Field(default=None, max_length=128)
    camera_id: str | None = Field(default=None, max_length=128)
    bbox: tuple[float, float, float, float] | None = None
    dataset_split: DatasetSplit | None = None
    captured_at: datetime | None = None


# ------------------------------------------------------------------- Annotation


class CreateAnnotationRequest(ApiModel):
    annotation_id: str | None = None
    sample_id: str
    schema_id: str = Field(min_length=1, max_length=256)
    payload: dict[str, Any]
    task_id: str | None = None


class AppendRevisionRequest(ApiModel):
    payload: dict[str, Any]


class ReviewAnnotationRequest(ApiModel):
    status: Literal[AnnotationStatus.ACCEPTED, AnnotationStatus.REJECTED]


class RevisionResponse(ApiModel):
    annotation: Annotation
    revision: AnnotationRevision


class CreateAnnotationTaskRequest(ApiModel):
    task_id: str | None = None
    dataset_id: str
    schema_id: str = Field(min_length=1, max_length=256)
    sample_ids: tuple[str, ...] = Field(min_length=1, max_length=1000)
    provider_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TransitionAnnotationTaskRequest(ApiModel):
    status: AnnotationTaskStatus
    assignee_principal_id: str | None = Field(default=None, min_length=1, max_length=128)


class ReviewAnnotationTaskRequest(ApiModel):
    decision: Literal["approved", "rejected"]
    comment: str = Field(default="", max_length=2000)
    revision_id: str | None = None
    consistency_score: float | None = Field(default=None, ge=0, le=1)


class AnnotationTaskReviewResponse(ApiModel):
    task: AnnotationTask
    review: AnnotationReview


class CreateAnnotationProviderRequest(ApiModel):
    provider_id: str | None = None
    name: str = Field(min_length=1, max_length=256)
    provider_type: str = Field(min_length=1, max_length=128)
    config_ref: ObjectReference | None = None
    endpoint: str | None = Field(default=None, max_length=2048)


# -------------------------------------------------------------------- Quality


class CreateQualityRuleRequest(ApiModel):
    rule_id: str | None = None
    name: str = Field(min_length=1, max_length=256)
    rule_type: Literal[
        "sample_count_min",
        "content_checksum",
        "unique_content",
        "split_present",
        "annotation_coverage",
        "reid_fields_required",
    ]
    parameters: dict[str, Any] = Field(default_factory=dict)


class CreateQualityRunRequest(ApiModel):
    dataset_version_id: str
    rule_ids: tuple[str, ...] = Field(default=(), max_length=50)


class QualityRunResponse(ApiModel):
    quality_run: QualityRun
    quality_report: DataQualityReport


# ---------------------------------------------------------------- Hard Sample


class HardSampleContractItem(ApiModel):
    feedback_id: str
    kind: Literal[
        "false_positive",
        "false_negative",
        "wrong_attribute",
        "wrong_identity",
        "ocr_correction",
    ]
    media_ref: str
    result_ref: str
    model_id: str
    model_version: str
    pipeline_id: str
    pipeline_version: str
    correction: dict[str, Any]
    authorized_for_training: bool = True
    deidentified: bool = True


class HardSampleContractManifest(ApiModel):
    """Published `hard-sample-handoff` 1.0.0 payload, without local extensions."""

    schema_version: Literal["1.0"] = contracts.HARD_SAMPLE_MANIFEST_SCHEMA_VERSION  # type: ignore[assignment]
    manifest_id: str
    tenant_id: str
    project_id: str
    dataset_id: str
    version: str
    label_schema: str = "scenara.feedback.correction.v1"
    split: Literal["train", "validation", "test"] = "train"
    items: tuple[HardSampleContractItem, ...] = Field(min_length=1, max_length=10_000)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_by: str
    created_at: float

    def calculated_sha256(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "dataset_id": self.dataset_id,
            "version": self.version,
            "label_schema": self.label_schema,
            "split": self.split,
            "items": [item.model_dump(mode="json") for item in self.items],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @model_validator(mode="after")
    def validate_handoff(self) -> HardSampleContractManifest:
        if self.sha256 != self.calculated_sha256():
            raise ValueError("hard-sample manifest checksum does not match canonical content")
        if any(not item.authorized_for_training or not item.deidentified for item in self.items):
            raise ValueError("hard-sample items must be authorized and deidentified")
        return self


class HardSampleSource(ApiModel):
    """Transport metadata used to materialize a contract item into Data-owned storage."""

    feedback_id: str
    source_ref: ObjectReference
    occurred_at: datetime
    source_result_id: str | None = None
    source_resource_type: str = "media_asset"
    media_type: str | None = None
    person_id: str | None = None
    camera_id: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    dataset_split: DatasetSplit | None = None
    captured_at: datetime | None = None


class HardSampleIntakeRequest(ApiModel):
    """Core 投递的难例清单（`hard-sample-handoff` 契约 1.0）。

    `manifest` 是契约本体，其余字段是 Data 侧的承接选项，不参与清单内容摘要。
    """

    schema_version: Literal["1.0"] = contracts.HARD_SAMPLE_MANIFEST_SCHEMA_VERSION  # type: ignore[assignment]
    manifest: HardSampleContractManifest
    sources: tuple[HardSampleSource, ...] = Field(min_length=1, max_length=10_000)
    annotation_schema_id: str | None = Field(default=None, min_length=1, max_length=256)
    build_version: str | None = Field(default=None, min_length=1, max_length=64)
    publish: bool = False

    @model_validator(mode="after")
    def sources_match_manifest(self) -> HardSampleIntakeRequest:
        feedback_ids = [item.feedback_id for item in self.manifest.items]
        source_ids = [item.feedback_id for item in self.sources]
        if len(set(feedback_ids)) != len(feedback_ids):
            raise ValueError("hard-sample manifest feedback_id values must be unique")
        if len(set(source_ids)) != len(source_ids) or set(source_ids) != set(feedback_ids):
            raise ValueError("hard-sample sources must match manifest items one-to-one")
        return self


class HardSampleIntakeResponse(ApiModel):
    import_id: str
    manifest_id: str
    status: str
    accepted_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    sample_ids: list[str]
    annotation_task_ids: list[str]
    dataset_version_id: str | None = None
    replayed: bool = False


# --------------------------------------------------------------------- 错误


class ErrorBody(ApiModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(ApiModel):
    schema_version: Literal["1.0"] = contracts.ERROR_ENVELOPE_VERSION  # type: ignore[assignment]
    request_id: str
    error: ErrorBody
    occurred_at: datetime | None = None


DatasetPage = Page[Dataset]
DatasetVersionPage = Page[DatasetVersion]
SamplePage = Page[Sample]
AnnotationPage = Page[Annotation]
AnnotationRevisionPage = Page[AnnotationRevision]
AnnotationTaskPage = Page[AnnotationTask]
AnnotationAssignmentPage = Page[AnnotationAssignment]
AnnotationReviewPage = Page[AnnotationReview]
AnnotationProviderPage = Page[AnnotationProvider]
QualityRulePage = Page[QualityRule]
QualityRunPage = Page[QualityRun]
QualityIssuePage = Page[QualityIssue]
LineagePage = Page[LineageLink]
AccessGrantPage = Page[DatasetAccessGrant]
HardSampleImportModel = HardSampleImport
AnnotationSnapshotModel = AnnotationSnapshot
LineageSnapshotModel = LineageSnapshot
