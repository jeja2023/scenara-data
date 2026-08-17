from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from scenara_data.adapters.migration_package import InMemoryMigrationPackage
from scenara_data.api.container import build_container
from scenara_data.config import Settings
from scenara_data.domain.models import JobStatus
from scenara_data.ports.interfaces import RequestContext

NOW = datetime(2026, 8, 16, 2, 0, tzinfo=UTC)
CONTEXT = RequestContext(
    tenant_id="tenant-a",
    project_id="project-a",
    principal_id="migration-service",
    principal_type="service_account",
    permission_scopes=("data.import.execute", "data.dataset.read"),
    product_entitlements=("scenara.data",),
    request_id="req-migration",
    trace_id="0123456789abcdef0123456789abcdef",
)


def test_invalid_migration_records_produce_a_persisted_idempotent_failure_report() -> None:
    records = b"{not-json}\n"
    manifest = {
        "schema_version": "1.0",
        "source_repository": "scenara",
        "source_version": "1.0.0",
        "generated_at": NOW.isoformat().replace("+00:00", "Z"),
        "tenant_id": CONTEXT.tenant_id,
        "project_id": CONTEXT.project_id,
        "exporter_version": "1.0.0",
        "files": [
            {
                "file": "datasets.jsonl",
                "record_count": 1,
                "sha256": hashlib.sha256(records).hexdigest(),
            }
        ],
    }
    package = InMemoryMigrationPackage(
        {
            "migration-manifest.json": json.dumps(manifest).encode("utf-8"),
            "datasets.jsonl": records,
        }
    )
    migrations = build_container(Settings()).migrations

    first = migrations.import_package(package, CONTEXT)
    replay = migrations.import_package(package, CONTEXT)

    assert first.status == JobStatus.FAILED
    assert first.failed_count == 1
    assert first.details_ref is not None
    assert first.completed_at is not None
    assert first.failures[0].startswith("迁移包校验失败")
    assert replay == first
