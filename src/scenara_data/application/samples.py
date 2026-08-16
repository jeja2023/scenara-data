"""Sample 领域应用服务（指南 6.3）。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal

from scenara_data.application.errors import ConflictError, InputValidationError, ResourceNotFoundError
from scenara_data.application.support import ApplicationService, Clock, new_id, transactional, utc_now
from scenara_data.domain.models import ObjectReference, Sample
from scenara_data.ports.interfaces import (
    AuditPort,
    ObjectStorageProvider,
    OutboxPort,
    RequestContext,
    SampleRepository,
    UnitOfWork,
)

DatasetSplit = Literal["train", "query", "gallery"]


class SampleService(ApplicationService):
    def __init__(
        self,
        *,
        unit_of_work: UnitOfWork,
        samples: SampleRepository,
        object_storage: ObjectStorageProvider,
        audit: AuditPort,
        outbox: OutboxPort,
        allowed_source_systems: tuple[str, ...] = ("scenara",),
        clock: Clock = utc_now,
    ) -> None:
        super().__init__(unit_of_work=unit_of_work, audit=audit, outbox=outbox, clock=clock)
        self._samples = samples
        self._object_storage = object_storage
        self._allowed_source_systems = allowed_source_systems

    @transactional
    def create_sample(
        self,
        *,
        source_ref: ObjectReference,
        media_type: str,
        source_lineage: tuple[str, ...],
        sample_metadata: dict[str, Any],
        context: RequestContext,
        sample_id: str | None = None,
        source_system: str | None = None,
        source_resource_type: str | None = None,
        source_resource_id: str | None = None,
        person_id: str | None = None,
        camera_id: str | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        dataset_split: DatasetSplit | None = None,
        captured_at: datetime | None = None,
    ) -> Sample:
        self._require(context, "data.sample.create")
        resolved_source_system = source_system or self._allowed_source_systems[0]
        if resolved_source_system not in self._allowed_source_systems:
            raise InputValidationError(
                "样本来源系统未被允许",
                details={"source_system": resolved_source_system, "allowed": list(self._allowed_source_systems)},
            )
        metadata = dict(sample_metadata)
        resolved_split = dataset_split or _metadata_split(metadata)
        value = Sample(
            sample_id=sample_id or new_id("smp"),
            tenant_id=context.organization_id,
            project_id=context.project_id,
            source_ref=source_ref,
            media_type=media_type,
            source_lineage=source_lineage,
            sample_metadata=metadata,
            created_at=self._clock(),
            media_kind=media_type,
            content_sha256=source_ref.checksum,
            source_system=resolved_source_system,
            source_resource_type=source_resource_type,
            source_resource_id=source_resource_id,
            person_id=person_id,
            camera_id=camera_id,
            bbox=bbox,
            dataset_split=resolved_split,
            captured_at=captured_at,
        )
        try:
            self._samples.add_sample(value, context.principal_id)
        except ValueError as exc:
            raise ConflictError("样本标识已存在", details={"sample_id": value.sample_id}) from exc
        return value

    def get_sample(self, sample_id: str, context: RequestContext) -> Sample:
        self._require(context, "data.sample.read")
        return self.require_sample(sample_id, context)

    def list_samples(
        self,
        context: RequestContext,
        *,
        limit: int,
        offset: int,
        dataset_split: str | None = None,
    ) -> tuple[list[Sample], int]:
        self._require(context, "data.sample.read")
        return self._samples.list_samples(
            context.organization_id,
            context.project_id,
            limit=limit,
            offset=offset,
            dataset_split=dataset_split,
        )

    def require_sample(self, sample_id: str, context: RequestContext) -> Sample:
        try:
            return self._samples.get_sample(sample_id, context.organization_id, context.project_id)
        except KeyError as exc:
            raise ResourceNotFoundError("sample", sample_id) from exc

    def verify_sample_content(self, samples: Sequence[Sample]) -> tuple[str, ...]:
        """按对象引用重新校验内容摘要，返回失败的 sample_id（规范 32）。"""
        failures: list[str] = []
        for sample in samples:
            reference = sample.content_ref or sample.source_ref
            try:
                self._object_storage.read_verified(reference)
            except (FileNotFoundError, ValueError):
                failures.append(sample.sample_id)
        return tuple(failures)


def _metadata_split(metadata: dict[str, Any]) -> DatasetSplit | None:
    value = metadata.get("dataset_split")
    if value in {"train", "query", "gallery"}:
        return value  # type: ignore[return-value]
    if value is None:
        return None
    raise InputValidationError(
        "dataset_split 只能是 train、query 或 gallery",
        details={"dataset_split": value},
    )
