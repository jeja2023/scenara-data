"""受控重建 PostgreSQL Outbox 死信事件；默认只报告，不修改数据。"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from uuid import uuid4

from scenara_data.config import load_settings

DEAD_LETTER_PREFIX = "DEAD_LETTER:"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def main() -> int:
    parser = argparse.ArgumentParser(description="检查或重新排队 Outbox 死信事件")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--event-id", help="仅重新排队指定事件")
    scope.add_argument("--all-dead-letters", action="store_true", help="选择所有死信事件")
    parser.add_argument("--apply", action="store_true", help="实际重新排队；未设置时仅报告")
    parser.add_argument("--operator", default="outbox-rebuild-cli")
    arguments = parser.parse_args()
    settings = load_settings()
    if settings.runtime_mode != "postgres":
        raise SystemExit("Outbox 重建要求 PostgreSQL 运行模式")

    import psycopg
    from psycopg.rows import dict_row

    filters = ["delivered_at IS NULL", "last_error LIKE %s"]
    parameters: list[object] = [f"{DEAD_LETTER_PREFIX}%"]
    if arguments.event_id:
        filters.append("event_id = %s")
        parameters.append(arguments.event_id)
    predicate = " AND ".join(filters)
    with psycopg.connect(settings.database_url, row_factory=dict_row) as connection, connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT event_id, tenant_id, project_id, event_type, attempt_count, last_error
            FROM data_outbox_events
            WHERE {predicate}
            ORDER BY occurred_at, event_id
            """,
            parameters,
        )
        rows = [dict(row) for row in cursor.fetchall()]
        if arguments.apply and rows:
            now = _utc_now()
            event_ids = [str(row["event_id"]) for row in rows]
            cursor.execute(
                """
                UPDATE data_outbox_events
                SET attempt_count = 0, available_at = %s, last_error = NULL
                WHERE event_id = ANY(%s)
                """,
                (now, event_ids),
            )
            for row in rows:
                cursor.execute(
                    """
                    INSERT INTO data_audit_records
                        (audit_id, tenant_id, project_id, action, entity_id, occurred_at, payload)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        f"aud_{uuid4().hex}",
                        row["tenant_id"],
                        row["project_id"],
                        "outbox.dead_letter.requeued",
                        row["event_id"],
                        now,
                        json.dumps(
                            {
                                "event_id": row["event_id"],
                                "event_type": row["event_type"],
                                "previous_attempt_count": row["attempt_count"],
                                "previous_error": row["last_error"],
                                "operator": arguments.operator,
                                "requeued_at": now.isoformat().replace("+00:00", "Z"),
                            },
                            ensure_ascii=True,
                            sort_keys=True,
                        ),
                    ),
                )
            connection.commit()

    print(
        json.dumps(
            {
                "mode": "applied" if arguments.apply else "dry_run",
                "selected_count": len(rows),
                "events": [
                    {
                        "event_id": row["event_id"],
                        "event_type": row["event_type"],
                        "attempt_count": row["attempt_count"],
                    }
                    for row in rows
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
