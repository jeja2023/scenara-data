from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"


def database_url() -> str:
    value = os.getenv("SCENARA_DATA_DATABASE_URL")
    if not value:
        raise RuntimeError("SCENARA_DATA_DATABASE_URL is required")
    return value


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def apply_migrations() -> None:
    with psycopg.connect(database_url()) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS data_schema_migrations (
                version text PRIMARY KEY,
                sha256 text NOT NULL,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        for path in sorted(MIGRATIONS.glob("[0-9][0-9][0-9][0-9]_*.sql")):
            if path.name.endswith(".down.sql"):
                continue
            version = path.name.split("_", 1)[0]
            content = path.read_bytes()
            sha256 = digest(content)
            cursor.execute("SELECT sha256 FROM data_schema_migrations WHERE version = %s", (version,))
            previous = cursor.fetchone()
            if previous:
                if previous[0] != sha256:
                    raise RuntimeError(f"applied migration {version} has changed")
                continue
            cursor.execute(content.decode("utf-8"))
            cursor.execute(
                "INSERT INTO data_schema_migrations (version, sha256) VALUES (%s, %s)",
                (version, sha256),
            )
        connection.commit()


def rollback(version: str) -> None:
    down_candidates = sorted(MIGRATIONS.glob(f"{version}_*.down.sql"))
    if len(down_candidates) != 1:
        raise RuntimeError(f"rollback migration for {version} was not found")
    with psycopg.connect(database_url()) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT version FROM data_schema_migrations ORDER BY version DESC LIMIT 1")
        latest = cursor.fetchone()
        if latest is None or latest[0] != version:
            raise RuntimeError("only the latest applied migration can be rolled back")
        cursor.execute(down_candidates[0].read_text(encoding="utf-8"))
        cursor.execute("DELETE FROM data_schema_migrations WHERE version = %s", (version,))
        connection.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply or roll back Scenara Data migrations")
    parser.add_argument("--rollback", metavar="VERSION")
    arguments = parser.parse_args()
    if arguments.rollback:
        rollback(arguments.rollback)
    else:
        apply_migrations()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
