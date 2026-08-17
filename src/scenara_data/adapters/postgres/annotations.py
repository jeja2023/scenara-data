"""标注、修订、任务、分派、复核、服务商与快照的 PostgreSQL 实现。"""

from __future__ import annotations

from collections.abc import Iterable

from scenara_data.adapters.postgres._sql import SqlSupport
from scenara_data.domain.models import (
    Annotation,
    AnnotationAssignment,
    AnnotationProvider,
    AnnotationReview,
    AnnotationRevision,
    AnnotationSnapshot,
    AnnotationTask,
)


class AnnotationSqlMixin(SqlSupport):
    def add_annotation(self, value: Annotation, organization_id: str, project_id: str) -> None:
        inserted = self._insert_returning_count(
            """
            INSERT INTO data_annotations
                (annotation_id, sample_id, tenant_id, project_id, status, created_at, payload)
            SELECT %s, s.sample_id, s.tenant_id, s.project_id, %s, %s, %s::jsonb
            FROM data_samples s
            WHERE s.sample_id = %s AND s.tenant_id = %s AND s.project_id = %s
            """,
            (
                value.annotation_id,
                value.status,
                value.created_at,
                self._json(value),
                value.sample_id,
                organization_id,
                project_id,
            ),
        )
        if inserted == 0:
            raise KeyError(value.sample_id)

    def get_annotation(self, annotation_id: str, organization_id: str, project_id: str) -> Annotation:
        row = self._fetch_one(
            """
            SELECT payload FROM data_annotations
            WHERE annotation_id = %s AND tenant_id = %s AND project_id = %s
            """,
            (annotation_id, organization_id, project_id),
        )
        if row is None:
            raise KeyError(annotation_id)
        return Annotation.model_validate(row["payload"])

    def update_annotation(self, value: Annotation, organization_id: str, project_id: str) -> None:
        updated = self._execute(
            """
            UPDATE data_annotations SET status = %s, payload = %s::jsonb
            WHERE annotation_id = %s AND tenant_id = %s AND project_id = %s
            """,
            (value.status, self._json(value), value.annotation_id, organization_id, project_id),
        )
        if updated == 0:
            raise KeyError(value.annotation_id)

    def list_annotations(
        self, sample_id: str, organization_id: str, project_id: str, *, limit: int, offset: int
    ) -> tuple[list[Annotation], int]:
        rows, total = self._fetch_page(
            """
            SELECT payload, count(*) OVER () AS total
            FROM data_annotations
            WHERE sample_id = %s AND tenant_id = %s AND project_id = %s
            ORDER BY created_at DESC, annotation_id DESC
            LIMIT %s OFFSET %s
            """,
            (sample_id, organization_id, project_id, limit, offset),
            """
            SELECT count(*) FROM data_annotations
            WHERE sample_id = %s AND tenant_id = %s AND project_id = %s
            """,
            (sample_id, organization_id, project_id),
        )
        return [Annotation.model_validate(row["payload"]) for row in rows], total

    def list_sample_annotations(
        self, sample_ids: Iterable[str], organization_id: str, project_id: str
    ) -> list[Annotation]:
        wanted = list(dict.fromkeys(sample_ids))
        if not wanted:
            return []
        rows = self._fetch_all(
            """
            SELECT payload FROM data_annotations
            WHERE tenant_id = %s AND project_id = %s AND sample_id = ANY(%s)
            ORDER BY created_at, annotation_id
            """,
            (organization_id, project_id, wanted),
        )
        return [Annotation.model_validate(row["payload"]) for row in rows]

    def add_revision(self, value: AnnotationRevision, organization_id: str, project_id: str) -> None:
        inserted = self._insert_returning_count(
            """
            INSERT INTO data_annotation_revisions
                (revision_id, annotation_id, tenant_id, project_id, revision_number, created_at, payload)
            SELECT %s, a.annotation_id, a.tenant_id, a.project_id, %s, %s, %s::jsonb
            FROM data_annotations a
            WHERE a.annotation_id = %s AND a.tenant_id = %s AND a.project_id = %s
            """,
            (
                value.revision_id,
                value.revision_number,
                value.created_at,
                self._json(value),
                value.annotation_id,
                organization_id,
                project_id,
            ),
        )
        if inserted == 0:
            raise KeyError(value.annotation_id)

    def list_revisions(
        self, annotation_id: str, organization_id: str, project_id: str
    ) -> list[AnnotationRevision]:
        rows = self._fetch_all(
            """
            SELECT payload FROM data_annotation_revisions
            WHERE annotation_id = %s AND tenant_id = %s AND project_id = %s
            ORDER BY revision_number
            """,
            (annotation_id, organization_id, project_id),
        )
        return [AnnotationRevision.model_validate(row["payload"]) for row in rows]

    def get_revision(self, revision_id: str, organization_id: str, project_id: str) -> AnnotationRevision:
        row = self._fetch_one(
            """
            SELECT payload FROM data_annotation_revisions
            WHERE revision_id = %s AND tenant_id = %s AND project_id = %s
            """,
            (revision_id, organization_id, project_id),
        )
        if row is None:
            raise KeyError(revision_id)
        return AnnotationRevision.model_validate(row["payload"])

    def add_task(self, value: AnnotationTask) -> None:
        inserted = self._insert_returning_count(
            """
            INSERT INTO data_annotation_tasks
                (task_id, dataset_id, tenant_id, project_id, status, created_at, payload)
            SELECT %s, d.dataset_id, d.tenant_id, d.project_id, %s, %s, %s::jsonb
            FROM data_datasets d
            WHERE d.dataset_id = %s AND d.tenant_id = %s AND d.project_id = %s
            """,
            (
                value.task_id,
                value.status,
                value.created_at,
                self._json(value),
                value.dataset_id,
                value.tenant_id,
                value.project_id,
            ),
        )
        if inserted == 0:
            raise KeyError(value.dataset_id)

    def get_task(self, task_id: str, organization_id: str, project_id: str) -> AnnotationTask:
        row = self._fetch_one(
            """
            SELECT payload FROM data_annotation_tasks
            WHERE task_id = %s AND tenant_id = %s AND project_id = %s
            """,
            (task_id, organization_id, project_id),
        )
        if row is None:
            raise KeyError(task_id)
        return AnnotationTask.model_validate(row["payload"])

    def update_task(self, value: AnnotationTask) -> None:
        updated = self._execute(
            """
            UPDATE data_annotation_tasks SET status = %s, payload = %s::jsonb
            WHERE task_id = %s AND tenant_id = %s AND project_id = %s
            """,
            (value.status, self._json(value), value.task_id, value.tenant_id, value.project_id),
        )
        if updated == 0:
            raise KeyError(value.task_id)

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
        filters = """
            WHERE tenant_id = %s AND project_id = %s
              AND (%s::text IS NULL OR dataset_id = %s)
              AND (%s::text IS NULL OR status = %s)
        """
        scope = (organization_id, project_id, dataset_id, dataset_id, status, status)
        rows, total = self._fetch_page(
            f"""
            SELECT payload, count(*) OVER () AS total
            FROM data_annotation_tasks
            {filters}
            ORDER BY created_at DESC, task_id DESC
            LIMIT %s OFFSET %s
            """,
            (*scope, limit, offset),
            f"SELECT count(*) FROM data_annotation_tasks {filters}",
            scope,
        )
        return [AnnotationTask.model_validate(row["payload"]) for row in rows], total

    def add_assignment(self, value: AnnotationAssignment, organization_id: str, project_id: str) -> None:
        inserted = self._insert_returning_count(
            """
            INSERT INTO data_annotation_assignments
                (assignment_id, task_id, tenant_id, project_id, created_at, payload)
            SELECT %s, t.task_id, t.tenant_id, t.project_id, %s, %s::jsonb
            FROM data_annotation_tasks t
            WHERE t.task_id = %s AND t.tenant_id = %s AND t.project_id = %s
            """,
            (
                value.assignment_id,
                value.assigned_at,
                self._json(value),
                value.task_id,
                organization_id,
                project_id,
            ),
        )
        if inserted == 0:
            raise KeyError(value.task_id)

    def list_assignments(
        self, task_id: str, organization_id: str, project_id: str
    ) -> list[AnnotationAssignment]:
        rows = self._fetch_all(
            """
            SELECT payload FROM data_annotation_assignments
            WHERE task_id = %s AND tenant_id = %s AND project_id = %s
            ORDER BY created_at, assignment_id
            """,
            (task_id, organization_id, project_id),
        )
        return [AnnotationAssignment.model_validate(row["payload"]) for row in rows]

    def add_review(self, value: AnnotationReview, organization_id: str, project_id: str) -> None:
        inserted = self._insert_returning_count(
            """
            INSERT INTO data_annotation_reviews
                (review_id, task_id, revision_id, tenant_id, project_id, reviewed_at, payload)
            SELECT %s, t.task_id, r.revision_id, t.tenant_id, t.project_id, %s, %s::jsonb
            FROM data_annotation_tasks t
            JOIN data_annotation_revisions r
              ON r.revision_id = %s AND r.tenant_id = t.tenant_id AND r.project_id = t.project_id
            WHERE t.task_id = %s AND t.tenant_id = %s AND t.project_id = %s
            """,
            (
                value.review_id,
                value.reviewed_at,
                self._json(value),
                value.revision_id,
                value.task_id,
                organization_id,
                project_id,
            ),
        )
        if inserted == 0:
            raise KeyError(value.task_id)

    def list_reviews(self, task_id: str, organization_id: str, project_id: str) -> list[AnnotationReview]:
        rows = self._fetch_all(
            """
            SELECT payload FROM data_annotation_reviews
            WHERE task_id = %s AND tenant_id = %s AND project_id = %s
            ORDER BY reviewed_at, review_id
            """,
            (task_id, organization_id, project_id),
        )
        return [AnnotationReview.model_validate(row["payload"]) for row in rows]

    def add_provider(self, value: AnnotationProvider, organization_id: str, project_id: str) -> None:
        self._insert(
            """
            INSERT INTO data_annotation_providers
                (provider_id, tenant_id, project_id, created_at, payload)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            """,
            (value.provider_id, organization_id, project_id, value.created_at, self._json(value)),
        )

    def get_provider(self, provider_id: str, organization_id: str, project_id: str) -> AnnotationProvider:
        row = self._fetch_one(
            """
            SELECT payload FROM data_annotation_providers
            WHERE provider_id = %s AND tenant_id = %s AND project_id = %s
            """,
            (provider_id, organization_id, project_id),
        )
        if row is None:
            raise KeyError(provider_id)
        return AnnotationProvider.model_validate(row["payload"])

    def update_provider(
        self, value: AnnotationProvider, organization_id: str, project_id: str
    ) -> None:
        updated = self._execute(
            """
            UPDATE data_annotation_providers SET payload = %s::jsonb
            WHERE provider_id = %s AND tenant_id = %s AND project_id = %s
            """,
            (self._json(value), value.provider_id, organization_id, project_id),
        )
        if updated == 0:
            raise KeyError(value.provider_id)

    def list_providers(
        self, organization_id: str, project_id: str, *, limit: int, offset: int
    ) -> tuple[list[AnnotationProvider], int]:
        rows, total = self._fetch_page(
            """
            SELECT payload, count(*) OVER () AS total
            FROM data_annotation_providers
            WHERE tenant_id = %s AND project_id = %s
            ORDER BY created_at, provider_id
            LIMIT %s OFFSET %s
            """,
            (organization_id, project_id, limit, offset),
            "SELECT count(*) FROM data_annotation_providers WHERE tenant_id = %s AND project_id = %s",
            (organization_id, project_id),
        )
        return [AnnotationProvider.model_validate(row["payload"]) for row in rows], total

    def add_annotation_snapshot(
        self, value: AnnotationSnapshot, organization_id: str, project_id: str
    ) -> None:
        inserted = self._insert_returning_count(
            """
            INSERT INTO data_annotation_snapshots
                (snapshot_id, version_id, tenant_id, project_id, checksum, created_at, payload)
            SELECT %s, v.version_id, v.tenant_id, v.project_id, %s, %s, %s::jsonb
            FROM data_dataset_versions v
            WHERE v.version_id = %s AND v.tenant_id = %s AND v.project_id = %s
            """,
            (
                value.snapshot_id,
                value.checksum,
                value.created_at,
                self._json(value),
                value.dataset_version_id,
                organization_id,
                project_id,
            ),
        )
        if inserted == 0:
            raise KeyError(value.dataset_version_id)

    def get_annotation_snapshot(
        self, snapshot_id: str, organization_id: str, project_id: str
    ) -> AnnotationSnapshot:
        row = self._fetch_one(
            """
            SELECT payload FROM data_annotation_snapshots
            WHERE snapshot_id = %s AND tenant_id = %s AND project_id = %s
            """,
            (snapshot_id, organization_id, project_id),
        )
        if row is None:
            raise KeyError(snapshot_id)
        return AnnotationSnapshot.model_validate(row["payload"])
