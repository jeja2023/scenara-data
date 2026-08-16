"""Core 迁移包导入器（指南 13、M3；任务清单第 8 项）。

导入流程严格按指南 13 执行：验证包与文件摘要 -> 校验 tenant/project 范围 -> 保留原始
Dataset/Version ID -> 幂等处理重复导入 -> 输出成功/跳过/冲突/失败统计 -> 对已发布版本
重新计算 Manifest 摘要 -> 生成可归档迁移报告。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from scenara_data.application.errors import ConflictError, InputValidationError, ResourceNotFoundError
from scenara_data.application.support import ApplicationService, Clock, new_id, transactional, utc_now
from scenara_data.domain.models import (
    AnnotationProvider,
    AnnotationTask,
    AnnotationTaskStatus,
    Dataset,
    DatasetVersion,
    DatasetVersionStatus,
    JobStatus,
    MigrationPackageManifest,
    MigrationReport,
    ObjectReference,
    Sample,
)
from scenara_data.domain.services import (
    canonical_json,
    map_core_dataset_status,
    map_core_dataset_version_status,
)
from scenara_data.ports.interfaces import (
    AnnotationRepository,
    AuditPort,
    DatasetRepository,
    MigrationPackageSource,
    MigrationRepository,
    ObjectStorageProvider,
    OutboxPort,
    RequestContext,
    SampleRepository,
    UnitOfWork,
)

MANIFEST_FILE = "migration-manifest.json"
CHECKSUMS_FILE = "checksums.txt"
DATASETS_FILE = "datasets.jsonl"
DATASET_VERSIONS_FILE = "dataset-versions.jsonl"
SAMPLES_FILE = "samples.jsonl"
ANNOTATION_PROVIDERS_FILE = "annotation-providers.jsonl"
ANNOTATION_TASKS_FILE = "annotation-tasks.jsonl"
HARD_SAMPLE_MANIFESTS_FILE = "hard-sample-manifests.jsonl"
OBJECT_REFERENCES_FILE = "object-references.jsonl"
AUDIT_REFERENCES_FILE = "audit-references.jsonl"

DATA_FILES = (
    DATASETS_FILE,
    SAMPLES_FILE,
    DATASET_VERSIONS_FILE,
    ANNOTATION_PROVIDERS_FILE,
    ANNOTATION_TASKS_FILE,
    HARD_SAMPLE_MANIFESTS_FILE,
    OBJECT_REFERENCES_FILE,
    AUDIT_REFERENCES_FILE,
)

MAX_RECORDED_FAILURES = 200


class PackageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MigrationDatasetRecord(PackageRecord):
    dataset_id: str
    name: str
    description: str = ""
    status: str
    created_by: str
    created_at: datetime
    owner_principal_id: str | None = None
    labels: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime | None = None
    archived_at: datetime | None = None


class MigrationDatasetVersionRecord(PackageRecord):
    version_id: str
    dataset_id: str
    version: str
    status: str
    created_by: str
    created_at: datetime
    manifest_ref: ObjectReference | None = None
    manifest_file: str | None = None
    source_manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    sample_ids: tuple[str, ...] = ()
    sample_count: int | None = None
    published_at: datetime | None = None
    archived_at: datetime | None = None
    quality_report_id: str | None = None
    lineage_snapshot_id: str | None = None


class MigrationAnnotationProviderRecord(PackageRecord):
    provider_id: str
    name: str
    provider_type: str
    active: bool = True
    endpoint: str | None = None
    health: str = "unknown"
    created_at: datetime
    updated_at: datetime | None = None


class MigrationAnnotationTaskRecord(PackageRecord):
    task_id: str
    dataset_id: str
    schema_id: str
    sample_ids: tuple[str, ...]
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    provider_id: str | None = None
    assigned_to: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    consistency_score: float | None = Field(default=None, ge=0, le=1)
    review_comment: str = ""


class MigrationSampleRecord(PackageRecord):
    sample_id: str
    source_ref: ObjectReference
    media_type: str
    source_lineage: tuple[str, ...]
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_system: str = "scenara"
    source_resource_type: str | None = None
    source_resource_id: str | None = None
    created_by: str
    created_at: datetime


class MigrationObjectReferenceRecord(PackageRecord):
    entity_type: str
    entity_id: str
    reference: ObjectReference


class MigrationAuditReferenceRecord(PackageRecord):
    audit_id: str
    action: str
    entity_type: str
    entity_id: str
    occurred_at: datetime


class MigrationHardSampleRecord(PackageRecord):
    manifest_id: str
    source_result_ids: tuple[str, ...] = ()
    generated_at: datetime


@dataclass(slots=True)
class ImportTally:
    imported: int = 0
    skipped: int = 0
    conflicts: int = 0
    failed: int = 0
    failures: list[str] = field(default_factory=list)

    def fail(self, message: str) -> None:
        self.failed += 1
        if len(self.failures) < MAX_RECORDED_FAILURES:
            self.failures.append(message)

    def conflict(self, message: str) -> None:
        self.conflicts += 1
        if len(self.failures) < MAX_RECORDED_FAILURES:
            self.failures.append(message)

    def merge(self, other: ImportTally) -> None:
        self.imported += other.imported
        self.skipped += other.skipped
        self.conflicts += other.conflicts
        self.failed += other.failed
        for message in other.failures:
            if len(self.failures) < MAX_RECORDED_FAILURES:
                self.failures.append(message)


class MigrationImportService(ApplicationService):
    def __init__(
        self,
        *,
        unit_of_work: UnitOfWork,
        datasets: DatasetRepository,
        samples: SampleRepository,
        annotations: AnnotationRepository,
        migrations: MigrationRepository,
        object_storage: ObjectStorageProvider,
        audit: AuditPort,
        outbox: OutboxPort,
        import_bucket: str,
        clock: Clock = utc_now,
    ) -> None:
        super().__init__(unit_of_work=unit_of_work, audit=audit, outbox=outbox, clock=clock)
        self._datasets = datasets
        self._samples = samples
        self._annotations = annotations
        self._migrations = migrations
        self._object_storage = object_storage
        self._import_bucket = import_bucket

    def import_package(
        self,
        package: MigrationPackageSource,
        context: RequestContext,
        *,
        dry_run: bool = False,
    ) -> MigrationReport:
        self._require(context, "data.import.execute")
        manifest = self._load_manifest(package)
        self._verify_scope(manifest, context)
        package_checksum = self._verify_checksums(package, manifest)

        previous = self._migrations.find_migration_report_by_checksum(
            package_checksum, context.organization_id, context.project_id
        )
        if previous is not None:
            if previous.status == JobStatus.RUNNING:
                raise ConflictError(
                    "同一迁移包正在导入中", details={"migration_id": previous.migration_id}
                )
            # 相同内容的重复投递始终复用已有终态报告，避免重复写入或唯一约束泄漏。
            return previous

        report = self._open_report(manifest, package_checksum, context)
        tally = ImportTally()
        try:
            tally.merge(self._import_datasets(package, manifest, context, dry_run=dry_run))
            tally.merge(self._import_samples(package, manifest, context, dry_run=dry_run))
            tally.merge(self._import_dataset_versions(package, manifest, context, dry_run=dry_run))
            tally.merge(self._import_annotation_providers(package, manifest, context, dry_run=dry_run))
            tally.merge(self._import_annotation_tasks(package, manifest, context, dry_run=dry_run))
            tally.merge(self._verify_object_references(package, manifest))
            tally.merge(
                self._count_reference_only(package, manifest, HARD_SAMPLE_MANIFESTS_FILE, MigrationHardSampleRecord)
            )
            tally.merge(
                self._count_reference_only(package, manifest, AUDIT_REFERENCES_FILE, MigrationAuditReferenceRecord)
            )
        except InputValidationError as exc:
            # 包摘要和作用域已经验证完毕；后续记录格式错误应写入失败报告，供迁移方定位修复。
            tally.fail(f"migration package validation failed: {exc.message}")
        return self._close_report(report, tally, manifest, context, dry_run=dry_run)

    def get_report(self, migration_id: str, context: RequestContext) -> MigrationReport:
        self._require(context, "data.dataset.read")
        try:
            return self._migrations.get_migration_report(
                migration_id, context.organization_id, context.project_id
            )
        except KeyError as exc:
            raise ResourceNotFoundError("migration_report", migration_id) from exc

    # ------------------------------------------------------- 包校验与报告

    def _load_manifest(self, package: MigrationPackageSource) -> MigrationPackageManifest:
        if not package.exists(MANIFEST_FILE):
            raise InputValidationError("迁移包缺少 migration-manifest.json")
        try:
            payload = json.loads(package.read(MANIFEST_FILE).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InputValidationError("migration-manifest.json 不是合法 UTF-8 JSON") from exc
        try:
            return MigrationPackageManifest.model_validate(payload)
        except Exception as exc:  # pydantic ValidationError
            raise InputValidationError(
                "migration-manifest.json 不符合迁移包契约", details={"reason": str(exc)[:500]}
            ) from exc

    def _verify_scope(self, manifest: MigrationPackageManifest, context: RequestContext) -> None:
        if manifest.tenant_id != context.organization_id or manifest.project_id != context.project_id:
            raise InputValidationError(
                "迁移包 tenant/project 范围与请求上下文不一致",
                details={
                    "package_tenant_id": manifest.tenant_id,
                    "package_project_id": manifest.project_id,
                },
            )

    def _verify_checksums(self, package: MigrationPackageSource, manifest: MigrationPackageManifest) -> str:
        declared = self._parse_checksums(package)
        digests: dict[str, str] = {}
        for entry in manifest.files:
            if not package.exists(entry.file):
                raise InputValidationError(
                    "迁移包缺少清单声明的文件", details={"file": entry.file}
                )
            actual = hashlib.sha256(package.read(entry.file)).hexdigest()
            if actual != entry.sha256:
                raise InputValidationError(
                    "迁移包文件摘要与清单不一致",
                    details={"file": entry.file, "expected": entry.sha256, "actual": actual},
                )
            if entry.file in declared and declared[entry.file] != actual:
                raise InputValidationError(
                    "checksums.txt 与实际文件摘要不一致", details={"file": entry.file}
                )
            actual_count = sum(1 for _ in self._iter_lines(package, entry.file))
            if actual_count != entry.record_count:
                raise InputValidationError(
                    "迁移包文件记录数与清单不一致",
                    details={
                        "file": entry.file,
                        "expected": entry.record_count,
                        "actual": actual_count,
                    },
                )
            digests[entry.file] = actual
        undeclared = sorted(set(declared) - set(digests))
        if undeclared:
            raise InputValidationError(
                "checksums.txt 声明了清单之外的文件", details={"files": undeclared}
            )
        fingerprint = {
            "manifest": hashlib.sha256(package.read(MANIFEST_FILE)).hexdigest(),
            "files": dict(sorted(digests.items())),
        }
        return f"sha256:{hashlib.sha256(canonical_json(fingerprint)).hexdigest()}"

    def _parse_checksums(self, package: MigrationPackageSource) -> dict[str, str]:
        if not package.exists(CHECKSUMS_FILE):
            return {}
        declared: dict[str, str] = {}
        for line in package.read(CHECKSUMS_FILE).decode("utf-8").splitlines():
            entry = line.strip()
            if not entry or entry.startswith("#"):
                continue
            parts = entry.split()
            if len(parts) != 2:
                raise InputValidationError("checksums.txt 行格式必须是 `<sha256>  <file>`")
            digest, name = parts[0].lower(), parts[1].lstrip("*")
            if len(digest) != 64:
                raise InputValidationError("checksums.txt 摘要必须是 64 位小写十六进制")
            declared[name] = digest
        return declared

    @transactional
    def _open_report(
        self, manifest: MigrationPackageManifest, package_checksum: str, context: RequestContext
    ) -> MigrationReport:
        created_at = self._clock()
        report = MigrationReport(
            migration_id=new_id("mig"),
            package_checksum=package_checksum,
            status=JobStatus.RUNNING,
            imported_count=0,
            skipped_count=0,
            conflict_count=0,
            failed_count=0,
            created_at=created_at,
            source_repository=manifest.source_repository,
            source_version=manifest.source_version,
        )
        try:
            self._migrations.add_migration_report(report, context.organization_id, context.project_id)
        except ValueError as exc:
            raise ConflictError(
                "同一迁移包摘要已存在报告", details={"package_checksum": package_checksum}
            ) from exc
        return report

    @transactional
    def _close_report(
        self,
        report: MigrationReport,
        tally: ImportTally,
        manifest: MigrationPackageManifest,
        context: RequestContext,
        *,
        dry_run: bool,
    ) -> MigrationReport:
        occurred_at = self._clock()
        details = {
            "schema_version": "1.0",
            "migration_id": report.migration_id,
            "package_checksum": report.package_checksum,
            "source_repository": manifest.source_repository,
            "source_version": manifest.source_version,
            "exporter_version": manifest.exporter_version,
            "tenant_id": manifest.tenant_id,
            "project_id": manifest.project_id,
            "dry_run": dry_run,
            "imported_count": tally.imported,
            "skipped_count": tally.skipped,
            "conflict_count": tally.conflicts,
            "failed_count": tally.failed,
            "failures": tally.failures,
            "files": [entry.model_dump(mode="json") for entry in manifest.files],
        }
        details_ref = self._object_storage.put_immutable(
            f"migrations/{report.migration_id}/report.json",
            canonical_json(details),
            "application/json",
            bucket=self._import_bucket,
        )
        status = (
            JobStatus.SUCCEEDED
            if tally.failed == 0 and tally.conflicts == 0
            else JobStatus.FAILED
        )
        completed = report.model_copy(
            update={
                "status": status,
                "imported_count": tally.imported,
                "skipped_count": tally.skipped,
                "conflict_count": tally.conflicts,
                "failed_count": tally.failed,
                "failures": tuple(tally.failures),
                "details_ref": details_ref,
                "completed_at": occurred_at,
            }
        )
        self._migrations.update_migration_report(
            completed, context.organization_id, context.project_id
        )
        self._record_audit(
            "dataset.migration.import",
            "migration_report",
            report.migration_id,
            context,
            before=report,
            after=completed,
            result="succeeded" if status == JobStatus.SUCCEEDED else "failed",
        )
        self._emit(
            "dataset.migration.completed",
            context,
            occurred_at,
            {
                "migration_id": completed.migration_id,
                "status": completed.status,
                "imported_count": completed.imported_count,
                "skipped_count": completed.skipped_count,
                "conflict_count": completed.conflict_count,
                "failed_count": completed.failed_count,
                "details_ref": details_ref.model_dump(mode="json"),
            },
        )
        return completed

    # ----------------------------------------------------------- 各类记录

    @transactional
    def _import_datasets(
        self,
        package: MigrationPackageSource,
        manifest: MigrationPackageManifest,
        context: RequestContext,
        *,
        dry_run: bool,
    ) -> ImportTally:
        tally = ImportTally()
        for line_number, payload in self._iter_records(package, manifest, DATASETS_FILE):
            try:
                record = MigrationDatasetRecord.model_validate(payload)
                value = Dataset(
                    dataset_id=record.dataset_id,
                    name=record.name,
                    description=record.description,
                    tenant_id=context.organization_id,
                    project_id=context.project_id,
                    created_by=record.created_by,
                    created_at=record.created_at,
                    status=map_core_dataset_status(record.status),
                    owner_principal_id=record.owner_principal_id or record.created_by,
                    labels=record.labels,
                    dataset_metadata=record.metadata,
                    updated_at=record.updated_at,
                    archived_at=record.archived_at,
                )
            except Exception as exc:
                tally.fail(f"{DATASETS_FILE}:{line_number} {type(exc).__name__}: {exc}")
                continue
            existing = self._existing_dataset(value.dataset_id, context)
            if existing is not None:
                if _same_dataset(existing, value):
                    tally.skipped += 1
                else:
                    tally.conflict(f"{DATASETS_FILE}:{line_number} dataset {value.dataset_id} 已存在且内容不同")
                continue
            if dry_run:
                tally.imported += 1
                continue
            try:
                self._datasets.add_dataset(value)
                tally.imported += 1
            except ValueError as exc:
                tally.conflict(f"{DATASETS_FILE}:{line_number} {exc}")
        return tally

    @transactional
    def _import_samples(
        self,
        package: MigrationPackageSource,
        manifest: MigrationPackageManifest,
        context: RequestContext,
        *,
        dry_run: bool,
    ) -> ImportTally:
        tally = ImportTally()
        for line_number, payload in self._iter_records(package, manifest, SAMPLES_FILE):
            location = f"{SAMPLES_FILE}:{line_number}"
            try:
                record = MigrationSampleRecord.model_validate(payload)
                value = Sample(
                    sample_id=record.sample_id,
                    tenant_id=context.organization_id,
                    project_id=context.project_id,
                    source_ref=record.source_ref,
                    media_type=record.media_type,
                    source_lineage=record.source_lineage,
                    sample_metadata=record.metadata,
                    created_at=record.created_at,
                    media_kind=record.media_type,
                    content_sha256=record.source_ref.checksum,
                    source_system=record.source_system,
                    source_resource_type=record.source_resource_type,
                    source_resource_id=record.source_resource_id,
                )
            except Exception as exc:
                tally.fail(f"{location} {type(exc).__name__}: {exc}")
                continue
            try:
                existing = self._samples.get_sample(
                    value.sample_id, context.organization_id, context.project_id
                )
                if existing == value:
                    tally.skipped += 1
                else:
                    tally.conflict(f"{location} sample {value.sample_id} 已存在且内容不同")
                continue
            except KeyError:
                pass
            if dry_run:
                tally.imported += 1
                continue
            try:
                self._samples.add_sample(value, record.created_by)
                tally.imported += 1
            except ValueError as exc:
                tally.conflict(f"{location} {exc}")
        return tally

    @transactional
    def _import_dataset_versions(
        self,
        package: MigrationPackageSource,
        manifest: MigrationPackageManifest,
        context: RequestContext,
        *,
        dry_run: bool,
    ) -> ImportTally:
        tally = ImportTally()
        for line_number, payload in self._iter_records(package, manifest, DATASET_VERSIONS_FILE):
            location = f"{DATASET_VERSIONS_FILE}:{line_number}"
            try:
                record = MigrationDatasetVersionRecord.model_validate(payload)
                status = map_core_dataset_version_status(record.status)
                manifest_ref = self._resolve_manifest_ref(
                    package, manifest, record, dry_run=dry_run
                )
                value = DatasetVersion(
                    dataset_version_id=record.version_id,
                    dataset_id=record.dataset_id,
                    version=record.version,
                    status=status,
                    manifest_ref=manifest_ref,
                    created_by=record.created_by,
                    created_at=record.created_at,
                    published_at=record.published_at,
                    archived_at=record.archived_at,
                    manifest_sha256=manifest_ref.checksum if manifest_ref else None,
                    sample_count=record.sample_count,
                    quality_report_id=record.quality_report_id,
                    lineage_snapshot_id=record.lineage_snapshot_id,
                )
            except Exception as exc:
                tally.fail(f"{location} {type(exc).__name__}: {exc}")
                continue
            if self._existing_dataset(value.dataset_id, context) is None:
                tally.fail(f"{location} dataset {value.dataset_id} 不在迁移包或目标库中")
                continue
            if not dry_run and value.status in {DatasetVersionStatus.PUBLISHED, DatasetVersionStatus.ARCHIVED}:
                error = self._recompute_manifest_digest(value)
                if error is not None:
                    tally.fail(f"{location} {error}")
                    continue
            existing = self._existing_version(value.dataset_version_id, context)
            if existing is not None:
                if _same_version(existing, value):
                    tally.skipped += 1
                else:
                    tally.conflict(f"{location} dataset version {value.dataset_version_id} 已存在且内容不同")
                continue
            if dry_run:
                tally.imported += 1
                continue
            try:
                self._datasets.add_dataset_version(
                    value, context.organization_id, context.project_id
                )
                for sample_id in record.sample_ids:
                    self._samples.restore_sample_to_version(
                        value.dataset_version_id,
                        sample_id,
                        context.organization_id,
                        context.project_id,
                    )
                tally.imported += 1
            except (ValueError, KeyError) as exc:
                tally.conflict(f"{location} {exc}")
        return tally

    @transactional
    def _import_annotation_providers(
        self,
        package: MigrationPackageSource,
        manifest: MigrationPackageManifest,
        context: RequestContext,
        *,
        dry_run: bool,
    ) -> ImportTally:
        tally = ImportTally()
        for line_number, payload in self._iter_records(package, manifest, ANNOTATION_PROVIDERS_FILE):
            location = f"{ANNOTATION_PROVIDERS_FILE}:{line_number}"
            try:
                record = MigrationAnnotationProviderRecord.model_validate(payload)
                value = AnnotationProvider(
                    provider_id=record.provider_id,
                    name=record.name,
                    provider_type=record.provider_type,
                    endpoint=record.endpoint,
                    active=record.active,
                    health=record.health,
                    created_at=record.created_at,
                    updated_at=record.updated_at,
                )
            except Exception as exc:
                tally.fail(f"{location} {type(exc).__name__}: {exc}")
                continue
            try:
                self._annotations.get_provider(
                    value.provider_id, context.organization_id, context.project_id
                )
                tally.skipped += 1
                continue
            except KeyError:
                pass
            if dry_run:
                tally.imported += 1
                continue
            try:
                self._annotations.add_provider(value, context.organization_id, context.project_id)
                tally.imported += 1
            except ValueError as exc:
                tally.conflict(f"{location} {exc}")
        return tally

    @transactional
    def _import_annotation_tasks(
        self,
        package: MigrationPackageSource,
        manifest: MigrationPackageManifest,
        context: RequestContext,
        *,
        dry_run: bool,
    ) -> ImportTally:
        tally = ImportTally()
        for line_number, payload in self._iter_records(package, manifest, ANNOTATION_TASKS_FILE):
            location = f"{ANNOTATION_TASKS_FILE}:{line_number}"
            try:
                record = MigrationAnnotationTaskRecord.model_validate(payload)
                if record.status not in set(AnnotationTaskStatus):
                    raise ValueError(f"unmapped annotation task status: {record.status}")
                value = AnnotationTask(
                    task_id=record.task_id,
                    tenant_id=context.organization_id,
                    project_id=context.project_id,
                    dataset_id=record.dataset_id,
                    schema_id=record.schema_id,
                    sample_ids=record.sample_ids,
                    status=AnnotationTaskStatus(record.status),
                    provider_id=record.provider_id,
                    assigned_to=record.assigned_to,
                    task_metadata=record.metadata,
                    consistency_score=record.consistency_score,
                    review_comment=record.review_comment,
                    created_by=record.created_by,
                    created_at=record.created_at,
                    updated_at=record.updated_at,
                )
            except Exception as exc:
                tally.fail(f"{location} {type(exc).__name__}: {exc}")
                continue
            try:
                self._annotations.get_task(value.task_id, context.organization_id, context.project_id)
                tally.skipped += 1
                continue
            except KeyError:
                pass
            if dry_run:
                tally.imported += 1
                continue
            try:
                self._annotations.add_task(value)
                tally.imported += 1
            except (ValueError, KeyError) as exc:
                tally.conflict(f"{location} {exc}")
        return tally

    def _verify_object_references(
        self, package: MigrationPackageSource, manifest: MigrationPackageManifest
    ) -> ImportTally:
        tally = ImportTally()
        for line_number, payload in self._iter_records(package, manifest, OBJECT_REFERENCES_FILE):
            location = f"{OBJECT_REFERENCES_FILE}:{line_number}"
            try:
                record = MigrationObjectReferenceRecord.model_validate(payload)
            except Exception as exc:
                tally.fail(f"{location} {type(exc).__name__}: {exc}")
                continue
            try:
                self._object_storage.read_verified(record.reference)
                tally.skipped += 1
            except FileNotFoundError:
                tally.fail(f"{location} 对象不存在：{record.reference.bucket}/{record.reference.key}")
            except ValueError as exc:
                tally.fail(f"{location} 对象摘要校验失败：{exc}")
        return tally

    def _count_reference_only(
        self,
        package: MigrationPackageSource,
        manifest: MigrationPackageManifest,
        name: str,
        model: type[PackageRecord],
    ) -> ImportTally:
        """只校验结构并计入跳过：这些事实仍由 Core 拥有（指南 10、69）。"""
        tally = ImportTally()
        for line_number, payload in self._iter_records(package, manifest, name):
            try:
                model.model_validate(payload)
                tally.skipped += 1
            except Exception as exc:
                tally.fail(f"{name}:{line_number} {type(exc).__name__}: {exc}")
        return tally

    # ------------------------------------------------------------------ 内部

    def _recompute_manifest_digest(self, value: DatasetVersion) -> str | None:
        if value.manifest_ref is None:
            return "已发布版本缺少 manifest_ref"
        try:
            content = self._object_storage.read_verified(value.manifest_ref)
        except FileNotFoundError:
            return f"Manifest 对象不存在：{value.manifest_ref.bucket}/{value.manifest_ref.key}"
        except ValueError as exc:
            return f"Manifest 摘要校验失败：{exc}"
        recomputed = f"sha256:{hashlib.sha256(content).hexdigest()}"
        if recomputed != value.manifest_ref.checksum:
            return "重新计算的 Manifest 摘要与迁移包声明不一致"
        return None

    def _resolve_manifest_ref(
        self,
        package: MigrationPackageSource,
        manifest: MigrationPackageManifest,
        record: MigrationDatasetVersionRecord,
        *,
        dry_run: bool,
    ) -> ObjectReference | None:
        if record.manifest_file is None:
            return record.manifest_ref
        entry = manifest.entry(record.manifest_file)
        if entry is None:
            raise ValueError(f"manifest_file is not declared: {record.manifest_file}")
        content = package.read(record.manifest_file)
        digest = hashlib.sha256(content).hexdigest()
        if digest != entry.sha256:
            raise ValueError(f"manifest_file checksum mismatch: {record.manifest_file}")
        key = f"migrations/manifests/{record.version_id}-{digest}.json"
        if dry_run:
            return ObjectReference(
                bucket=self._import_bucket,
                key=key,
                version=None,
                checksum=f"sha256:{digest}",
                size_bytes=len(content),
                content_type="application/json",
            )
        return self._object_storage.put_immutable(
            key, content, "application/json", bucket=self._import_bucket
        )

    def _existing_dataset(self, dataset_id: str, context: RequestContext) -> Dataset | None:
        try:
            return self._datasets.get_dataset(dataset_id, context.organization_id, context.project_id)
        except KeyError:
            return None

    def _existing_version(self, version_id: str, context: RequestContext) -> DatasetVersion | None:
        try:
            return self._datasets.get_dataset_version(
                version_id, context.organization_id, context.project_id
            )
        except KeyError:
            return None

    def _iter_records(
        self, package: MigrationPackageSource, manifest: MigrationPackageManifest, name: str
    ) -> Iterator[tuple[int, dict[str, Any]]]:
        if manifest.entry(name) is None:
            return
        for line_number, line in enumerate(self._iter_lines(package, name), start=1):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise InputValidationError(
                    "迁移包 JSONL 行不是合法 JSON", details={"file": name, "line": line_number, "reason": str(exc)}
                ) from exc
            if not isinstance(payload, dict):
                raise InputValidationError(
                    "迁移包 JSONL 行必须是 JSON 对象", details={"file": name, "line": line_number}
                )
            yield line_number, payload

    @staticmethod
    def _iter_lines(package: MigrationPackageSource, name: str) -> Iterator[str]:
        if not package.exists(name):
            return
        for line in package.read(name).decode("utf-8").splitlines():
            if line.strip():
                yield line


def _same_dataset(existing: Dataset, incoming: Dataset) -> bool:
    return (
        existing.name == incoming.name
        and existing.description == incoming.description
        and existing.status == incoming.status
        and existing.created_at == incoming.created_at
    )


def _same_version(existing: DatasetVersion, incoming: DatasetVersion) -> bool:
    return (
        existing.dataset_id == incoming.dataset_id
        and existing.version == incoming.version
        and existing.status == incoming.status
        and existing.manifest_sha256 == incoming.manifest_sha256
        and existing.created_at == incoming.created_at
    )
