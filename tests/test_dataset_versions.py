from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from scenara_data.domain.models import DatasetVersion, DatasetVersionStatus, ObjectReference

NOW = datetime(2026, 8, 15, 10, 30, tzinfo=UTC)


def version(status: DatasetVersionStatus = DatasetVersionStatus.DRAFT) -> DatasetVersion:
    return DatasetVersion(
        dataset_version_id="dsv_example",
        dataset_id="dataset.example",
        version="1.0.0",
        status=status,
        created_by="user_example",
        created_at=NOW,
    )


def manifest_ref() -> ObjectReference:
    return ObjectReference(
        bucket="scenara-datasets",
        key="datasets/example/1.0.0/manifest.json",
        version="version-1",
        checksum=f"sha256:{'a' * 64}",
        size_bytes=1024,
        content_type="application/json",
    )


def test_dataset_version_requires_legal_state_transitions() -> None:
    validated = version().transition(DatasetVersionStatus.BUILDING).transition(DatasetVersionStatus.VALIDATED)
    published = validated.transition(DatasetVersionStatus.PUBLISHED, manifest_ref=manifest_ref(), occurred_at=NOW)

    assert published.status == DatasetVersionStatus.PUBLISHED
    assert published.manifest_ref == manifest_ref()
    with pytest.raises(ValueError, match="illegal dataset version transition"):
        published.transition(DatasetVersionStatus.VALIDATED)


def test_published_version_cannot_exist_without_manifest() -> None:
    with pytest.raises(ValidationError, match="immutable manifest"):
        version(DatasetVersionStatus.PUBLISHED)


def test_domain_timestamps_require_timezone() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        DatasetVersion(
            dataset_version_id="dsv_example",
            dataset_id="dataset.example",
            version="1.0.0",
            created_by="user_example",
            created_at=datetime(2026, 8, 15, 10, 30),
        )


def test_object_reference_rejects_local_paths() -> None:
    with pytest.raises(ValidationError, match="portable object key"):
        ObjectReference(
            bucket="scenara-datasets",
            key="C:\\data\\manifest.json",
            checksum=f"sha256:{'a' * 64}",
            size_bytes=1,
            content_type="application/json",
        )
