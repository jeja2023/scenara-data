from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SEMVER = r"^\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?$"
BUSINESS_ID = r"^[a-z][a-z0-9_.-]{1,127}$"
CHECKSUM = r"^sha256:[0-9a-f]{64}$"


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("*", check_fields=False)
    @classmethod
    def timezone_required(cls, value: Any) -> Any:
        if isinstance(value, datetime) and value.tzinfo is None:
            raise ValueError("timestamps must include a timezone")
        return value


class DatasetVersionStatus(StrEnum):
    DRAFT = "draft"
    BUILDING = "building"
    VALIDATED = "validated"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class AnnotationStatus(StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ObjectReference(DomainModel):
    bucket: str = Field(min_length=1, max_length=255)
    key: str = Field(min_length=1, max_length=1024)
    version: str | None = Field(default=None, max_length=256)
    checksum: str = Field(pattern=CHECKSUM)
    size_bytes: int = Field(ge=0)
    content_type: str = Field(min_length=1, max_length=255)

    @field_validator("key")
    @classmethod
    def portable_key(cls, value: str) -> str:
        if value.startswith(("/", "\\")) or ":\\" in value or ".." in value.split("/"):
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


class Sample(DomainModel):
    sample_id: str = Field(pattern=BUSINESS_ID)
    source_ref: ObjectReference
    media_type: str = Field(min_length=1, max_length=128)
    source_lineage: tuple[str, ...] = Field(min_length=1, max_length=100)
    sample_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class Annotation(DomainModel):
    annotation_id: str = Field(pattern=BUSINESS_ID)
    sample_id: str = Field(pattern=BUSINESS_ID)
    schema_id: str = Field(min_length=1, max_length=256)
    payload: dict[str, Any]
    status: AnnotationStatus = AnnotationStatus.DRAFT
    created_by: str = Field(min_length=1, max_length=128)
    created_at: datetime


class DatasetManifest(DomainModel):
    manifest_id: str = Field(pattern=BUSINESS_ID)
    dataset_id: str = Field(pattern=BUSINESS_ID)
    version: str = Field(pattern=SEMVER)
    sample_ids: tuple[str, ...] = Field(min_length=1)
    split_counts: dict[str, int]
    manifest_ref: ObjectReference
    created_at: datetime

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

    @model_validator(mode="after")
    def published_version_has_manifest(self) -> DatasetVersion:
        if self.status == DatasetVersionStatus.PUBLISHED and (self.manifest_ref is None or self.published_at is None):
            raise ValueError("published dataset versions require an immutable manifest and published_at")
        return self

    def transition(
        self,
        target: DatasetVersionStatus,
        *,
        manifest_ref: ObjectReference | None = None,
        occurred_at: datetime | None = None,
    ) -> DatasetVersion:
        allowed = {
            DatasetVersionStatus.DRAFT: {DatasetVersionStatus.BUILDING},
            DatasetVersionStatus.BUILDING: {DatasetVersionStatus.VALIDATED},
            DatasetVersionStatus.VALIDATED: {DatasetVersionStatus.PUBLISHED},
            DatasetVersionStatus.PUBLISHED: {DatasetVersionStatus.ARCHIVED},
            DatasetVersionStatus.ARCHIVED: set(),
        }
        if target not in allowed[self.status]:
            raise ValueError(f"illegal dataset version transition: {self.status} -> {target}")
        if target == DatasetVersionStatus.PUBLISHED:
            if manifest_ref is None or occurred_at is None:
                raise ValueError("publishing requires manifest_ref and occurred_at")
            return self.model_copy(
                update={"status": target, "manifest_ref": manifest_ref, "published_at": occurred_at}
            )
        return self.model_copy(update={"status": target})
