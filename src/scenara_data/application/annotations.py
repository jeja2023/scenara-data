"""标注领域应用服务（指南 6.4、11.1、M4）。

标注修订采用追加式版本，审核历史不可覆盖；Dataset Version 发布时冻结当时已接受的修订。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from scenara_data.application.errors import (
    ConflictError,
    InputValidationError,
    InvalidStateError,
    ResourceNotFoundError,
)
from scenara_data.application.support import ApplicationService, Clock, new_id, transactional, utc_now
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
    ObjectReference,
)
from scenara_data.domain.services import annotation_snapshot_checksum
from scenara_data.ports.interfaces import (
    AnnotationRepository,
    AuditPort,
    DatasetRepository,
    OutboxPort,
    RequestContext,
    SampleRepository,
    UnitOfWork,
)


class AnnotationService(ApplicationService):
    def __init__(
        self,
        *,
        unit_of_work: UnitOfWork,
        annotations: AnnotationRepository,
        samples: SampleRepository,
        datasets: DatasetRepository,
        audit: AuditPort,
        outbox: OutboxPort,
        clock: Clock = utc_now,
    ) -> None:
        super().__init__(unit_of_work=unit_of_work, audit=audit, outbox=outbox, clock=clock)
        self._annotations = annotations
        self._samples = samples
        self._datasets = datasets

    # ------------------------------------------------------------------ 标注

    @transactional
    def create_annotation(
        self,
        *,
        sample_id: str,
        schema_id: str,
        payload: dict[str, Any],
        context: RequestContext,
        annotation_id: str | None = None,
        task_id: str | None = None,
    ) -> Annotation:
        self._require(context, "data.annotation.create")
        self._require_sample(sample_id, context)
        if task_id is not None:
            task = self._require_task(task_id, context)
            if sample_id not in task.sample_ids:
                raise InputValidationError(
                    "样本不属于该标注任务",
                    details={"task_id": task_id, "sample_id": sample_id},
                )
        occurred_at = self._clock()
        resolved_id = annotation_id or new_id("ann")
        revision = AnnotationRevision(
            revision_id=new_id("anr"),
            annotation_id=resolved_id,
            revision_number=1,
            payload=payload,
            created_by=context.principal_id,
            created_at=occurred_at,
            task_id=task_id,
        )
        value = Annotation(
            annotation_id=resolved_id,
            sample_id=sample_id,
            schema_id=schema_id,
            payload=payload,
            created_by=context.principal_id,
            created_at=occurred_at,
            task_id=task_id,
            current_revision_id=revision.revision_id,
            revision_number=1,
        )
        try:
            self._annotations.add_annotation(value, context.organization_id, context.project_id)
            self._annotations.add_revision(revision, context.organization_id, context.project_id)
        except ValueError as exc:
            raise ConflictError("标注标识已存在", details={"annotation_id": resolved_id}) from exc
        return value

    @transactional
    def append_revision(
        self,
        annotation_id: str,
        *,
        payload: dict[str, Any],
        context: RequestContext,
    ) -> tuple[Annotation, AnnotationRevision]:
        self._require(context, "data.annotation.create")
        current = self.require_annotation(annotation_id, context)
        occurred_at = self._clock()
        revision = AnnotationRevision(
            revision_id=new_id("anr"),
            annotation_id=annotation_id,
            revision_number=current.revision_number + 1,
            payload=payload,
            created_by=context.principal_id,
            created_at=occurred_at,
            task_id=current.task_id,
        )
        try:
            self._annotations.add_revision(revision, context.organization_id, context.project_id)
        except ValueError as exc:
            raise ConflictError(
                "标注修订版本已被并发请求占用",
                details={"annotation_id": annotation_id, "revision_number": revision.revision_number},
            ) from exc
        updated = current.append_revision(
            revision_id=revision.revision_id, payload=payload, occurred_at=occurred_at
        )
        self._annotations.update_annotation(updated, context.organization_id, context.project_id)
        return updated, revision

    def list_revisions(self, annotation_id: str, context: RequestContext) -> list[AnnotationRevision]:
        self._require(context, "data.dataset.read")
        self.require_annotation(annotation_id, context)
        return self._annotations.list_revisions(annotation_id, context.organization_id, context.project_id)

    @transactional
    def submit_annotation(self, annotation_id: str, context: RequestContext) -> Annotation:
        self._require(context, "data.annotation.create")
        current = self.require_annotation(annotation_id, context)
        try:
            updated = current.submit_for_review()
        except ValueError as exc:
            raise InvalidStateError(str(exc)) from exc
        self._annotations.update_annotation(updated, context.organization_id, context.project_id)
        self._emit(
            "annotation.submitted",
            context,
            self._clock(),
            {
                "annotation_id": annotation_id,
                "sample_id": updated.sample_id,
                "revision_id": updated.current_revision_id,
                "task_id": updated.task_id,
            },
        )
        return updated

    @transactional
    def review_annotation(
        self, annotation_id: str, target: AnnotationStatus, context: RequestContext
    ) -> Annotation:
        self._require(context, "data.annotation.review")
        current = self.require_annotation(annotation_id, context)
        occurred_at = self._clock()
        try:
            reviewed = current.review(target, reviewer=context.principal_id, occurred_at=occurred_at)
        except ValueError as exc:
            raise InvalidStateError(str(exc)) from exc
        self._annotations.update_annotation(reviewed, context.organization_id, context.project_id)
        self._record_audit(
            "annotation.review", "annotation", annotation_id, context, before=current, after=reviewed
        )
        self._emit(
            "annotation.reviewed",
            context,
            occurred_at,
            {
                "annotation_id": annotation_id,
                "sample_id": reviewed.sample_id,
                "status": reviewed.status,
                "revision_id": reviewed.accepted_revision_id or reviewed.current_revision_id,
            },
        )
        return reviewed

    def list_annotations(
        self, sample_id: str, context: RequestContext, *, limit: int, offset: int
    ) -> tuple[list[Annotation], int]:
        self._require(context, "data.dataset.read")
        self._require_sample(sample_id, context)
        return self._annotations.list_annotations(
            sample_id, context.organization_id, context.project_id, limit=limit, offset=offset
        )

    def require_annotation(self, annotation_id: str, context: RequestContext) -> Annotation:
        try:
            return self._annotations.get_annotation(
                annotation_id, context.organization_id, context.project_id
            )
        except KeyError as exc:
            raise ResourceNotFoundError("annotation", annotation_id) from exc

    # -------------------------------------------------------------- 标注任务

    @transactional
    def create_task(
        self,
        *,
        dataset_id: str,
        schema_id: str,
        sample_ids: tuple[str, ...],
        context: RequestContext,
        task_id: str | None = None,
        provider_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AnnotationTask:
        self._require(context, "data.annotation.create")
        self._require_dataset(dataset_id, context)
        if len(set(sample_ids)) != len(sample_ids):
            raise InputValidationError("标注任务样本不能重复")
        for sample_id in sample_ids:
            self._require_sample(sample_id, context)
        if provider_id is not None:
            self._require_provider(provider_id, context)
        occurred_at = self._clock()
        value = AnnotationTask(
            task_id=task_id or new_id("ant"),
            tenant_id=context.organization_id,
            project_id=context.project_id,
            dataset_id=dataset_id,
            schema_id=schema_id,
            sample_ids=sample_ids,
            provider_id=provider_id,
            task_metadata=dict(metadata or {}),
            created_by=context.principal_id,
            created_at=occurred_at,
            updated_at=occurred_at,
        )
        try:
            self._annotations.add_task(value)
        except ValueError as exc:
            raise ConflictError("标注任务标识已存在", details={"task_id": value.task_id}) from exc
        self._record_audit("annotation.task.create", "annotation_task", value.task_id, context, after=value)
        self._emit(
            "annotation.task.created",
            context,
            occurred_at,
            {
                "task_id": value.task_id,
                "dataset_id": dataset_id,
                "sample_count": len(sample_ids),
                "provider_id": provider_id,
            },
        )
        return value

    def get_task(self, task_id: str, context: RequestContext) -> AnnotationTask:
        self._require(context, "data.dataset.read")
        return self._require_task(task_id, context)

    def list_tasks(
        self,
        context: RequestContext,
        *,
        limit: int,
        offset: int,
        dataset_id: str | None = None,
        status: str | None = None,
    ) -> tuple[list[AnnotationTask], int]:
        self._require(context, "data.dataset.read")
        if status is not None and status not in set(AnnotationTaskStatus):
            raise InputValidationError("标注任务状态未登记", details={"status": status})
        return self._annotations.list_tasks(
            context.organization_id,
            context.project_id,
            limit=limit,
            offset=offset,
            dataset_id=dataset_id,
            status=status,
        )

    @transactional
    def transition_task(
        self,
        task_id: str,
        target: AnnotationTaskStatus,
        context: RequestContext,
        *,
        assignee_principal_id: str | None = None,
    ) -> AnnotationTask:
        self._require(context, "data.annotation.create")
        current = self._require_task(task_id, context)
        occurred_at = self._clock()
        try:
            updated = current.transition(target, occurred_at=occurred_at, assigned_to=assignee_principal_id)
        except ValueError as exc:
            raise InvalidStateError(str(exc)) from exc
        self._annotations.update_task(updated)
        if target == AnnotationTaskStatus.ASSIGNED:
            assignment = AnnotationAssignment(
                assignment_id=new_id("ana"),
                task_id=task_id,
                assignee_principal_id=updated.assigned_to or "",
                assigned_by=context.principal_id,
                assigned_at=occurred_at,
                provider_id=updated.provider_id,
            )
            self._annotations.add_assignment(assignment, context.organization_id, context.project_id)
        if target == AnnotationTaskStatus.SUBMITTED:
            self._emit(
                "annotation.submitted",
                context,
                occurred_at,
                {"task_id": task_id, "dataset_id": updated.dataset_id, "sample_count": len(updated.sample_ids)},
            )
        return updated

    def list_assignments(self, task_id: str, context: RequestContext) -> list[AnnotationAssignment]:
        self._require(context, "data.dataset.read")
        self._require_task(task_id, context)
        return self._annotations.list_assignments(task_id, context.organization_id, context.project_id)

    @transactional
    def review_task(
        self,
        task_id: str,
        *,
        decision: str,
        comment: str,
        context: RequestContext,
        revision_id: str | None = None,
        consistency_score: float | None = None,
    ) -> tuple[AnnotationTask, AnnotationReview]:
        self._require(context, "data.annotation.review")
        current = self._require_task(task_id, context)
        if current.status != AnnotationTaskStatus.SUBMITTED:
            raise InvalidStateError("只有已提交的标注任务可以复核")
        if decision not in {"approved", "rejected"}:
            raise InputValidationError("复核结论只能是批准或拒绝")
        resolved_revision = self._resolve_task_revision(current, context, revision_id)
        occurred_at = self._clock()
        target = (
            AnnotationTaskStatus.APPROVED if decision == "approved" else AnnotationTaskStatus.REJECTED
        )
        try:
            updated = current.transition(target, occurred_at=occurred_at)
        except ValueError as exc:
            raise InvalidStateError(str(exc)) from exc
        review = AnnotationReview(
            review_id=new_id("anv"),
            task_id=task_id,
            revision_id=resolved_revision.revision_id,
            decision=decision,  # type: ignore[arg-type]
            comment=comment,
            consistency_score=consistency_score,
            reviewed_by=context.principal_id,
            reviewed_at=occurred_at,
        )
        updated = updated.model_copy(update={"consistency_score": consistency_score, "review_comment": comment})
        self._annotations.update_task(updated)
        self._annotations.add_review(review, context.organization_id, context.project_id)
        if decision == "approved":
            self._accept_task_annotations(current, context, occurred_at)
        self._record_audit(
            "annotation.task.review", "annotation_task", task_id, context, before=current, after=updated
        )
        self._emit(
            "annotation.reviewed",
            context,
            occurred_at,
            {
                "task_id": task_id,
                "decision": decision,
                "revision_id": resolved_revision.revision_id,
                "status": updated.status,
            },
        )
        return updated, review

    def list_reviews(self, task_id: str, context: RequestContext) -> list[AnnotationReview]:
        self._require(context, "data.dataset.read")
        self._require_task(task_id, context)
        return self._annotations.list_reviews(task_id, context.organization_id, context.project_id)

    # ---------------------------------------------------------- 标注服务商

    @transactional
    def create_provider(
        self,
        *,
        name: str,
        provider_type: str,
        context: RequestContext,
        provider_id: str | None = None,
        config_ref: ObjectReference | None = None,
        endpoint: str | None = None,
    ) -> AnnotationProvider:
        self._require(context, "data.annotation.create")
        value = AnnotationProvider(
            provider_id=provider_id or new_id("anp"),
            name=name,
            provider_type=provider_type,
            config_ref=config_ref,
            endpoint=endpoint,
            created_at=self._clock(),
            updated_at=self._clock(),
        )
        try:
            self._annotations.add_provider(value, context.organization_id, context.project_id)
        except ValueError as exc:
            raise ConflictError("标注服务商标识已存在", details={"provider_id": value.provider_id}) from exc
        return value

    def list_providers(
        self, context: RequestContext, *, limit: int, offset: int
    ) -> tuple[list[AnnotationProvider], int]:
        self._require(context, "data.dataset.read")
        return self._annotations.list_providers(
            context.organization_id, context.project_id, limit=limit, offset=offset
        )

    @transactional
    def probe_provider(self, provider_id: str, context: RequestContext) -> AnnotationProvider:
        self._require(context, "data.annotation.create")
        current = self._require_provider(provider_id, context)
        updated = current.model_copy(
            update={"health": "configured" if current.endpoint else "unconfigured", "updated_at": self._clock()}
        )
        self._annotations.update_provider(updated, context.organization_id, context.project_id)
        self._record_audit(
            "annotation.provider.probe",
            "annotation_provider",
            provider_id,
            context,
            before=current,
            after=updated,
        )
        return updated

    # ------------------------------------------------------------ 发布冻结

    def freeze_for_version(
        self,
        *,
        dataset_version_id: str,
        sample_ids: Sequence[str],
        context: RequestContext,
        occurred_at: Any,
    ) -> tuple[AnnotationSnapshot, dict[str, list[tuple[str, str]]]]:
        """冻结版本内已接受的标注修订，返回快照和按样本分组的冻结条目。"""
        annotations = self._annotations.list_sample_annotations(
            sample_ids, context.organization_id, context.project_id
        )
        entries: list[tuple[str, str]] = []
        by_sample: dict[str, list[tuple[str, str]]] = {}
        for annotation in sorted(annotations, key=lambda item: item.annotation_id):
            if annotation.status != AnnotationStatus.ACCEPTED or annotation.accepted_revision_id is None:
                continue
            entry = (annotation.annotation_id, annotation.accepted_revision_id)
            entries.append(entry)
            by_sample.setdefault(annotation.sample_id, []).append(entry)
        snapshot = AnnotationSnapshot(
            snapshot_id=new_id("ans"),
            dataset_version_id=dataset_version_id,
            entries=tuple(entries),
            checksum=annotation_snapshot_checksum(entries),
            created_at=occurred_at,
        )
        self._annotations.add_annotation_snapshot(snapshot, context.organization_id, context.project_id)
        return snapshot, by_sample

    def get_annotation_snapshot(self, snapshot_id: str, context: RequestContext) -> AnnotationSnapshot:
        self._require(context, "data.dataset.read")
        try:
            return self._annotations.get_annotation_snapshot(
                snapshot_id, context.organization_id, context.project_id
            )
        except KeyError as exc:
            raise ResourceNotFoundError("annotation_snapshot", snapshot_id) from exc

    # ------------------------------------------------------------------ 内部

    def _accept_task_annotations(self, task: AnnotationTask, context: RequestContext, occurred_at: Any) -> None:
        annotations = self._annotations.list_sample_annotations(
            task.sample_ids, context.organization_id, context.project_id
        )
        for annotation in annotations:
            if annotation.task_id != task.task_id or annotation.status != AnnotationStatus.IN_REVIEW:
                continue
            self._annotations.update_annotation(
                annotation.review(
                    AnnotationStatus.ACCEPTED, reviewer=context.principal_id, occurred_at=occurred_at
                ),
                context.organization_id,
                context.project_id,
            )

    def _resolve_task_revision(
        self, task: AnnotationTask, context: RequestContext, revision_id: str | None
    ) -> AnnotationRevision:
        if revision_id is not None:
            try:
                revision = self._annotations.get_revision(
                    revision_id, context.organization_id, context.project_id
                )
            except KeyError as exc:
                raise ResourceNotFoundError("annotation_revision", revision_id) from exc
            if revision.task_id is not None and revision.task_id != task.task_id:
                raise InputValidationError(
                    "标注修订不属于该任务", details={"task_id": task.task_id, "revision_id": revision_id}
                )
            return revision
        candidates: list[AnnotationRevision] = []
        for annotation in self._annotations.list_sample_annotations(
            task.sample_ids, context.organization_id, context.project_id
        ):
            if annotation.task_id != task.task_id:
                continue
            candidates.extend(
                self._annotations.list_revisions(
                    annotation.annotation_id, context.organization_id, context.project_id
                )
            )
        if not candidates:
            raise InputValidationError("标注任务没有可复核的修订", details={"task_id": task.task_id})
        return max(candidates, key=lambda item: (item.created_at, item.revision_id))

    def _require_task(self, task_id: str, context: RequestContext) -> AnnotationTask:
        try:
            return self._annotations.get_task(task_id, context.organization_id, context.project_id)
        except KeyError as exc:
            raise ResourceNotFoundError("annotation_task", task_id) from exc

    def _require_provider(self, provider_id: str, context: RequestContext) -> AnnotationProvider:
        try:
            return self._annotations.get_provider(provider_id, context.organization_id, context.project_id)
        except KeyError as exc:
            raise ResourceNotFoundError("annotation_provider", provider_id) from exc

    def _require_sample(self, sample_id: str, context: RequestContext) -> None:
        try:
            self._samples.get_sample(sample_id, context.organization_id, context.project_id)
        except KeyError as exc:
            raise ResourceNotFoundError("sample", sample_id) from exc

    def _require_dataset(self, dataset_id: str, context: RequestContext) -> None:
        try:
            self._datasets.get_dataset(dataset_id, context.organization_id, context.project_id)
        except KeyError as exc:
            raise ResourceNotFoundError("dataset", dataset_id) from exc
