from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from scripts.backup_object_store import backup_key, manifest_checksum
from scripts.backup_postgres import build_manifest, sha256_file
from scripts.load_test_api import percentile
from scripts.preproduction_check import expected_migrations
from scripts.restore_object_store import load_manifest as load_object_manifest
from scripts.restore_postgres import load_and_verify_manifest
from scripts.verify_object_inventory import verify_bucket


def test_backup_manifest_redacts_password_and_restore_verifies_checksum(tmp_path: Path) -> None:
    artifact = tmp_path / "backup.dump"
    artifact.write_bytes(b"backup-content")
    checksum = sha256_file(artifact)
    manifest = build_manifest(
        artifact=artifact,
        checksum=checksum,
        database_url="postgresql://operator:secret@db.example/scenara?sslmode=verify-full&password=secret",
        created_at=datetime(2026, 9, 5, tzinfo=UTC),
    )
    assert manifest["database"] == "postgresql://operator@db.example/scenara?sslmode=verify-full"
    manifest_path = tmp_path / "backup.manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert load_and_verify_manifest(artifact, manifest_path) == manifest

    artifact.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="SHA-256"):
        load_and_verify_manifest(artifact, manifest_path)


def test_load_percentiles_and_migration_inventory() -> None:
    assert percentile([], 0.95) is None
    assert percentile([1.0, 2.0, 3.0], 0.50) == 2.0
    assert "0003" in expected_migrations()


def test_object_snapshot_manifest_is_version_aware_and_tamper_evident(tmp_path: Path) -> None:
    assert backup_key("20260905T000000Z", "scenara-datasets", "folder/a b.jpg", "version-1").endswith(
        "folder%2Fa%20b.jpg/version-1"
    )
    payload = {
        "schema_version": "1.0",
        "created_at": "2026-09-05T00:00:00Z",
        "backup_bucket": "scenara-data-backups",
        "entries": [],
    }
    payload["sha256"] = manifest_checksum(payload)
    path = tmp_path / "object-snapshot.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_object_manifest(path)["entries"] == []
    payload["entries"] = [{"source_key": "tampered"}]
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256"):
        load_object_manifest(path)


class _Paginator:
    def paginate(self, **_: object):
        return [{"Contents": [{"Key": "one"}, {"Key": "two"}]}]


class _S3:
    def get_bucket_versioning(self, **_: object) -> dict[str, str]:
        return {"Status": "Enabled"}

    def get_paginator(self, _: str) -> _Paginator:
        return _Paginator()

    def head_object(self, **kwargs: object) -> dict[str, object]:
        key = kwargs["Key"]
        return {"Metadata": {"sha256": hashlib.sha256(str(key).encode()).hexdigest()}} if key == "one" else {"Metadata": {}}


def test_object_inventory_reports_missing_checksum_metadata() -> None:
    result = verify_bucket(_S3(), "scenara-datasets", verify_content=False)
    assert result.versioning_enabled
    assert result.object_count == 2
    assert result.missing_checksum_count == 1
