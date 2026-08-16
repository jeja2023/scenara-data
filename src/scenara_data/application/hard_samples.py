"""Hard Sample 承接（指南 11.1、14、M6）。

Data 不重新决定反馈是否批准。Manifest 未批准、未授权、未脱敏或摘要错误时整体拒绝，
只有全部条目校验通过才物化样本、标注任务和可选新版本。
"""

from __future__ import annotations

from dataclasses import dataclass

from scenara_data.application.annotations import AnnotationService
from scenara_data.application.builder import DatasetBuilderService
from scenara_data.application.errors import ConflictError, InputValidationError, ResourceNotFoundError
from scenara_data.application.samples import SampleService
from scenara_data.application.support import ApplicationService, Clock, new_id, transactional, utc_now
from scenara_data.domain.models import (
    HardSampleImport,
    HardSampleManifest,
    JobStatus,
    Sample,
)
from scenara_data.ports.interfaces import (
    AuditPort,
    HardSampleRepository,
    ObjectStorageProvider,
    OutboxPort,
    RequestContext,
    UnitOfWork,
)

REJECT_CHECKSUM = "HARD_SAMPLE_CHECKSUM_MISMATCH"
REJECT_SOURCE = "HARD_SAMPLE_SOURCE_NOT_ALLOWED"


@dataclass(frozen=True, slots=True)
class IntakeResult:
    hard_sample_import: HardSampleImport
    samples: tuple[Sample, ...]
    dataset_version_id: str | None
    replayed: bool


