"""创建 PostgreSQL 自定义格式备份、校验清单，并可上传至受版本保护的备份桶。"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from scenara_data.config import Settings, load_settings


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def redact_database_url(database_url: str) -> str:
    parts = urlsplit(database_url)
    hostname = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    username = f"{parts.username}@" if parts.username else ""
    safe_query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() not in {"password", "pass", "secret", "token"}
        ]
    )
    return urlunsplit((parts.scheme, f"{username}{hostname}{port}", parts.path, safe_query, ""))


def build_manifest(*, artifact: Path, checksum: str, database_url: str, created_at: datetime) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "created_at": created_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "format": "pg_dump.custom",
        "artifact": {"name": artifact.name, "sha256": checksum, "size_bytes": artifact.stat().st_size},
        "database": redact_database_url(database_url),
    }


def _object_key(created_at: datetime, checksum: str, suffix: str) -> str:
    timestamp = created_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"postgres/{timestamp}-{checksum[:16]}{suffix}"


def _s3_client(settings: Settings):
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=settings.object_storage_endpoint,
        region_name=settings.object_storage_region,
        aws_access_key_id=settings.object_storage_access_key,
        aws_secret_access_key=settings.object_storage_secret_key,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="创建并上传 PostgreSQL 备份")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--pg-dump", default="pg_dump")
    parser.add_argument("--skip-upload", action="store_true")
    arguments = parser.parse_args()
    settings = load_settings()
    if settings.runtime_mode != "postgres":
        raise SystemExit("备份要求 PostgreSQL 运行模式")
    database_url = arguments.database_url or settings.database_url
    created_at = datetime.now(UTC)
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = created_at.strftime("%Y%m%dT%H%M%SZ")
    artifact = arguments.output_dir / f"scenara-data-{timestamp}.dump"
    partial_artifact = artifact.with_suffix(".dump.partial")
    manifest_path = artifact.with_suffix(".manifest.json")

    subprocess.run(
        [
            arguments.pg_dump,
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            "--file",
            str(partial_artifact),
            database_url,
        ],
        check=True,
    )
    partial_artifact.replace(artifact)
    checksum = sha256_file(artifact)
    manifest = build_manifest(
        artifact=artifact, checksum=checksum, database_url=database_url, created_at=created_at
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    uploaded: dict[str, str] = {}
    if not arguments.skip_upload:
        client = _s3_client(settings)
        artifact_key = _object_key(created_at, checksum, ".dump")
        manifest_key = _object_key(created_at, checksum, ".manifest.json")
        client.put_object(
            Bucket=settings.backup_bucket,
            Key=artifact_key,
            Body=artifact.read_bytes(),
            ContentType="application/octet-stream",
            Metadata={"sha256": checksum, "format": "pg_dump.custom"},
        )
        client.put_object(
            Bucket=settings.backup_bucket,
            Key=manifest_key,
            Body=manifest_path.read_bytes(),
            ContentType="application/json",
            Metadata={"sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest()},
        )
        uploaded = {"bucket": settings.backup_bucket, "artifact_key": artifact_key, "manifest_key": manifest_key}

    print(
        json.dumps(
            {
                "artifact": str(artifact.resolve()),
                "manifest": str(manifest_path.resolve()),
                "sha256": checksum,
                "uploaded": uploaded or None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
