"""数据质量与数据血缘的 PostgreSQL 实现。"""

from __future__ import annotations

from scenara_data.adapters.postgres._sql import SqlSupport
from scenara_data.domain.models import (
    DataQualityReport,
    LineageLink,
    LineageSnapshot,
    QualityIssue,
    QualityRule,
    QualityRun,
)


class QualitySqlMixin(SqlSupport):
    def add_quality_rule(self, value: QualityRule, organization_id: str, project_id: str) -> None:
        self._insert(
            """
            INSERT INTO data_quality_rules (rule_id, tenant_id, project_id, payload)
            VALUES (%s, %s, %s, %s::jsonb)
            """,
            (value.rule_id, organization_id, project_id, self._json(value)),
        )

    def get_quality_rule(self, rule_id: str, organization_id: str, project_id: str) -> QualityRule:
        row = self._fetch_one(
            "SELECT payload FROM data_quality_rules WHERE rule_id = %s AND tenant_id = %s AND project_id = %s",
            (rule_id, organization_id, project_id),
        )
        if row is None:
            raise KeyError(rule_id)
        return QualityRule.model_validate(row["payload"])

    def list_quality_rules(
        self, organization_id: str, project_id: str, *, limit: int, offset: int
    ) -> tuple[list[QualityRule], int]:
        rows, total = self._fetch_page(
            """
            SELECT payload, count(*) OVER () AS total
            FROM data_quality_rules
            WHERE tenant_id = %s AND project_id = %s
            ORDER BY rule_id
            LIMIT %s OFFSET %s
            """,
            (organization_id, project_id, limit, offset),
            "SELECT count(*) FROM data_quality_rules WHERE tenant_id = %s AND project_id = %s",
            (organization_id, project_id),
        )
        return [QualityRule.model_validate(row["payload"]) for row in rows], total

    def add_quality_run(self, value: QualityRun, organization_id: str, project_id: str) -> None:
        inserted = self._insert_returning_count(
            """
            INSERT INTO data_quality_runs
                (run_id, version_id, tenant_id, project_id, status, created_at, payload)
            SELECT %s, v.version_id, v.tenant_id, v.project_id, %s, %s, %s::jsonb
            FROM data_dataset_versions v
            WHERE v.version_id = %s AND v.tenant_id = %s AND v.project_id = %s
            """,
            (
                value.run_id,
                value.status,
                value.created_at,
                self._json(value),
                value.dataset_version_id,
                organization_id,
                project_id,
            ),
        )
        if inserted == 0:
            raise KeyError(value.dataset_version_id)

    def get_quality_run(self, run_id: str, organization_id: str, project_id: str) -> QualityRun:
        row = self._fetch_one(
            "SELECT payload FROM data_quality_runs WHERE run_id = %s AND tenant_id = %s AND project_id = %s",
            (run_id, organization_id, project_id),
        )
        if row is None:
            raise KeyError(run_id)
        return QualityRun.model_validate(row["payload"])

    def update_quality_run(self, value: QualityRun, organization_id: str, project_id: str) -> None:
        updated = self._execute(
            """
            UPDATE data_quality_runs SET status = %s, payload = %s::jsonb
            WHERE run_id = %s AND tenant_id = %s AND project_id = %s
            """,
            (value.status, self._json(value), value.run_id, organization_id, project_id),
        )
        if updated == 0:
            raise KeyError(value.run_id)

    def list_quality_runs(
        self, dataset_version_id: str, organization_id: str, project_id: str, *, limit: int, offset: int
    ) -> tuple[list[QualityRun], int]:
        rows, total = self._fetch_page(
            """
            SELECT payload, count(*) OVER () AS total
            FROM data_quality_runs
            WHERE version_id = %s AND tenant_id = %s AND project_id = %s
            ORDER BY created_at DESC, run_id DESC
            LIMIT %s OFFSET %s
            """,
            (dataset_version_id, organization_id, project_id, limit, offset),
            """
            SELECT count(*) FROM data_quality_runs
            WHERE version_id = %s AND tenant_id = %s AND project_id = %s
            """,
            (dataset_version_id, organization_id, project_id),
        )
        return [QualityRun.model_validate(row["payload"]) for row in rows], total

    def add_quality_issue(self, value: QualityIssue, organization_id: str, project_id: str) -> None:
        inserted = self._insert_returning_count(
            """
            INSERT INTO data_quality_issues (issue_id, run_id, tenant_id, project_id, payload)
            SELECT %s, r.run_id, r.tenant_id, r.project_id, %s::jsonb
            FROM data_quality_runs r
            WHERE r.run_id = %s AND r.tenant_id = %s AND r.project_id = %s
            """,
            (value.issue_id, self._json(value), value.quality_run_id, organization_id, project_id),
        )
        if inserted == 0:
            raise KeyError(value.quality_run_id)

    def list_quality_issues(
        self, quality_run_id: str, organization_id: str, project_id: str
    ) -> list[QualityIssue]:
        rows = self._fetch_all(
            """
            SELECT payload FROM data_quality_issues
            WHERE run_id = %s AND tenant_id = %s AND project_id = %s
            ORDER BY issue_id
            """,
            (quality_run_id, organization_id, project_id),
        )
        return [QualityIssue.model_validate(row["payload"]) for row in rows]

    def add_quality_report(
        self, value: DataQualityReport, organization_id: str, project_id: str
    ) -> None:
        inserted = self._insert_returning_count(
            """
            INSERT INTO data_quality_reports
                (report_id, version_id, tenant_id, project_id, status, created_at, payload)
            SELECT %s, v.version_id, v.tenant_id, v.project_id, %s, %s, %s::jsonb
            FROM data_dataset_versions v
            WHERE v.version_id = %s AND v.tenant_id = %s AND v.project_id = %s
            """,
            (
                value.report_id,
                value.status,
                value.created_at,
                self._json(value),
                value.dataset_version_id,
                organization_id,
                project_id,
            ),
        )
        if inserted == 0:
            raise KeyError(value.dataset_version_id)

    def get_quality_report(
        self, report_id: str, organization_id: str, project_id: str
    ) -> DataQualityReport:
        row = self._fetch_one(
            """
            SELECT payload FROM data_quality_reports
            WHERE report_id = %s AND tenant_id = %s AND project_id = %s
            """,
            (report_id, organization_id, project_id),
        )
        if row is None:
            raise KeyError(report_id)
        return DataQualityReport.model_validate(row["payload"])


