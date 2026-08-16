"""内存数据仓储：实现 `DataRepository` 全部子端口的开发适配器。"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from threading import RLock

from scenara_data.adapters.memory._tables import Table
from scenara_data.domain.models import (
    Annotation,
    AnnotationAssignment,
    AnnotationProvider,
    AnnotationReview,
    AnnotationRevision,
    AnnotationSnapshot,
    AnnotationTask,
    DataQualityReport,
    Dataset,
    DatasetAccessGrant,
    DatasetVersion,
    DatasetVersionStatus,
    HardSampleImport,
    LineageLink,
    LineageSnapshot,
    MigrationReport,
    QualityIssue,
    QualityRule,
    QualityRun,
    Sample,
)

PUBLISHED_STATES = {DatasetVersionStatus.PUBLISHED, DatasetVersionStatus.ARCHIVED}


class InMemoryDataRepository:
    """Deterministic development adapter; never a production fact store."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._transaction_depth = 0
        self._transaction_snapshot: tuple[dict[str, object], list[tuple[object, object]]] | None = None
        self._transaction_participants: list[object] = []
        self._datasets: Table[Dataset] = Table("dataset", lambda value: value.dataset_id)
        self._versions: Table[DatasetVersion] = Table(
            "dataset_version",
            lambda value: value.dataset_version_id,
            unique=(lambda value: (value.dataset_id, value.version),),
        )
        self._version_samples: dict[str, list[str]] = {}
        self._samples: Table[Sample] = Table("sample", lambda value: value.sample_id)
        self._sample_creators: dict[str, str] = {}
        self._annotations: Table[Annotation] = Table("annotation", lambda value: value.annotation_id)
        self._revisions: Table[AnnotationRevision] = Table(
            "annotation_revision",
            lambda value: value.revision_id,
            unique=(lambda value: (value.annotation_id, value.revision_number),),
        )
        self._tasks: Table[AnnotationTask] = Table("annotation_task", lambda value: value.task_id)
        self._assignments: Table[AnnotationAssignment] = Table(
            "annotation_assignment", lambda value: value.assignment_id
        )
        self._reviews: Table[AnnotationReview] = Table("annotation_review", lambda value: value.review_id)
        self._providers: Table[AnnotationProvider] = Table(
            "annotation_provider", lambda value: value.provider_id
        )
        self._annotation_snapshots: Table[AnnotationSnapshot] = Table(
            "annotation_snapshot", lambda value: value.snapshot_id
        )
        self._quality_rules: Table[QualityRule] = Table("quality_rule", lambda value: value.rule_id)
        self._quality_runs: Table[QualityRun] = Table("quality_run", lambda value: value.run_id)
        self._quality_issues: Table[QualityIssue] = Table("quality_issue", lambda value: value.issue_id)
        self._quality_reports: Table[DataQualityReport] = Table(
            "quality_report", lambda value: value.report_id
        )
        self._lineage: Table[LineageLink] = Table("lineage_edge", lambda value: value.lineage_id)
        self._lineage_snapshots: Table[LineageSnapshot] = Table(
            "lineage_snapshot", lambda value: value.snapshot_id
        )
        self._hard_sample_imports: Table[HardSampleImport] = Table(
            "hard_sample_import",
            lambda value: value.import_id,
            unique=(lambda value: (value.manifest_id,),),
        )
        self._migration_reports: Table[MigrationReport] = Table(
            "migration_report",
            lambda value: value.migration_id,
            unique=(lambda value: (value.package_checksum,),),
        )
        self._access_grants: Table[DatasetAccessGrant] = Table(
            "dataset_access_grant", lambda value: value.grant_id
        )

    def register_transaction_participant(self, participant: object) -> None:
        """让内存适配器的辅助事实（审计、Outbox、幂等）共享回滚边界。"""
        if not hasattr(participant, "_transaction_snapshot") or not hasattr(participant, "_transaction_restore"):
            raise TypeError("transaction participant must provide snapshot and restore hooks")
        self._transaction_participants.append(participant)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            outermost = self._transaction_depth == 0
            if outermost:
                self._transaction_snapshot = self._snapshot()
            self._transaction_depth += 1
            try:
                yield
            except Exception:
                if outermost and self._transaction_snapshot is not None:
                    self._restore(self._transaction_snapshot)
                raise
            finally:
                self._transaction_depth -= 1
                if outermost:
                    self._transaction_snapshot = None

    def ping(self) -> bool:
        return True

    def _snapshot(self) -> tuple[dict[str, object], list[tuple[object, object]]]:
        tables: dict[str, object] = {
            name: (dict(table.rows), dict(table.scopes))
            for name, table in self._tables().items()
        }
        tables["_version_samples"] = {
            key: list(value) for key, value in self._version_samples.items()
        }
        tables["_sample_creators"] = dict(self._sample_creators)
        participants = [
            (participant, participant._transaction_snapshot())  # type: ignore[attr-defined]
            for participant in self._transaction_participants
        ]
        return tables, participants

    def _restore(self, snapshot: tuple[dict[str, object], list[tuple[object, object]]]) -> None:
        tables, participants = snapshot
        for name, table in self._tables().items():
            rows, scopes = tables[name]  # type: ignore[misc]
            table.rows = dict(rows)
            table.scopes = dict(scopes)
        self._version_samples = {
            key: list(value)
            for key, value in tables["_version_samples"].items()  # type: ignore[union-attr]
        }
        self._sample_creators = dict(tables["_sample_creators"])  # type: ignore[arg-type]
        for participant, participant_snapshot in participants:
            participant._transaction_restore(participant_snapshot)  # type: ignore[attr-defined]

    def _tables(self) -> dict[str, Table[object]]:
        return {
            "_datasets": self._datasets,
            "_versions": self._versions,
            "_samples": self._samples,
            "_annotations": self._annotations,
            "_revisions": self._revisions,
            "_tasks": self._tasks,
            "_assignments": self._assignments,
            "_reviews": self._reviews,
            "_providers": self._providers,
            "_annotation_snapshots": self._annotation_snapshots,
            "_quality_rules": self._quality_rules,
            "_quality_runs": self._quality_runs,
            "_quality_issues": self._quality_issues,
            "_quality_reports": self._quality_reports,
            "_lineage": self._lineage,
            "_lineage_snapshots": self._lineage_snapshots,
            "_hard_sample_imports": self._hard_sample_imports,
            "_migration_reports": self._migration_reports,
            "_access_grants": self._access_grants,
        }

    # ---------------------------------------------------------------- Dataset

    def add_dataset(self, value: Dataset) -> None:
        self._datasets.add(value, (value.tenant_id, value.project_id))

    def get_dataset(self, dataset_id: str, organization_id: str, project_id: str) -> Dataset:
        return self._datasets.get(dataset_id, (organization_id, project_id))

    def list_datasets(
        self, organization_id: str, project_id: str, *, limit: int, offset: int
    ) -> tuple[list[Dataset], int]:
        return self._datasets.page(
            (organization_id, project_id),
            limit=limit,
            offset=offset,
            sort_key=lambda value: (value.created_at, value.dataset_id),
        )

    def update_dataset(self, value: Dataset) -> None:
        self._datasets.update(value)

    def add_dataset_version(self, value: DatasetVersion, organization_id: str, project_id: str) -> None:
        scope = (organization_id, project_id)
        self._datasets.get(value.dataset_id, scope)
        with self._lock:
            self._versions.add(value, scope)
            self._version_samples[value.dataset_version_id] = []

    def get_dataset_version(
        self, dataset_version_id: str, organization_id: str, project_id: str
    ) -> DatasetVersion:
        return self._versions.get(dataset_version_id, (organization_id, project_id))

    def list_dataset_versions(
        self, dataset_id: str, organization_id: str, project_id: str, *, limit: int, offset: int
    ) -> tuple[list[DatasetVersion], int]:
        self.get_dataset(dataset_id, organization_id, project_id)
        return self._versions.page(
            (organization_id, project_id),
            limit=limit,
            offset=offset,
            predicate=lambda value: value.dataset_id == dataset_id,
            sort_key=lambda value: (value.created_at, value.dataset_version_id),
        )

    def update_dataset_version(self, value: DatasetVersion, organization_id: str, project_id: str) -> None:
        with self._lock:
            self._versions.get(value.dataset_version_id, (organization_id, project_id))
            previous = self._versions.rows.get(value.dataset_version_id)
            if previous is None:
                raise KeyError(value.dataset_version_id)
            _assert_version_mutable(previous, value)
            self._versions.update(value)

    def add_access_grant(self, value: DatasetAccessGrant, organization_id: str, project_id: str) -> None:
        self.get_dataset_version(value.dataset_version_id, organization_id, project_id)
        self._access_grants.add(value, (organization_id, project_id))

    def get_access_grant(self, grant_id: str, organization_id: str, project_id: str) -> DatasetAccessGrant:
        return self._access_grants.get(grant_id, (organization_id, project_id))

    def list_access_grants(
        self, dataset_version_id: str, organization_id: str, project_id: str
    ) -> list[DatasetAccessGrant]:
        return self._access_grants.select(
            (organization_id, project_id),
            predicate=lambda value: value.dataset_version_id == dataset_version_id,
            sort_key=lambda value: (value.created_at, value.grant_id),
        )

    # ----------------------------------------------------------------- Sample

    def add_sample(self, value: Sample, created_by: str) -> None:
        with self._lock:
            self._samples.add(value, (value.tenant_id, value.project_id))
            self._sample_creators[value.sample_id] = created_by

    def get_sample(self, sample_id: str, organization_id: str, project_id: str) -> Sample:
        return self._samples.get(sample_id, (organization_id, project_id))

    def update_sample(self, value: Sample) -> None:
        self._samples.update(value)

    def list_samples(
        self,
        organization_id: str,
        project_id: str,
        *,
        limit: int,
        offset: int,
        dataset_split: str | None = None,
    ) -> tuple[list[Sample], int]:
        return self._samples.page(
            (organization_id, project_id),
            limit=limit,
            offset=offset,
            predicate=None if dataset_split is None else (lambda value: value.dataset_split == dataset_split),
            sort_key=lambda value: (value.created_at, value.sample_id),
        )

    def add_sample_to_version(
        self, dataset_version_id: str, sample_id: str, organization_id: str, project_id: str
    ) -> None:
        with self._lock:
            members = self._version_samples.get(dataset_version_id)
            scope = self._versions.scope_of(dataset_version_id)
            if members is None or scope != (organization_id, project_id):
                raise KeyError(dataset_version_id)
            if self._samples.find(sample_id, scope) is None:
                raise KeyError(sample_id)
            version = self._versions.rows[dataset_version_id]
            if version.status != DatasetVersionStatus.BUILDING:
                raise ValueError("dataset version sample membership is mutable only while building")
            if sample_id in members:
                raise ValueError("duplicate version sample")
            members.append(sample_id)

    def restore_sample_to_version(
        self, dataset_version_id: str, sample_id: str, organization_id: str, project_id: str
    ) -> None:
        with self._lock:
            members = self._version_samples.get(dataset_version_id)
            scope = self._versions.scope_of(dataset_version_id)
            if members is None or scope != (organization_id, project_id):
                raise KeyError(dataset_version_id)
            if self._samples.find(sample_id, scope) is None:
                raise KeyError(sample_id)
            if sample_id not in members:
                members.append(sample_id)

    def list_version_samples(
        self, dataset_version_id: str, organization_id: str, project_id: str
    ) -> list[Sample]:
        self.get_dataset_version(dataset_version_id, organization_id, project_id)
        members = self._version_samples.get(dataset_version_id, [])
        return [self.get_sample(item, organization_id, project_id) for item in sorted(members)]

    # ------------------------------------------------------------- Annotation

    def add_annotation(self, value: Annotation, organization_id: str, project_id: str) -> None:
        self.get_sample(value.sample_id, organization_id, project_id)
        self._annotations.add(value, (organization_id, project_id))

    def get_annotation(self, annotation_id: str, organization_id: str, project_id: str) -> Annotation:
        return self._annotations.get(annotation_id, (organization_id, project_id))

    def update_annotation(self, value: Annotation, organization_id: str, project_id: str) -> None:
        self._annotations.get(value.annotation_id, (organization_id, project_id))
        self._annotations.update(value)

    def list_annotations(
        self, sample_id: str, organization_id: str, project_id: str, *, limit: int, offset: int
    ) -> tuple[list[Annotation], int]:
        return self._annotations.page(
            (organization_id, project_id),
            limit=limit,
            offset=offset,
            predicate=lambda value: value.sample_id == sample_id,
            sort_key=lambda value: (value.created_at, value.annotation_id),
        )

    def list_sample_annotations(
        self, sample_ids: Iterable[str], organization_id: str, project_id: str
    ) -> list[Annotation]:
        wanted = set(sample_ids)
        return self._annotations.select(
            (organization_id, project_id),
            predicate=lambda value: value.sample_id in wanted,
            sort_key=lambda value: (value.created_at, value.annotation_id),
        )

    def add_revision(self, value: AnnotationRevision, organization_id: str, project_id: str) -> None:
        self.get_annotation(value.annotation_id, organization_id, project_id)
        self._revisions.add(value, (organization_id, project_id))

    def list_revisions(
        self, annotation_id: str, organization_id: str, project_id: str
    ) -> list[AnnotationRevision]:
        return self._revisions.select(
            (organization_id, project_id),
            predicate=lambda value: value.annotation_id == annotation_id,
            sort_key=lambda value: value.revision_number,
        )

    def get_revision(self, revision_id: str, organization_id: str, project_id: str) -> AnnotationRevision:
        return self._revisions.get(revision_id, (organization_id, project_id))

    def add_task(self, value: AnnotationTask) -> None:
        self._tasks.add(value, (value.tenant_id, value.project_id))

    def get_task(self, task_id: str, organization_id: str, project_id: str) -> AnnotationTask:
        return self._tasks.get(task_id, (organization_id, project_id))

    def update_task(self, value: AnnotationTask) -> None:
        self._tasks.get(value.task_id, (value.tenant_id, value.project_id))
        self._tasks.update(value)

    def list_tasks(
        self,
        organization_id: str,
        project_id: str,
        *,
        limit: int,
        offset: int,
        dataset_id: str | None = None,
        status: str | None = None,
    ) -> tuple[list[AnnotationTask], int]:
        def matches(value: AnnotationTask) -> bool:
            if dataset_id is not None and value.dataset_id != dataset_id:
                return False
            return not (status is not None and value.status != status)

        return self._tasks.page(
            (organization_id, project_id),
            limit=limit,
            offset=offset,
            predicate=matches,
            sort_key=lambda value: (value.created_at, value.task_id),
        )

    def add_assignment(self, value: AnnotationAssignment, organization_id: str, project_id: str) -> None:
        self.get_task(value.task_id, organization_id, project_id)
        self._assignments.add(value, (organization_id, project_id))

    def list_assignments(
        self, task_id: str, organization_id: str, project_id: str
    ) -> list[AnnotationAssignment]:
        return self._assignments.select(
            (organization_id, project_id),
            predicate=lambda value: value.task_id == task_id,
            sort_key=lambda value: (value.assigned_at, value.assignment_id),
        )

    def add_review(self, value: AnnotationReview, organization_id: str, project_id: str) -> None:
        self.get_task(value.task_id, organization_id, project_id)
        self._reviews.add(value, (organization_id, project_id))

    def list_reviews(self, task_id: str, organization_id: str, project_id: str) -> list[AnnotationReview]:
        return self._reviews.select(
            (organization_id, project_id),
            predicate=lambda value: value.task_id == task_id,
            sort_key=lambda value: (value.reviewed_at, value.review_id),
        )

    def add_provider(self, value: AnnotationProvider, organization_id: str, project_id: str) -> None:
        self._providers.add(value, (organization_id, project_id))

    def get_provider(self, provider_id: str, organization_id: str, project_id: str) -> AnnotationProvider:
        return self._providers.get(provider_id, (organization_id, project_id))

    def update_provider(
        self, value: AnnotationProvider, organization_id: str, project_id: str
    ) -> None:
        self._providers.get(value.provider_id, (organization_id, project_id))
        self._providers.update(value)

    def list_providers(
        self, organization_id: str, project_id: str, *, limit: int, offset: int
    ) -> tuple[list[AnnotationProvider], int]:
        return self._providers.page(
            (organization_id, project_id),
            limit=limit,
            offset=offset,
            sort_key=lambda value: (value.created_at, value.provider_id),
        )

    def add_annotation_snapshot(
        self, value: AnnotationSnapshot, organization_id: str, project_id: str
    ) -> None:
        self._annotation_snapshots.add(value, (organization_id, project_id))

    def get_annotation_snapshot(
        self, snapshot_id: str, organization_id: str, project_id: str
    ) -> AnnotationSnapshot:
        return self._annotation_snapshots.get(snapshot_id, (organization_id, project_id))

    # ---------------------------------------------------------------- Quality

    def add_quality_rule(self, value: QualityRule, organization_id: str, project_id: str) -> None:
        self._quality_rules.add(value, (organization_id, project_id))

    def get_quality_rule(self, rule_id: str, organization_id: str, project_id: str) -> QualityRule:
        return self._quality_rules.get(rule_id, (organization_id, project_id))

    def list_quality_rules(
        self, organization_id: str, project_id: str, *, limit: int, offset: int
    ) -> tuple[list[QualityRule], int]:
        return self._quality_rules.page(
            (organization_id, project_id), limit=limit, offset=offset, sort_key=lambda value: value.rule_id, reverse=False
        )

    def add_quality_run(self, value: QualityRun, organization_id: str, project_id: str) -> None:
        self.get_dataset_version(value.dataset_version_id, organization_id, project_id)
        self._quality_runs.add(value, (organization_id, project_id))

    def get_quality_run(self, run_id: str, organization_id: str, project_id: str) -> QualityRun:
        return self._quality_runs.get(run_id, (organization_id, project_id))

    def update_quality_run(self, value: QualityRun, organization_id: str, project_id: str) -> None:
        self._quality_runs.get(value.run_id, (organization_id, project_id))
        self._quality_runs.update(value)

    def list_quality_runs(
        self, dataset_version_id: str, organization_id: str, project_id: str, *, limit: int, offset: int
    ) -> tuple[list[QualityRun], int]:
        return self._quality_runs.page(
            (organization_id, project_id),
            limit=limit,
            offset=offset,
            predicate=lambda value: value.dataset_version_id == dataset_version_id,
            sort_key=lambda value: (value.created_at, value.run_id),
        )

    def add_quality_issue(self, value: QualityIssue, organization_id: str, project_id: str) -> None:
        self.get_quality_run(value.quality_run_id, organization_id, project_id)
        self._quality_issues.add(value, (organization_id, project_id))

    def list_quality_issues(
        self, quality_run_id: str, organization_id: str, project_id: str
    ) -> list[QualityIssue]:
        return self._quality_issues.select(
            (organization_id, project_id),
            predicate=lambda value: value.quality_run_id == quality_run_id,
            sort_key=lambda value: value.issue_id,
        )

    def add_quality_report(
        self, value: DataQualityReport, organization_id: str, project_id: str
    ) -> None:
        self.get_dataset_version(value.dataset_version_id, organization_id, project_id)
        self._quality_reports.add(value, (organization_id, project_id))

    def get_quality_report(
        self, report_id: str, organization_id: str, project_id: str
    ) -> DataQualityReport:
        return self._quality_reports.get(report_id, (organization_id, project_id))

    # ---------------------------------------------------------------- Lineage

    def add_lineage_link(self, value: LineageLink, organization_id: str, project_id: str) -> None:
        self._lineage.add(value, (organization_id, project_id))

    def list_lineage(self, entity_id: str, organization_id: str, project_id: str) -> list[LineageLink]:
        return self._lineage.select(
            (organization_id, project_id),
            predicate=lambda value: entity_id in {value.source_entity_id, value.target_entity_id},
            sort_key=lambda value: (value.created_at, value.lineage_id),
        )

    def add_lineage_snapshot(
        self, value: LineageSnapshot, organization_id: str, project_id: str
    ) -> None:
        self._lineage_snapshots.add(value, (organization_id, project_id))

    def get_lineage_snapshot(
        self, snapshot_id: str, organization_id: str, project_id: str
    ) -> LineageSnapshot:
        return self._lineage_snapshots.get(snapshot_id, (organization_id, project_id))

    # ------------------------------------------------------------ Hard Sample

    def add_hard_sample_import(
        self, value: HardSampleImport, organization_id: str, project_id: str
    ) -> None:
        self._hard_sample_imports.add(value, (organization_id, project_id))

    def get_hard_sample_import(
        self, import_id: str, organization_id: str, project_id: str
    ) -> HardSampleImport:
        return self._hard_sample_imports.get(import_id, (organization_id, project_id))

    def find_hard_sample_import_by_manifest(
        self, manifest_id: str, organization_id: str, project_id: str
    ) -> HardSampleImport | None:
        matches = self._hard_sample_imports.select(
            (organization_id, project_id), predicate=lambda value: value.manifest_id == manifest_id
        )
        return matches[0] if matches else None

    def update_hard_sample_import(
        self, value: HardSampleImport, organization_id: str, project_id: str
    ) -> None:
        self._hard_sample_imports.get(value.import_id, (organization_id, project_id))
        self._hard_sample_imports.update(value)

    # -------------------------------------------------------------- Migration

    def add_migration_report(
        self, value: MigrationReport, organization_id: str, project_id: str
    ) -> None:
        self._migration_reports.add(value, (organization_id, project_id))

    def get_migration_report(
        self, migration_id: str, organization_id: str, project_id: str
    ) -> MigrationReport:
        return self._migration_reports.get(migration_id, (organization_id, project_id))

    def find_migration_report_by_checksum(
        self, package_checksum: str, organization_id: str, project_id: str
    ) -> MigrationReport | None:
        matches = self._migration_reports.select(
            (organization_id, project_id),
            predicate=lambda value: value.package_checksum == package_checksum,
        )
        return matches[0] if matches else None

    def update_migration_report(
        self, value: MigrationReport, organization_id: str, project_id: str
    ) -> None:
        self._migration_reports.get(value.migration_id, (organization_id, project_id))
        self._migration_reports.update(value)


def _assert_version_mutable(previous: DatasetVersion, incoming: DatasetVersion) -> None:
    """已发布版本只允许 published -> archived，且不可改动不可变字段。"""
    if previous.status not in PUBLISHED_STATES:
        return
    if previous.status == DatasetVersionStatus.ARCHIVED:
        raise ValueError("archived dataset version is immutable")
    frozen = ("manifest_ref", "manifest_sha256", "published_at", "sample_count", "version")
    if incoming.status != DatasetVersionStatus.ARCHIVED or any(
        getattr(previous, field) != getattr(incoming, field) for field in frozen
    ):
        raise ValueError("published dataset version is immutable")

