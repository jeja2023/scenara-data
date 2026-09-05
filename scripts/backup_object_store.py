"""把受版本保护的 S3 业务对象复制到备份桶，并生成可恢复的对象清单。"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from scenara_data.config import Settings, load_settings


def _client(settings: Settings):
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=settings.object_storage_endpoint,
        region_name=settings.object_storage_region,
        aws_access_key_id=settings.object_storage_access_key,
        aws_secret_access_key=settings.object_storage_secret_key,
    )


def backup_key(timestamp: str, bucket: str, key: str, version_id: str | None) -> str:
    encoded_key = quote(key, safe="")
    encoded_version = quote(version_id or "unversioned", safe="")
    return f"object-snapshots/{timestamp}/{bucket}/{encoded_key}/{encoded_version}"


def manifest_checksum(manifest: dict[str, Any]) -> str:
    payload = json.dumps(manifest, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="创建对象存储版本快照备份")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--bucket", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()
    settings = load_settings()
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    buckets = arguments.bucket or [
        settings.dataset_bucket,
        settings.manifest_bucket,
        settings.import_bucket,
        settings.export_bucket,
        settings.artifact_bucket,
    ]
    if settings.backup_bucket in buckets:
        raise SystemExit("备份桶不能作为对象快照来源")
    client = _client(settings)
    entries: list[dict[str, object]] = []
    for bucket in buckets:
        paginator = client.get_paginator("list_object_versions")
        for page in paginator.paginate(Bucket=bucket):
            for version in page.get("Versions", []):
                key = str(version["Key"])
                version_id = str(version["VersionId"]) if version.get("VersionId") else None
                destination = backup_key(timestamp, bucket, key, version_id)
                if not arguments.dry_run:
                    source: dict[str, str] = {"Bucket": bucket, "Key": key}
                    if version_id:
                        source["VersionId"] = version_id
                    client.copy_object(
                        Bucket=settings.backup_bucket,
                        Key=destination,
                        CopySource=source,
                        MetadataDirective="COPY",
                    )
                entries.append(
                    {
                        "source_bucket": bucket,
                        "source_key": key,
                        "source_version_id": version_id,
                        "backup_bucket": settings.backup_bucket,
                        "backup_key": destination,
                        "etag": str(version.get("ETag", "")).strip('"'),
                        "size_bytes": int(version.get("Size", 0)),
                    }
                )
    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "backup_bucket": settings.backup_bucket,
        "entries": entries,
    }
    checksum = manifest_checksum(manifest)
    manifest["sha256"] = checksum
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = arguments.output_dir / f"object-snapshot-{timestamp}.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    if not arguments.dry_run:
        client.put_object(
            Bucket=settings.backup_bucket,
            Key=f"object-snapshots/{timestamp}/manifest.json",
            Body=manifest_path.read_bytes(),
            ContentType="application/json",
            Metadata={"sha256": checksum},
        )
    print(
        json.dumps(
            {
                "mode": "dry_run" if arguments.dry_run else "backed_up",
                "manifest": str(manifest_path.resolve()),
                "sha256": checksum,
                "object_count": len(entries),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
