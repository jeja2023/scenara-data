"""难例承接、迁移报告、审计、Outbox 与幂等的 PostgreSQL 实现。"""

from __future__ import annotations

from datetime import datetime, timedelta

from scenara_data.adapters.postgres._sql import SqlSupport
from scenara_data.domain.models import AuditRecord, HardSampleImport, MigrationReport, OutboxEvent
from scenara_data.ports.interfaces import IdempotencyRecord, PendingEvent

OUTBOX_CLAIM_LEASE_SECONDS = 30


class IntakeSqlMixin(SqlSupport):
    def add_hard_sample_import(
        self, value: HardSampleImport, organization_id: str, project_id: str
    ) -> None:
        self._insert(
            """
            INSERT INTO data_hard_sample_imports
                (import_id, manifest_id, manifest_checksum, tenant_id, project_id, status, created_at, payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                value.import_id,
                value.manifest_id,
                value.manifest_checksum,
                organization_id,
                project_id,
                value.status,
                value.created_at,
                self._json(value),
            ),
        )

    def get_hard_sample_import(
        self, import_id: str, organization_id: str, project_id: str
    ) -> HardSampleImport:
        row = self._fetch_one(
            """
            SELECT payload FROM data_hard_sample_imports
            WHERE import_id = %s AND tenant_id = %s AND project_id = %s
            """,
            (import_id, organization_id, project_id),
        )
        if row is None:
            raise KeyError(import_id)
        return HardSampleImport.model_validate(row["payload"])

    def find_hard_sample_import_by_manifest(
        self, manifest_id: str, organization_id: str, project_id: str
    ) -> HardSampleImport | None:
        row = self._fetch_one(
            """
            SELECT payload FROM data_hard_sample_imports
            WHERE manifest_id = %s AND tenant_id = %s AND project_id = %s
            """,
            (manifest_id, organization_id, project_id),
        )
        return None if row is None else HardSampleImport.model_validate(row["payload"])

    def update_hard_sample_import(
        self, value: HardSampleImport, organization_id: str, project_id: str
    ) -> None:
        updated = self._execute(
            """
            UPDATE data_hard_sample_imports SET status = %s, payload = %s::jsonb
            WHERE import_id = %s AND tenant_id = %s AND project_id = %s
            """,
            (value.status, self._json(value), value.import_id, organization_id, project_id),
        )
        if updated == 0:
            raise KeyError(value.import_id)

    def add_migration_report(
        self, value: MigrationReport, organization_id: str, project_id: str
    ) -> None:
        self._insert(
            """
            INSERT INTO data_migration_reports
                (migration_id, tenant_id, project_id, package_checksum, status, created_at, payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                value.migration_id,
                organization_id,
                project_id,
                value.package_checksum,
                value.status,
                value.created_at,
                self._json(value),
            ),
        )

    def get_migration_report(
        self, migration_id: str, organization_id: str, project_id: str
    ) -> MigrationReport:
        row = self._fetch_one(
            """
            SELECT payload FROM data_migration_reports
            WHERE migration_id = %s AND tenant_id = %s AND project_id = %s
            """,
            (migration_id, organization_id, project_id),
        )
        if row is None:
            raise KeyError(migration_id)
        return MigrationReport.model_validate(row["payload"])

    def find_migration_report_by_checksum(
        self, package_checksum: str, organization_id: str, project_id: str
    ) -> MigrationReport | None:
        row = self._fetch_one(
            """
            SELECT payload FROM data_migration_reports
            WHERE package_checksum = %s AND tenant_id = %s AND project_id = %s
            """,
            (package_checksum, organization_id, project_id),
        )
        return None if row is None else MigrationReport.model_validate(row["payload"])

    def update_migration_report(
        self, value: MigrationReport, organization_id: str, project_id: str
    ) -> None:
        updated = self._execute(
            """
            UPDATE data_migration_reports SET status = %s, payload = %s::jsonb
            WHERE migration_id = %s AND tenant_id = %s AND project_id = %s
            """,
            (value.status, self._json(value), value.migration_id, organization_id, project_id),
        )
        if updated == 0:
            raise KeyError(value.migration_id)


class SupportSqlMixin(SqlSupport):
    def record(self, record: AuditRecord) -> None:
        self._insert(
            """
            INSERT INTO data_audit_records
                (audit_id, tenant_id, project_id, action, entity_id, occurred_at, payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                record.audit_id,
                record.organization_id,
                record.project_id,
                record.action,
                record.entity_id,
                record.occurred_at,
                self._json(record),
            ),
        )

    def append(self, event: OutboxEvent) -> None:
        self._insert(
            """
            INSERT INTO data_outbox_events
                (event_id, tenant_id, project_id, event_type, occurred_at, payload)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                event.event_id,
                event.tenant_id,
                event.project_id,
                event.event_type,
                event.occurred_at,
                self._json(event),
            ),
        )

    def claim_pending(self, *, limit: int, now: datetime) -> list[PendingEvent]:
        lease_until = now + timedelta(seconds=OUTBOX_CLAIM_LEASE_SECONDS)
        rows = self._fetch_all(
            """
            WITH pending AS (
                SELECT event_id
                FROM data_outbox_events
                WHERE delivered_at IS NULL AND available_at <= %s
                ORDER BY occurred_at, event_id
                LIMIT %s
                FOR UPDATE SKIP LOCKED
            )
            UPDATE data_outbox_events AS event
            SET available_at = %s
            FROM pending
            WHERE event.event_id = pending.event_id
            RETURNING event.payload, event.attempt_count
            """,
            (now, limit, lease_until),
        )
        return [
            PendingEvent(
                event=OutboxEvent.model_validate(row["payload"]),
                attempt_count=int(row["attempt_count"]),
            )
            for row in rows
        ]

    def mark_delivered(self, event_id: str, delivered_at: datetime) -> None:
        updated = self._execute(
            "UPDATE data_outbox_events SET delivered_at = %s, last_error = NULL WHERE event_id = %s",
            (delivered_at, event_id),
        )
        if updated == 0:
            raise KeyError(event_id)

    def mark_failed(self, event_id: str, *, error: str, available_at: datetime) -> None:
        updated = self._execute(
            """
            UPDATE data_outbox_events
            SET attempt_count = attempt_count + 1, available_at = %s, last_error = %s
            WHERE event_id = %s
            """,
            (available_at, error, event_id),
        )
        if updated == 0:
            raise KeyError(event_id)

    def get(self, scope: str, key: str) -> IdempotencyRecord | None:
        row = self._fetch_one(
            """
            SELECT scope, idempotency_key, request_hash, status_code, response_payload
            FROM data_idempotency_records
            WHERE scope = %s AND idempotency_key = %s
            """,
            (scope, key),
        )
        if row is None:
            return None
        return IdempotencyRecord(
            scope=row["scope"],
            key=row["idempotency_key"],
            request_hash=row["request_hash"],
            status_code=int(row["status_code"]),
            response_payload=row["response_payload"],
        )

    def save(self, record: IdempotencyRecord) -> None:
        self._insert(
            """
            INSERT INTO data_idempotency_records
                (scope, idempotency_key, request_hash, status_code, response_payload)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            """,
            (
                record.scope,
                record.key,
                record.request_hash,
                record.status_code,
                self._json(record.response_payload),
            ),
        )
