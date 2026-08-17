"""Dataset 与 Dataset Version 应用服务（指南 6.1、6.2、11、M2）。

发布后的 Dataset Version 不可变：version、manifest_ref、manifest_sha256、样本集合、标注快照、
QualityReport 引用和 Lineage Snapshot 引用全部冻结（规范 12、61）。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

from scenara_data import contracts
from scenara_data.application.annotations import AnnotationService
from scenara_data.application.errors import (
    ConflictError,
    ImmutableResourceError,
    InputValidationError,
    InvalidStateError,
    ResourceNotFoundError,
)
from scenara_data.application.lineage import LineageService
from scenara_data.application.quality import QualityService
from scenara_data.application.support import ApplicationService, Clock, new_id, transactional, utc_now
from scenara_data.domain.models import (
    DataQualityReport,
    Dataset,
    DatasetAccessGrant,
    DatasetManifest,
    DatasetStatus,
    DatasetVersion,
    DatasetVersionStatus,
    ObjectReference,
    QualityStatus,
    Sample,
)
from scenara_data.domain.services import (
    build_manifest_payload,
    canonical_json,
    manifest_object_key,
    sample_object_key,
    split_counts,
)
from scenara_data.ports.interfaces import (
    AuditPort,
    DatasetRepository,
    ObjectStorageProvider,
    OutboxPort,
    RequestContext,
    SampleRepository,
    UnitOfWork,
)


def _immutable_uri(reference: ObjectReference) -> str:
    key = quote(reference.key, safe="/")
    digest = reference.checksum.removeprefix("sha256:")
    return f"s3://{reference.bucket}/{key}#sha256={digest}"

GRANT_PERMISSIONS = frozenset({"manifest.read", "objects.read"})


class DatasetService(ApplicationService):
    def __init__(
        self,
        *,
        unit_of_work: UnitOfWork,
        datasets: DatasetRepository,
        samples: SampleRepository,
        annotations: AnnotationService,
        lineage: LineageService,
        quality: QualityService,
        object_storage: ObjectStorageProvider,
        audit: AuditPort,
        outbox: OutboxPort,
        dataset_bucket: str,
        manifest_bucket: str | None = None,
        access_grant_max_ttl_seconds: int = 86400,
        clock: Clock = utc_now,
    ) -> None:
        super().__init__(unit_of_work=unit_of_work, audit=audit, outbox=outbox, clock=clock)
        self._datasets = datasets
        self._samples = samples
        self._annotations = annotations
        self._lineage = lineage
        self._quality = quality
        self._object_storage = object_storage
        self._dataset_bucket = dataset_bucket
        self._manifest_bucket = manifest_bucket or dataset_bucket
        self._access_grant_max_ttl_seconds = access_grant_max_ttl_seconds

    # ---------------------------------------------------------------- 数据集

    @transactional
    def create_dataset(
        self,
        *,
        name: str,
        description: str,
        context: RequestContext,
        dataset_id: str | None = None,
        labels: tuple[str, ...] = (),
        dataset_metadata: dict[str, Any] | None = None,
    ) -> Dataset:
        self._require(context, "data.dataset.create")
        value = Dataset(
            dataset_id=dataset_id or new_id("dst"),
            name=name,
            description=description,
            tenant_id=context.organization_id,
            project_id=context.project_id,
            created_by=context.principal_id,
            created_at=self._clock(),
            owner_principal_id=context.principal_id,
            labels=labels,
            dataset_metadata=dict(dataset_metadata or {}),
        )
        try:
            self._datasets.add_dataset(value)
        except ValueError as exc:
            raise ConflictError("数据集标识已存在", details={"dataset_id": value.dataset_id}) from exc
        self._record_audit("dataset.create", "dataset", value.dataset_id, context, after=value)
        self._emit(
            "dataset.created",
            context,
            value.created_at,
            {"dataset_id": value.dataset_id, "name": value.name, "status": value.status},
        )
        return value

    def get_dataset(self, dataset_id: str, context: RequestContext) -> Dataset:
        self._require(context, "data.dataset.read")
        return self.require_dataset(dataset_id, context)

    def list_datasets(self, context: RequestContext, *, limit: int, offset: int) -> tuple[list[Dataset], int]:
        self._require(context, "data.dataset.read")
        return self._datasets.list_datasets(
            context.organization_id, context.project_id, limit=limit, offset=offset
        )

    @transactional
    def update_dataset(
        self,
        dataset_id: str,
        context: RequestContext,
        *,
        name: str | None = None,
        description: str | None = None,
        labels: tuple[str, ...] | None = None,
        dataset_metadata: dict[str, Any] | None = None,
        target_status: DatasetStatus | None = None,
    ) -> Dataset:
        permission = "data.dataset.archive" if target_status == DatasetStatus.ARCHIVED else "data.dataset.update"
        self._require(context, permission)
        current = self.require_dataset(dataset_id, context)
        if current.status == DatasetStatus.ARCHIVED:
            raise InvalidStateError("归档数据集不可修改")
        occurred_at = self._clock()
        try:
            if target_status == DatasetStatus.ACTIVE:
                updated = current.activate(occurred_at)
            elif target_status == DatasetStatus.ARCHIVED:
                updated = current.archive(occurred_at)
            elif target_status in {None, current.status}:
                updated = current.model_copy(update={"updated_at": occurred_at})
            else:
                raise ValueError("非法的数据集状态转换")
        except ValueError as exc:
            raise InvalidStateError(str(exc)) from exc
        changes: dict[str, Any] = {"updated_at": occurred_at}
        if name is not None:
            changes["name"] = name
        if description is not None:
            changes["description"] = description
        if labels is not None:
            changes["labels"] = labels
        if dataset_metadata is not None:
            changes["dataset_metadata"] = dataset_metadata
        updated = updated.model_copy(update=changes)
        self._datasets.update_dataset(updated)
        archived = updated.status == DatasetStatus.ARCHIVED
        self._record_audit(
            "dataset.archive" if archived else "dataset.update",
            "dataset",
            dataset_id,
            context,
            before=current,
            after=updated,
        )
        self._emit(
            "dataset.archived" if archived else "dataset.updated",
            context,
            occurred_at,
            {"dataset_id": dataset_id, "status": updated.status},
        )
        return updated

    def archive_dataset(self, dataset_id: str, context: RequestContext) -> Dataset:
        return self.update_dataset(dataset_id, context, target_status=DatasetStatus.ARCHIVED)

    def require_dataset(self, dataset_id: str, context: RequestContext) -> Dataset:
        try:
            return self._datasets.get_dataset(dataset_id, context.organization_id, context.project_id)
        except KeyError as exc:
            raise ResourceNotFoundError("dataset", dataset_id) from exc

    # ------------------------------------------------------------ 数据集版本

    @transactional
    def create_dataset_version(
        self,
        *,
        dataset_id: str,
        version: str,
        context: RequestContext,
        dataset_version_id: str | None = None,
    ) -> DatasetVersion:
        self._require(context, "data.dataset.update")
        dataset = self.require_dataset(dataset_id, context)
        if dataset.status != DatasetStatus.ACTIVE:
            raise InvalidStateError("只有启用状态的数据集可以创建新版本")
        value = DatasetVersion(
            dataset_version_id=dataset_version_id or new_id("dsv"),
            dataset_id=dataset_id,
            version=version,
            created_by=context.principal_id,
            created_at=self._clock(),
        )
        try:
            self._datasets.add_dataset_version(value, context.organization_id, context.project_id)
        except ValueError as exc:
            raise ConflictError(
                "数据集版本标识或版本号已存在",
                details={"dataset_id": dataset_id, "version": version},
            ) from exc
        self._record_audit(
            "dataset.version.create", "dataset_version", value.dataset_version_id, context, after=value
        )
        self._emit(
            "dataset.version.created",
            context,
            value.created_at,
            {
                "dataset_id": dataset_id,
                "dataset_version_id": value.dataset_version_id,
                "version": version,
            },
        )
        return value

    def get_dataset_version(self, dataset_version_id: str, context: RequestContext) -> DatasetVersion:
        self._require(context, "data.dataset.read")
        return self.require_version(dataset_version_id, context)

    def list_dataset_versions(
        self, dataset_id: str, context: RequestContext, *, limit: int, offset: int
    ) -> tuple[list[DatasetVersion], int]:
        self._require(context, "data.dataset.read")
        self.require_dataset(dataset_id, context)
        return self._datasets.list_dataset_versions(
            dataset_id, context.organization_id, context.project_id, limit=limit, offset=offset
        )

    @transactional
    def begin_build(self, dataset_version_id: str, context: RequestContext) -> DatasetVersion:
        self._require(context, "data.dataset.update")
        current = self.require_version(dataset_version_id, context)
        return self._apply_transition(current, DatasetVersionStatus.BUILDING, context)

    @transactional
    def fail_build(self, dataset_version_id: str, context: RequestContext, *, reason: str) -> DatasetVersion:
        self._require(context, "data.dataset.update")
        current = self.require_version(dataset_version_id, context)
        updated = self._apply_transition(
            current, DatasetVersionStatus.FAILED, context, failure_reason=reason
        )
        self._emit(
            "dataset.version.failed",
            context,
            self._clock(),
            {
                "dataset_id": updated.dataset_id,
                "dataset_version_id": dataset_version_id,
                "reason": reason,
            },
        )
        return updated

    @transactional
    def add_sample_to_version(
        self, dataset_version_id: str, sample_id: str, context: RequestContext
    ) -> DatasetVersion:
        self._require(context, "data.dataset.update")
        version = self.require_version(dataset_version_id, context)
        if version.status != DatasetVersionStatus.BUILDING:
            raise InvalidStateError("只有构建中的数据集版本可以添加样本")
        try:
            self._samples.get_sample(sample_id, context.organization_id, context.project_id)
        except KeyError as exc:
            raise ResourceNotFoundError("sample", sample_id) from exc
        try:
            self._samples.add_sample_to_version(
                dataset_version_id, sample_id, context.organization_id, context.project_id
            )
        except ValueError as exc:
            raise ConflictError(
                "样本已属于该数据集版本",
                details={"dataset_version_id": dataset_version_id, "sample_id": sample_id},
            ) from exc
        return version

    def list_version_samples(self, dataset_version_id: str, context: RequestContext) -> list[Sample]:
        self._require(context, "data.sample.read")
        self.require_version(dataset_version_id, context)
        return self._samples.list_version_samples(
            dataset_version_id, context.organization_id, context.project_id
        )

    @transactional
    def validate_dataset_version(
        self, dataset_version_id: str, context: RequestContext, *, rule_ids: tuple[str, ...] = ()
    ) -> tuple[DatasetVersion, DataQualityReport]:
        """执行质量运行并把构建中状态推进到就绪状态；质量失败则推进到失败状态。"""
        self._require(context, "data.quality.run")
        current = self.require_version(dataset_version_id, context)
        if current.status != DatasetVersionStatus.BUILDING:
            raise InvalidStateError("只有构建中的数据集版本可以验证")
        _, report = self._quality.run_quality(dataset_version_id, context, rule_ids=rule_ids)
        if report.status == QualityStatus.FAILED:
            failed = self._apply_transition(
                current,
                DatasetVersionStatus.FAILED,
                context,
                quality_report_id=report.report_id,
                failure_reason=f"数据质量验证失败：{report.report_id}",
            )
            self._emit(
                "dataset.version.failed",
                context,
                self._clock(),
                {
                    "dataset_id": failed.dataset_id,
                    "dataset_version_id": dataset_version_id,
                    "quality_report_id": report.report_id,
                },
            )
            # 质量运行本身已完成，只是未通过发布门禁。返回失败版本和持久化报告，
            # 让调用方能够查询问题并创建新的构建版本；不能抛异常回滚审计、报告和事件。
            return failed, report
        ready = self._apply_transition(
            current, DatasetVersionStatus.READY, context, quality_report_id=report.report_id
        )
        self._emit(
            "dataset.version.ready",
            context,
            self._clock(),
            {
                "dataset_id": ready.dataset_id,
                "dataset_version_id": dataset_version_id,
                "quality_report_id": report.report_id,
                "quality_status": report.status,
            },
        )
        return ready, report

    @transactional
    def publish_dataset_version(
        self, dataset_version_id: str, context: RequestContext
    ) -> tuple[DatasetVersion, DatasetManifest]:
        self._require(context, "data.dataset.publish")
        current = self.require_version(dataset_version_id, context)
        if current.status in {DatasetVersionStatus.PUBLISHED, DatasetVersionStatus.ARCHIVED}:
            raise ImmutableResourceError(dataset_version_id)
        if current.status != DatasetVersionStatus.READY:
            raise InvalidStateError("只有已就绪的数据集版本可以发布")
        if current.quality_report_id is None:
            raise InvalidStateError("发布前必须绑定质量报告")
        samples = self._samples.list_version_samples(
            dataset_version_id, context.organization_id, context.project_id
        )
        if not samples:
            raise InputValidationError("数据集版本没有可发布样本")

        occurred_at = self._clock()
        manifest_id = new_id("dsm")
        materialized = self._materialize_samples(current, samples)
        snapshot, frozen = self._annotations.freeze_for_version(
            dataset_version_id=dataset_version_id,
            sample_ids=[sample.sample_id for sample in samples],
            context=context,
            occurred_at=occurred_at,
        )
        edges: list[tuple[str, str, str, str, str]] = [
            ("dataset", current.dataset_id, "dataset_version", dataset_version_id, "has_version")
        ]
        edges.extend(
            ("sample", sample.sample_id, "dataset_version", dataset_version_id, "included_in")
            for sample in samples
        )
        edges.extend(
            ("annotation_revision", revision_id, "dataset_version", dataset_version_id, "frozen_in")
            for entries in frozen.values()
            for _, revision_id in entries
        )
        lineage_ids = self._lineage.record_edges(edges, context, occurred_at=occurred_at)
        lineage_snapshot = self._lineage.create_snapshot(
            dataset_version_id=dataset_version_id,
            lineage_ids=lineage_ids,
            context=context,
            occurred_at=occurred_at,
        )
        payload = build_manifest_payload(
            manifest_id=manifest_id,
            dataset_id=current.dataset_id,
            dataset_version_id=dataset_version_id,
            version=current.version,
            created_at=occurred_at,
            samples=samples,
            materialized=materialized,
            frozen_annotations=frozen,
            quality_report_id=current.quality_report_id,
            lineage_snapshot_id=lineage_snapshot.snapshot_id,
            annotation_snapshot_id=snapshot.snapshot_id,
        )
        manifest_ref = self._object_storage.put_immutable(
            manifest_object_key(current.dataset_id, current.version),
            canonical_json(payload),
            "application/json",
            bucket=self._manifest_bucket,
        )
        manifest = DatasetManifest(
            manifest_id=manifest_id,
            dataset_id=current.dataset_id,
            dataset_version_id=dataset_version_id,
            version=current.version,
            sample_ids=tuple(sorted(sample.sample_id for sample in samples)),
            split_counts=split_counts(samples),
            manifest_ref=manifest_ref,
            created_at=occurred_at,
        )
        try:
            published = current.transition(
                DatasetVersionStatus.PUBLISHED,
                manifest_ref=manifest_ref,
                occurred_at=occurred_at,
                sample_count=len(samples),
                quality_report_id=current.quality_report_id,
                lineage_snapshot_id=lineage_snapshot.snapshot_id,
                annotation_snapshot_id=snapshot.snapshot_id,
            )
        except ValueError as exc:
            raise InvalidStateError(str(exc)) from exc
        self._datasets.update_dataset_version(published, context.organization_id, context.project_id)
        self._record_audit(
            "dataset.version.publish",
            "dataset_version",
            dataset_version_id,
            context,
            before=current,
            after=published,
        )
        self._emit(
            "dataset.version.published",
            context,
            occurred_at,
            {
                "dataset_id": current.dataset_id,
                "dataset_version_id": dataset_version_id,
                "version": current.version,
                "sample_count": len(samples),
                "manifest_ref": manifest_ref.model_dump(mode="json"),
                "manifest_sha256": manifest_ref.checksum,
                "quality_report_id": current.quality_report_id,
                "lineage_snapshot_id": lineage_snapshot.snapshot_id,
                "annotation_snapshot_id": snapshot.snapshot_id,
            },
        )
        return published, manifest

    @transactional
    def archive_dataset_version(self, dataset_version_id: str, context: RequestContext) -> DatasetVersion:
        self._require(context, "data.dataset.archive")
        current = self.require_version(dataset_version_id, context)
        if current.status != DatasetVersionStatus.PUBLISHED:
            raise InvalidStateError("只有已发布的数据集版本可以归档")
        occurred_at = self._clock()
        try:
            archived = current.transition(DatasetVersionStatus.ARCHIVED, occurred_at=occurred_at)
        except ValueError as exc:
            raise InvalidStateError(str(exc)) from exc
        self._datasets.update_dataset_version(archived, context.organization_id, context.project_id)
        self._record_audit(
            "dataset.version.archive",
            "dataset_version",
            dataset_version_id,
            context,
            before=current,
            after=archived,
        )
        self._emit(
            "dataset.version.archived",
            context,
            occurred_at,
            {"dataset_id": current.dataset_id, "dataset_version_id": dataset_version_id},
        )
        return archived

    # ---------------------------------------------------------- 对模型平台输出

    def dataset_version_reference(self, dataset_version_id: str, context: RequestContext) -> dict[str, Any]:
        """`dataset-version-input` 契约：不可变清单、摘要、授权和血缘信息。"""
        self._require(context, "data.dataset.read")
        value = self.require_version(dataset_version_id, context)
        if value.status != DatasetVersionStatus.PUBLISHED or value.manifest_ref is None:
            raise InvalidStateError("只有已发布的数据集版本可以作为训练输入")
        grants = self._datasets.list_access_grants(
            dataset_version_id, context.organization_id, context.project_id
        )
        now = self._clock()
        active_grants = sorted(
            (grant for grant in grants if grant.expires_at > now),
            key=lambda grant: (grant.created_at, grant.grant_id),
        )
        if not active_grants:
            raise InvalidStateError("数据集版本尚未签发有效的模型访问授权")
        if value.lineage_snapshot_id is None or value.published_at is None or value.manifest_sha256 is None:
            raise InvalidStateError("发布版本缺少不可变清单或血缘快照")
        lineage_snapshot = self._lineage.get_snapshot(value.lineage_snapshot_id, context)
        lineage_ref = self._object_storage.put_immutable(
            f"datasets/{value.dataset_id}/{value.version}/lineage-snapshot.json",
            canonical_json(lineage_snapshot.model_dump(mode="json")),
            "application/json",
            bucket=self._manifest_bucket,
        )
        grant = active_grants[0]
        return {
            "schema_version": contracts.DATASET_VERSION_INPUT_SCHEMA_VERSION,
            "dataset_id": value.dataset_id,
            "version": value.version,
            "manifest_uri": _immutable_uri(value.manifest_ref),
            "manifest_sha256": value.manifest_sha256.removeprefix("sha256:"),
            "lineage_refs": [_immutable_uri(lineage_ref)],
            "authorization_id": grant.grant_id,
            "authorized_consumer_repository_ids": ["scenara-model"],
            "created_at": value.published_at.timestamp(),
        }

    def read_manifest(self, dataset_version_id: str, context: RequestContext) -> dict[str, Any]:
        self._require(context, "data.dataset.read")
        value = self.require_version(dataset_version_id, context)
        if value.manifest_ref is None:
            raise InvalidStateError("数据集版本尚未生成不可变清单")
        content = self._object_storage.read_verified(value.manifest_ref)
        return json.loads(content.decode("utf-8"))

    @transactional
    def create_access_grant(
        self,
        dataset_version_id: str,
        *,
        service_account_id: str,
        permissions: tuple[str, ...],
        ttl_seconds: int,
        context: RequestContext,
    ) -> tuple[DatasetAccessGrant, dict[str, str]]:
        self._require(context, "data.export.execute")
        value = self.require_version(dataset_version_id, context)
        if value.status != DatasetVersionStatus.PUBLISHED or value.manifest_ref is None:
            raise InvalidStateError("只有已发布的数据集版本可以授权访问")
        unknown = sorted(set(permissions) - GRANT_PERMISSIONS)
        if unknown or not permissions:
            raise InputValidationError(
                "授权范围未登记",
                details={"permissions": list(permissions), "allowed": sorted(GRANT_PERMISSIONS)},
            )
        if ttl_seconds <= 0 or ttl_seconds > self._access_grant_max_ttl_seconds:
            raise InputValidationError(
                "授权有效期超出允许范围",
                details={"ttl_seconds": ttl_seconds, "max_ttl_seconds": self._access_grant_max_ttl_seconds},
            )
        created_at = self._clock()
        grant = DatasetAccessGrant(
            grant_id=new_id("dag"),
            dataset_version_id=dataset_version_id,
            service_account_id=service_account_id,
            permissions=tuple(sorted(set(permissions))),  # type: ignore[arg-type]
            expires_at=created_at + timedelta(seconds=ttl_seconds),
            created_by=context.principal_id,
            created_at=created_at,
        )
        self._datasets.add_access_grant(grant, context.organization_id, context.project_id)
        urls: dict[str, str] = {}
        if "manifest.read" in grant.permissions:
            urls["manifest_url"] = self._object_storage.presign_read(value.manifest_ref, ttl_seconds)
        self._record_audit(
            "dataset.access_grant.create", "dataset_access_grant", grant.grant_id, context, after=grant
        )
        self._emit(
            "dataset.access_grant.created",
            context,
            created_at,
            {
                "grant_id": grant.grant_id,
                "dataset_version_id": dataset_version_id,
                "service_account_id": service_account_id,
                "permissions": list(grant.permissions),
                "expires_at": grant.expires_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            },
        )
        return grant, urls

    def list_access_grants(
        self, dataset_version_id: str, context: RequestContext
    ) -> list[DatasetAccessGrant]:
        self._require(context, "data.dataset.read")
        self.require_version(dataset_version_id, context)
        return self._datasets.list_access_grants(
            dataset_version_id, context.organization_id, context.project_id
        )

    def require_version(self, dataset_version_id: str, context: RequestContext) -> DatasetVersion:
        try:
            return self._datasets.get_dataset_version(
                dataset_version_id, context.organization_id, context.project_id
            )
        except KeyError as exc:
            raise ResourceNotFoundError("dataset_version", dataset_version_id) from exc

    # ------------------------------------------------------------------ 内部

    def _materialize_samples(
        self, version: DatasetVersion, samples: list[Sample]
    ) -> dict[str, ObjectReference]:
        """把样本内容复制到数据平台自有不可变对象空间并验证 SHA-256（指南 9）。"""
        materialized: dict[str, ObjectReference] = {}
        for sample in samples:
            if sample.content_ref is not None:
                self._object_storage.read_verified(sample.content_ref)
                materialized[sample.sample_id] = sample.content_ref
                continue
            content = self._object_storage.read_verified(sample.source_ref)
            reference = self._object_storage.put_immutable(
                sample_object_key(version.dataset_id, version.version, sample.sample_id, sample.source_ref.key),
                content,
                sample.source_ref.content_type,
                bucket=self._dataset_bucket,
            )
            updated = sample.materialize(reference)
            self._samples.update_sample(updated)
            materialized[sample.sample_id] = reference
        return materialized

    def _published_split_counts(self, version: DatasetVersion, context: RequestContext) -> dict[str, int]:
        samples = self._samples.list_version_samples(
            version.dataset_version_id, context.organization_id, context.project_id
        )
        return split_counts(samples)

    def _apply_transition(
        self,
        current: DatasetVersion,
        target: DatasetVersionStatus,
        context: RequestContext,
        *,
        quality_report_id: str | None = None,
        failure_reason: str | None = None,
        occurred_at: datetime | None = None,
    ) -> DatasetVersion:
        try:
            updated = current.transition(
                target,
                quality_report_id=quality_report_id,
                failure_reason=failure_reason,
                occurred_at=occurred_at,
            )
        except ValueError as exc:
            raise InvalidStateError(str(exc)) from exc
        self._datasets.update_dataset_version(updated, context.organization_id, context.project_id)
        self._record_audit(
            f"dataset.version.{target}",
            "dataset_version",
            current.dataset_version_id,
            context,
            before=current,
            after=updated,
        )
        return updated