class LineageSqlMixin(SqlSupport):
    def add_lineage_link(self, value: LineageLink, organization_id: str, project_id: str) -> None:
        self._insert(
            """
            INSERT INTO data_lineage_edges
                (lineage_id, source_entity_id, target_entity_id, tenant_id, project_id, created_at, payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                value.lineage_id,
                value.source_entity_id,
                value.target_entity_id,
                organization_id,
                project_id,
                value.created_at,
                self._json(value),
            ),
        )

    def list_lineage(self, entity_id: str, organization_id: str, project_id: str) -> list[LineageLink]:
        rows = self._fetch_all(
            """
            SELECT payload FROM data_lineage_edges
            WHERE tenant_id = %s AND project_id = %s
              AND (source_entity_id = %s OR target_entity_id = %s)
            ORDER BY created_at, lineage_id
            """,
            (organization_id, project_id, entity_id, entity_id),
        )
        return [LineageLink.model_validate(row["payload"]) for row in rows]

    def add_lineage_snapshot(
        self, value: LineageSnapshot, organization_id: str, project_id: str
    ) -> None:
        inserted = self._insert_returning_count(
            """
            INSERT INTO data_lineage_snapshots
                (snapshot_id, version_id, tenant_id, project_id, created_at, payload)
            SELECT %s, v.version_id, v.tenant_id, v.project_id, %s, %s::jsonb
            FROM data_dataset_versions v
            WHERE v.version_id = %s AND v.tenant_id = %s AND v.project_id = %s
            """,
            (
                value.snapshot_id,
                value.created_at,
                self._json(value),
                value.dataset_version_id,
                organization_id,
                project_id,
            ),
        )
        if inserted == 0:
            raise KeyError(value.dataset_version_id)

    def get_lineage_snapshot(
        self, snapshot_id: str, organization_id: str, project_id: str
    ) -> LineageSnapshot:
        row = self._fetch_one(
            """
            SELECT payload FROM data_lineage_snapshots
            WHERE snapshot_id = %s AND tenant_id = %s AND project_id = %s
            """,
            (snapshot_id, organization_id, project_id),
        )
        if row is None:
            raise KeyError(snapshot_id)
        return LineageSnapshot.model_validate(row["payload"])
