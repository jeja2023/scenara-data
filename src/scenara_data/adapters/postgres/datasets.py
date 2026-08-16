"""Dataset、Dataset Version 与访问授权的 PostgreSQL 实现。"""

from __future__ import annotations

from scenara_data.adapters.postgres._sql import SqlSupport
from scenara_data.domain.models import Dataset, DatasetAccessGrant, DatasetVersion


class DatasetSqlMixin(SqlSupport):
    def add_dataset(self, value: Dataset) -> None:
        self._insert(
            """
            INSERT INTO data_datasets
                (dataset_id, tenant_id, project_id, status, created_at, payload)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                value.dataset_id,
                value.tenant_id,
                value.project_id,
                value.status,
                value.created_at,
                self._json(value),
            ),
        )

    def get_dataset(self, dataset_id: str, organization_id: str, project_id: str) -> Dataset:
        row = self._fetch_one(
            """
            SELECT payload FROM data_datasets
            WHERE dataset_id = %s AND tenant_id = %s AND project_id = %s
            """,
            (dataset_id, organization_id, project_id),
        )
        if row is None:
            raise KeyError(dataset_id)
        return Dataset.model_validate(row["payload"])

    def list_datasets(
        self, organization_id: str, project_id: str, *, limit: int, offset: int
    ) -> tuple[list[Dataset], int]:
        rows, total = self._fetch_page(
            """
            SELECT payload, count(*) OVER () AS total
            FROM data_datasets
            WHERE tenant_id = %s AND project_id = %s
            ORDER BY created_at DESC, dataset_id DESC
            LIMIT %s OFFSET %s
            """,
            (organization_id, project_id, limit, offset),
            "SELECT count(*) FROM data_datasets WHERE tenant_id = %s AND project_id = %s",
            (organization_id, project_id),
        )
        return [Dataset.model_validate(row["payload"]) for row in rows], total

    def update_dataset(self, value: Dataset) -> None:
        updated = self._execute(
            """
            UPDATE data_datasets
            SET status = %s, payload = %s::jsonb
            WHERE dataset_id = %s AND tenant_id = %s AND project_id = %s
            """,
            (value.status, self._json(value), value.dataset_id, value.tenant_id, value.project_id),
        )
        if updated == 0:
            raise KeyError(value.dataset_id)

    def add_dataset_version(self, value: DatasetVersion, organization_id: str, project_id: str) -> None:
        inserted = self._insert_returning_count(
            """
            INSERT INTO data_dataset_versions
                (version_id, dataset_id, tenant_id, project_id, version, status, created_at, payload)
            SELECT %s, d.dataset_id, d.tenant_id, d.project_id, %s, %s, %s, %s::jsonb
            FROM data_datasets d
            WHERE d.dataset_id = %s AND d.tenant_id = %s AND d.project_id = %s
            """,
            (
                value.dataset_version_id,
                value.version,
                value.status,
                value.created_at,
                self._json(value),
                value.dataset_id,
                organization_id,
                project_id,
            ),
        )
        if inserted == 0:
            raise KeyError(value.dataset_id)

    def get_dataset_version(
        self, dataset_version_id: str, organization_id: str, project_id: str
    ) -> DatasetVersion:
        row = self._fetch_one(
            """
            SELECT payload FROM data_dataset_versions
            WHERE version_id = %s AND tenant_id = %s AND project_id = %s
            """,
            (dataset_version_id, organization_id, project_id),
        )
        if row is None:
            raise KeyError(dataset_version_id)
        return DatasetVersion.model_validate(row["payload"])

    def list_dataset_versions(
        self, dataset_id: str, organization_id: str, project_id: str, *, limit: int, offset: int
    ) -> tuple[list[DatasetVersion], int]:
        rows, total = self._fetch_page(
            """
            SELECT payload, count(*) OVER () AS total
            FROM data_dataset_versions
            WHERE dataset_id = %s AND tenant_id = %s AND project_id = %s
            ORDER BY created_at DESC, version_id DESC
            LIMIT %s OFFSET %s
            """,
            (dataset_id, organization_id, project_id, limit, offset),
            """
            SELECT count(*) FROM data_dataset_versions
            WHERE dataset_id = %s AND tenant_id = %s AND project_id = %s
            """,
            (dataset_id, organization_id, project_id),
        )
        return [DatasetVersion.model_validate(row["payload"]) for row in rows], total

    def update_dataset_version(self, value: DatasetVersion, organization_id: str, project_id: str) -> None:
        updated = self._execute(
            """
            UPDATE data_dataset_versions
            SET status = %s, payload = %s::jsonb
            WHERE version_id = %s AND tenant_id = %s AND project_id = %s
            """,
            (
                value.status,
                self._json(value),
                value.dataset_version_id,
                organization_id,
                project_id,
            ),
        )
        if updated == 0:
            raise KeyError(value.dataset_version_id)

    def add_access_grant(self, value: DatasetAccessGrant, organization_id: str, project_id: str) -> None:
        inserted = self._insert_returning_count(
            """
            INSERT INTO data_dataset_access_grants
                (grant_id, version_id, tenant_id, project_id, expires_at, created_at, payload)
            SELECT %s, v.version_id, v.tenant_id, v.project_id, %s, %s, %s::jsonb
            FROM data_dataset_versions v
            WHERE v.version_id = %s AND v.tenant_id = %s AND v.project_id = %s
            """,
            (
                value.grant_id,
                value.expires_at,
                value.created_at,
                self._json(value),
                value.dataset_version_id,
                organization_id,
                project_id,
            ),
        )
        if inserted == 0:
            raise KeyError(value.dataset_version_id)

    def get_access_grant(self, grant_id: str, organization_id: str, project_id: str) -> DatasetAccessGrant:
        row = self._fetch_one(
            """
            SELECT payload FROM data_dataset_access_grants
            WHERE grant_id = %s AND tenant_id = %s AND project_id = %s
            """,
            (grant_id, organization_id, project_id),
        )
        if row is None:
            raise KeyError(grant_id)
        return DatasetAccessGrant.model_validate(row["payload"])

    def list_access_grants(
        self, dataset_version_id: str, organization_id: str, project_id: str
    ) -> list[DatasetAccessGrant]:
        rows = self._fetch_all(
            """
            SELECT payload FROM data_dataset_access_grants
            WHERE version_id = %s AND tenant_id = %s AND project_id = %s
            ORDER BY created_at, grant_id
            """,
            (dataset_version_id, organization_id, project_id),
        )
        return [DatasetAccessGrant.model_validate(row["payload"]) for row in rows]
