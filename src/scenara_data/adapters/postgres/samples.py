"""Sample 与版本样本成员关系的 PostgreSQL 实现。"""

from __future__ import annotations

from scenara_data.adapters.postgres._sql import SqlSupport
from scenara_data.domain.models import Sample


class SampleSqlMixin(SqlSupport):
    def add_sample(self, value: Sample, created_by: str) -> None:
        self._insert(
            """
            INSERT INTO data_samples
                (sample_id, tenant_id, project_id, created_by, created_at, dataset_split, payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                value.sample_id,
                value.tenant_id,
                value.project_id,
                created_by,
                value.created_at,
                value.dataset_split,
                self._json(value),
            ),
        )

    def get_sample(self, sample_id: str, organization_id: str, project_id: str) -> Sample:
        row = self._fetch_one(
            "SELECT payload FROM data_samples WHERE sample_id = %s AND tenant_id = %s AND project_id = %s",
            (sample_id, organization_id, project_id),
        )
        if row is None:
            raise KeyError(sample_id)
        return Sample.model_validate(row["payload"])

    def update_sample(self, value: Sample) -> None:
        updated = self._execute(
            """
            UPDATE data_samples
            SET payload = %s::jsonb, dataset_split = %s
            WHERE sample_id = %s AND tenant_id = %s AND project_id = %s
            """,
            (
                self._json(value),
                value.dataset_split,
                value.sample_id,
                value.tenant_id,
                value.project_id,
            ),
        )
        if updated == 0:
            raise KeyError(value.sample_id)

    def list_samples(
        self,
        organization_id: str,
        project_id: str,
        *,
        limit: int,
        offset: int,
        dataset_split: str | None = None,
    ) -> tuple[list[Sample], int]:
        rows, total = self._fetch_page(
            """
            SELECT payload, count(*) OVER () AS total
            FROM data_samples
            WHERE tenant_id = %s AND project_id = %s
              AND (%s::text IS NULL OR dataset_split = %s)
            ORDER BY created_at DESC, sample_id DESC
            LIMIT %s OFFSET %s
            """,
            (organization_id, project_id, dataset_split, dataset_split, limit, offset),
            """
            SELECT count(*) FROM data_samples
            WHERE tenant_id = %s AND project_id = %s
              AND (%s::text IS NULL OR dataset_split = %s)
            """,
            (organization_id, project_id, dataset_split, dataset_split),
        )
        return [Sample.model_validate(row["payload"]) for row in rows], total

    def add_sample_to_version(
        self, dataset_version_id: str, sample_id: str, organization_id: str, project_id: str
    ) -> None:
        inserted = self._insert_returning_count(
            """
            INSERT INTO data_dataset_version_samples
                (version_id, sample_id, tenant_id, project_id)
            SELECT v.version_id, s.sample_id, v.tenant_id, v.project_id
            FROM data_dataset_versions v
            JOIN data_samples s
              ON s.sample_id = %s
             AND s.tenant_id = v.tenant_id
             AND s.project_id = v.project_id
            WHERE v.version_id = %s AND v.tenant_id = %s AND v.project_id = %s
            """,
            (sample_id, dataset_version_id, organization_id, project_id),
        )
        if inserted == 0:
            raise KeyError(dataset_version_id)

    def restore_sample_to_version(
        self, dataset_version_id: str, sample_id: str, organization_id: str, project_id: str
    ) -> None:
        inserted = self._insert_returning_count(
            """
            INSERT INTO data_dataset_version_samples
                (version_id, sample_id, tenant_id, project_id)
            SELECT v.version_id, s.sample_id, v.tenant_id, v.project_id
            FROM data_dataset_versions v
            JOIN data_samples s
              ON s.sample_id = %s
             AND s.tenant_id = v.tenant_id
             AND s.project_id = v.project_id
            WHERE v.version_id = %s AND v.tenant_id = %s AND v.project_id = %s
            ON CONFLICT (version_id, sample_id) DO NOTHING
            """,
            (sample_id, dataset_version_id, organization_id, project_id),
        )
        if inserted == 0:
            existing = self._fetch_one(
                """
                SELECT 1 FROM data_dataset_version_samples
                WHERE version_id = %s AND sample_id = %s AND tenant_id = %s AND project_id = %s
                """,
                (dataset_version_id, sample_id, organization_id, project_id),
            )
            if existing is None:
                raise KeyError(dataset_version_id)

    def list_version_samples(
        self, dataset_version_id: str, organization_id: str, project_id: str
    ) -> list[Sample]:
        rows = self._fetch_all(
            """
            SELECT s.payload
            FROM data_dataset_version_samples dvs
            JOIN data_samples s
              ON s.sample_id = dvs.sample_id
             AND s.tenant_id = dvs.tenant_id
             AND s.project_id = dvs.project_id
            WHERE dvs.version_id = %s AND dvs.tenant_id = %s AND dvs.project_id = %s
            ORDER BY s.sample_id
            """,
            (dataset_version_id, organization_id, project_id),
        )
        return [Sample.model_validate(row["payload"]) for row in rows]