class HardSampleService(ApplicationService):
    def __init__(
        self,
        *,
        unit_of_work: UnitOfWork,
        hard_samples: HardSampleRepository,
        samples: SampleService,
        annotations: AnnotationService,
        builder: DatasetBuilderService,
        object_storage: ObjectStorageProvider,
        audit: AuditPort,
        outbox: OutboxPort,
        allowed_source_systems: tuple[str, ...] = ("scenara",),
        clock: Clock = utc_now,
    ) -> None:
        super().__init__(unit_of_work=unit_of_work, audit=audit, outbox=outbox, clock=clock)
        self._hard_samples = hard_samples
        self._samples = samples
        self._annotations = annotations
        self._builder = builder
        self._object_storage = object_storage
        self._allowed_source_systems = allowed_source_systems

    def ingest_manifest(
        self,
        manifest: HardSampleManifest,
        context: RequestContext,
        *,
        annotation_schema_id: str | None = None,
        build_version: str | None = None,
        publish: bool = False,
    ) -> IntakeResult:
        self._require(context, "data.hard_sample.import")
        existing = self._hard_samples.find_hard_sample_import_by_manifest(
            manifest.manifest_id, context.organization_id, context.project_id
        )
        if existing is not None:
            if existing.manifest_checksum != manifest.content_checksum():
                raise ConflictError(
                    "同一难例清单标识已用于不同内容",
                    details={"manifest_id": manifest.manifest_id, "import_id": existing.import_id},
                )
            return IntakeResult(
                hard_sample_import=existing, samples=(), dataset_version_id=None, replayed=True
            )
        record = self._open_import(manifest, context)
        rejections = self._reject_reasons(manifest)
        if rejections:
            self._close_failed(record, context, rejections=rejections)
            raise InputValidationError(
                "难例清单整体拒绝",
                details={
                    "import_id": record.import_id,
                    "manifest_id": manifest.manifest_id,
                    "rejected_count": len(rejections),
                    "rejections": [
                        {"handoff_id": handoff_id, "code": code} for handoff_id, code in rejections
                    ],
                },
            )
        return self._accept(
            record,
            manifest,
            context,
            annotation_schema_id=annotation_schema_id,
            build_version=build_version,
            publish=publish,
        )

    def get_import(self, import_id: str, context: RequestContext) -> HardSampleImport:
        self._require(context, "data.dataset.read")
        try:
            return self._hard_samples.get_hard_sample_import(
                import_id, context.organization_id, context.project_id
            )
        except KeyError as exc:
            raise ResourceNotFoundError("hard_sample_import", import_id) from exc

    # ------------------------------------------------------------------ 内部

    @transactional
    def _open_import(self, manifest: HardSampleManifest, context: RequestContext) -> HardSampleImport:
        record = HardSampleImport(
            import_id=new_id("hsi"),
            manifest_id=manifest.manifest_id,
            manifest_checksum=manifest.content_checksum(),
            status=JobStatus.QUEUED,
            created_at=self._clock(),
        )
        try:
            self._hard_samples.add_hard_sample_import(
                record, context.organization_id, context.project_id
            )
        except ValueError as exc:
            raise ConflictError(
                "难例清单已在处理中", details={"manifest_id": manifest.manifest_id}
            ) from exc
        return record

    @transactional
    def _close_failed(
        self,
        record: HardSampleImport,
        context: RequestContext,
        *,
        rejections: tuple[tuple[str, str], ...],
    ) -> HardSampleImport:
        occurred_at = self._clock()
        codes = sorted({code for _, code in rejections})
        failed = record.model_copy(
            update={
                "status": JobStatus.FAILED,
                "rejected_count": len(rejections),
                "completed_at": occurred_at,
                "error_code": codes[0],
                "error_message": f"整体拒绝 {len(rejections)} 条难例：{codes}",
            }
        )
        self._hard_samples.update_hard_sample_import(
            failed, context.organization_id, context.project_id
        )
        self._record_audit(
            "hard_sample.import.reject",
            "hard_sample_import",
            record.import_id,
            context,
            before=record,
            after=failed,
            result="rejected",
        )
        self._emit(
            "hard_sample.import.failed",
            context,
            occurred_at,
            {
                "import_id": failed.import_id,
                "manifest_id": failed.manifest_id,
                "rejected_count": failed.rejected_count,
                "error_code": failed.error_code,
            },
        )
        return failed

    @transactional
    def _accept(
        self,
        record: HardSampleImport,
        manifest: HardSampleManifest,
        context: RequestContext,
        *,
        annotation_schema_id: str | None,
        build_version: str | None,
        publish: bool,
    ) -> IntakeResult:
        occurred_at = self._clock()
        created: list[Sample] = []
        for handoff in manifest.items:
            created.append(
                self._samples.create_sample(
                    source_ref=handoff.source_ref,
                    media_type=handoff.resolved_media_type,
                    source_lineage=(manifest.manifest_id, handoff.handoff_id, handoff.source_result_id),
                    sample_metadata={
                        "hard_sample_reason": handoff.reason,
                        "hard_sample_manifest_id": manifest.manifest_id,
                        **handoff.handoff_metadata,
                    },
                    context=context,
                    source_system=handoff.source_system,
                    source_resource_type=handoff.source_resource_type or "result",
                    source_resource_id=handoff.source_result_id,
                    person_id=handoff.person_id,
                    camera_id=handoff.camera_id,
                    bbox=handoff.bbox,
                    dataset_split=handoff.dataset_split,
                    captured_at=handoff.captured_at,
                )
            )

        task_ids: list[str] = []
        if manifest.dataset_id is not None and annotation_schema_id is not None:
            task = self._annotations.create_task(
                dataset_id=manifest.dataset_id,
                schema_id=annotation_schema_id,
                sample_ids=tuple(sample.sample_id for sample in created),
                context=context,
            )
            task_ids.append(task.task_id)

        dataset_version_id: str | None = None
        if build_version is not None:
            if manifest.dataset_id is None:
                raise InputValidationError("构建新版本需要难例清单声明 dataset_id")
            result = self._builder.build_version(
                dataset_id=manifest.dataset_id,
                version=build_version,
                sample_ids=[sample.sample_id for sample in created],
                context=context,
                publish=publish,
            )
            dataset_version_id = result.dataset_version.dataset_version_id

        completed = record.model_copy(
            update={
                "status": JobStatus.SUCCEEDED,
                "accepted_count": len(created),
                "sample_ids": tuple(sample.sample_id for sample in created),
                "annotation_task_ids": tuple(task_ids),
                "completed_at": occurred_at,
            }
        )
        self._hard_samples.update_hard_sample_import(
            completed, context.organization_id, context.project_id
        )
        self._record_audit(
            "hard_sample.import",
            "hard_sample_import",
            record.import_id,
            context,
            before=record,
            after=completed,
        )
        self._emit(
            "hard_sample.imported",
            context,
            occurred_at,
            {
                "import_id": completed.import_id,
                "manifest_id": manifest.manifest_id,
                "accepted_count": completed.accepted_count,
                "rejected_count": completed.rejected_count,
                "sample_ids": list(completed.sample_ids),
                "annotation_task_ids": list(completed.annotation_task_ids),
                "dataset_version_id": dataset_version_id,
            },
        )
        return IntakeResult(
            hard_sample_import=completed,
            samples=tuple(created),
            dataset_version_id=dataset_version_id,
            replayed=False,
        )

    def _reject_reasons(self, manifest: HardSampleManifest) -> tuple[tuple[str, str], ...]:
        """在物化前完成来源与摘要校验，任一条失败即整体拒绝。"""
        rejections: list[tuple[str, str]] = []
        for handoff in manifest.items:
            if handoff.source_system not in self._allowed_source_systems:
                rejections.append((handoff.handoff_id, REJECT_SOURCE))
                continue
            try:
                self._object_storage.read_verified(handoff.source_ref)
            except (FileNotFoundError, ValueError):
                rejections.append((handoff.handoff_id, REJECT_CHECKSUM))
        return tuple(rejections)
