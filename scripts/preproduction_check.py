"""生成可归档的部署前就绪报告；失败时返回非零，阻止错误发布。"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from scenara_data.api.container import build_container
from scenara_data.config import load_settings

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"


def expected_migrations() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in sorted(MIGRATIONS.glob("[0-9][0-9][0-9][0-9]_*.sql")):
        if path.name.endswith(".down.sql"):
            continue
        values[path.name.split("_", 1)[0]] = hashlib.sha256(path.read_bytes()).hexdigest()
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description="执行生产部署前依赖、迁移和 Outbox 检查")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--allow-dead-letters", action="store_true")
    arguments = parser.parse_args()
    settings = load_settings()
    if not settings.is_production_deployment:
        raise SystemExit("部署前检查只允许 SCENARA_DATA_DEPLOYMENT_PROFILE=production")

    container = build_container(settings)
    readiness = container.readiness()
    import psycopg
    from psycopg.rows import dict_row

    expected = expected_migrations()
    with psycopg.connect(settings.database_url, row_factory=dict_row) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT version, sha256 FROM data_schema_migrations")
        actual = {str(row["version"]): str(row["sha256"]) for row in cursor.fetchall()}
        cursor.execute(
            """
            SELECT count(*) AS count FROM data_outbox_events
            WHERE delivered_at IS NULL AND last_error LIKE 'DEAD_LETTER:%'
            """
        )
        dead_letters = int(cursor.fetchone()["count"])
    missing_or_changed = {
        version: {"expected": digest, "actual": actual.get(version)}
        for version, digest in expected.items()
        if actual.get(version) != digest
    }
    passed = bool(readiness) and all(readiness.values()) and not missing_or_changed
    if dead_letters and not arguments.allow_dead_letters:
        passed = False
    report = {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "service": settings.service_name,
        "profile": settings.deployment_profile,
        "passed": passed,
        "readiness": readiness,
        "migration_mismatches": missing_or_changed,
        "outbox_dead_letter_count": dead_letters,
    }
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
