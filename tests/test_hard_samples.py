from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from scenara_data.api.container import build_container
from scenara_data.application.errors import InputValidationError
from scenara_data.config import Settings
from scenara_data.domain.models import HardSampleHandoff, HardSampleManifest, JobStatus, ObjectReference
from scenara_data.ports.interfaces import RequestContext

NOW = datetime(2026, 9, 5, tzinfo=UTC)
CONTEXT = RequestContext(
    tenant_id="tenant-a",
    project_id="project-a",
    principal_id="hard-sample-service",
    principal_type="service_account",
    permission_scopes=("data.hard_sample.import", "data.sample.create", "data.dataset.read"),
    product_entitlements=("scenara.data",),
    request_id="req-hard-sample",
    trace_id="0123456789abcdef0123456789abcdef",
)


def test_failed_hard_sample_manifest_is_not_stuck_queued_and_can_retry() -> None:
    container = build_container(Settings())
    content = b"hard-sample"
    source_ref = ObjectReference(
        bucket="core-media",
        key="incoming/hard-sample.jpg",
        version="version:source-1",
        checksum=f"sha256:{hashlib.sha256(content).hexdigest()}",
        size_bytes=len(content),
        content_type="image/jpeg",
    )
    container.object_storage.register_external(source_ref, content)
    manifest = HardSampleManifest(
        manifest_id="hsm_retryable_failure",
        source_system="scenara",
        generated_at=NOW,
        items=(
            HardSampleHandoff(
                handoff_id="fb_retryable_failure",
                source_result_id="rst_retryable_failure",
                source_ref=source_ref,
                reason="false_positive",
                approved=True,
                authorized=True,
                deidentified=True,
                occurred_at=NOW,
            ),
        ),
    )

    # 缺少 dataset_id 的构建请求会在物化阶段失败；此前该路径会永久留下 queued 记录。
    with pytest.raises(InputValidationError, match="dataset_id"):
        container.hard_samples.ingest_manifest(manifest, CONTEXT, build_version="1.0.0")

    failed = container.repository.find_hard_sample_import_by_manifest(
        manifest.manifest_id, CONTEXT.organization_id, CONTEXT.project_id
    )
    assert failed is not None
    assert failed.status == JobStatus.FAILED
    assert failed.completed_at is not None
    assert failed.error_code == "VALIDATION_FAILED"

    # 相同清单会重新执行，而不是把失败的 queued/failed 状态伪装成成功重放。
    with pytest.raises(InputValidationError, match="dataset_id"):
        container.hard_samples.ingest_manifest(manifest, CONTEXT, build_version="1.0.0")
    retried = container.repository.find_hard_sample_import_by_manifest(
        manifest.manifest_id, CONTEXT.organization_id, CONTEXT.project_id
    )
    assert retried is not None
    assert retried.status == JobStatus.FAILED
    assert retried.import_id == failed.import_id
