from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from scenara_data.api.schemas import DatasetVersionReference

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_repository_contracts.py"
CONTRACTS_ROOT = ROOT.parent / "scenara-contracts"


def test_repository_contracts_validate_against_published_release() -> None:
    if not CONTRACTS_ROOT.is_dir():
        return
    subprocess.run(
        [sys.executable, str(SCRIPT), "--contracts-root", str(CONTRACTS_ROOT)],
        cwd=ROOT,
        check=True,
    )


def test_dataset_version_reference_keeps_published_identifier_constraints() -> None:
    values = {
        "schema_version": "1.0",
        "dataset_id": "INVALID SPACE",
        "version": "not-semver",
        "manifest_uri": "manifest#sha256=" + "a" * 64,
        "manifest_sha256": "a" * 64,
        "lineage_refs": ["lineage#sha256=" + "b" * 64],
        "authorization_id": "grant",
        "authorized_consumer_repository_ids": ["scenara-model"],
        "created_at": "2026-09-05T00:00:00Z",
    }
    with pytest.raises(ValidationError):
        DatasetVersionReference.model_validate(values)
