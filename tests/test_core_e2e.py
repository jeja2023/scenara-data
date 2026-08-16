from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

from scenara_data.adapters.migration_package import FilesystemMigrationPackage
from scenara_data.api.app import create_app
from scenara_data.api.container import build_container
from scenara_data.config import DEFAULT_DEV_SERVICE_TOKEN, Settings
from scenara_data.domain.models import JobStatus, ObjectReference
from scenara_data.ports.interfaces import RequestContext

CORE_REPO = Path(os.getenv("SCENARA_CORE_REPO", Path(__file__).resolve().parents[2] / "scenara"))
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not (CORE_REPO / "scenara" / "platform").is_dir(), reason="scenara Core checkout unavailable"),
]


@dataclass(frozen=True, slots=True)
class FakeAsset:
    object_key: str
    sha256: str
    size_bytes: int
    content_type: str


class FakeAssets:
    def __init__(self, assets: dict[str, FakeAsset]) -> None:
        self._assets = assets

    async def get_asset(self, tenant_id: str, project_id: str, asset_id: str) -> FakeAsset | None:
        assert tenant_id == "tenant-a"
        assert project_id == "project-a"
        return self._assets.get(asset_id)


class MigrationState:
    def __init__(self, dataset: object, version: object, asset: object) -> None:
        self._dataset = dataset
        self._version = version
        self._asset = asset

    async def list_datasets(self, tenant_id: str, project_id: str, *, offset: int, limit: int):
        return [self._dataset] if offset == 0 else []

    async def list_dataset_versions(
        self, tenant_id: str, project_id: str, dataset_id: str, *, offset: int, limit: int
    ):
        return [self._version] if offset == 0 else []

    async def get_asset(self, tenant_id: str, project_id: str, asset_id: str):
        return self._asset if asset_id == "ast_migration" else None

    async def audit_events(self, tenant_id: str, project_id: str, *, limit: int | None):
        return []


class EmptyMigrationFacts:
    async def list_annotation_providers(self, context: object):
        return []

    async def list_annotation_tasks(self, context: object):
        return []

    async def list_manifests(self, context: object):
        return []


def _hard_sample_digest(values: dict[str, object]) -> str:
    signed = {
        key: values[key]
        for key in ("schema_version", "dataset_id", "version", "label_schema", "split", "items")
    }
    content = json.dumps(signed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


@pytest.mark.asyncio
async def test_core_gateway_against_real_data_asgi() -> None:
    sys.path.insert(0, str(CORE_REPO))
    from scenara.platform.control_plane import (
        CreateAnnotationProviderRequest,
        CreateAnnotationTaskRequest,
        ReviewAnnotationTaskRequest,
    )
    from scenara.platform.data_platform import HttpDataPlatformClient
    from scenara.platform.feedback import FeedbackKind, HardSampleItem, HardSampleManifest
    from scenara.platform.models import CreateDatasetRequest, PrincipalContext, UpdateDatasetRequest

    content = b"cross-repository-e2e-image"
    digest = hashlib.sha256(content).hexdigest()
    asset = FakeAsset(
        object_key="media/ast_e2e.jpg",
        sha256=digest,
        size_bytes=len(content),
        content_type="image/jpeg",
    )
    application = create_app(Settings())
    source_ref = ObjectReference(
        bucket="scenara-media",
        key=asset.object_key,
        checksum=f"sha256:{digest}",
        size_bytes=len(content),
        content_type=asset.content_type,
    )
    application.state.container.object_storage.register_external(source_ref, content)
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://scenara-data") as data_http:
        gateway = HttpDataPlatformClient(
            "http://scenara-data",
            service_token=DEFAULT_DEV_SERVICE_TOKEN,
            client=data_http,
            source_assets=FakeAssets({"ast_e2e": asset}),
            source_bucket="scenara-media",
        )
        context = PrincipalContext(
            tenant_id="tenant-a",
            project_id="project-a",
            principal_id="user-a",
            scopes=frozenset(
                {
                    "data.dataset.create",
                    "data.dataset.read",
                    "data.dataset.update",
                    "data.sample.create",
                    "data.sample.read",
                    "data.annotation.create",
                    "data.annotation.review",
                    "data.hard_sample.import",
                }
            ),
            product_ids=frozenset({"scenara.data"}),
            request_id="core-data-e2e",
        )

        dataset = await gateway.create_dataset(context, CreateDatasetRequest(name="Core E2E dataset"))
        dataset = await gateway.update_dataset(
            context, dataset.dataset_id, UpdateDatasetRequest(status="active")
        )
        provider = await gateway.register_annotation_provider(
            context,
            CreateAnnotationProviderRequest(
                name="Core E2E provider", kind="internal", endpoint="https://annotator.invalid/api"
            ),
        )
        probed = await gateway.probe_annotation_provider(context, provider.record_id)
        assert probed.last_health == "configured"

        task = await gateway.create_annotation_task(
            context,
            CreateAnnotationTaskRequest(
                asset_ids=["ast_e2e"],
                schema_name="scenara.person.v1",
                assignee="annotator-a",
                labels={"person": "candidate"},
            ),
        )
        assert task.asset_ids == ["ast_e2e"]
        assert task.status == "in_review"
        reviewed = await gateway.review_annotation_task(
            context,
            task.record_id,
            ReviewAnnotationTaskRequest(approved=True, consistency_score=0.98, comment="accepted"),
        )
        assert reviewed.status == "approved"
        assert reviewed.consistency_score == 0.98

        item = HardSampleItem(
            feedback_id="fb_e2e",
            kind=FeedbackKind.FALSE_POSITIVE,
            media_ref="ast_e2e",
            result_ref="result_e2e#sha256=" + "b" * 64,
            model_id="person-reid",
            model_version="1.0.0",
            pipeline_id="portrait.pipeline",
            pipeline_version="1.0.0",
            correction={"label": "hard"},
        )
        manifest_values: dict[str, object] = {
            "schema_version": "1.0",
            "manifest_id": "hsm_e2e",
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "dataset_id": dataset.dataset_id,
            "version": "1.0.0",
            "label_schema": "scenara.feedback.correction.v1",
            "split": "train",
            "items": [item.model_dump(mode="json")],
            "created_by": "user-a",
            "created_at": 1.0,
        }
        manifest_values["sha256"] = _hard_sample_digest(manifest_values)
        intake = await gateway.submit_hard_sample_manifest(
            context, HardSampleManifest.model_validate(manifest_values)
        )
        assert intake["status"] == "succeeded"
        assert intake["accepted_count"] == 1


@pytest.mark.asyncio
async def test_core_export_is_imported_by_data(tmp_path: Path) -> None:
    sys.path.insert(0, str(CORE_REPO))
    from scenara.platform.data_migration import export_data_migration_package
    from scenara.platform.models import DatasetRecord, DatasetVersion

    content = b"migration-object"
    digest = hashlib.sha256(content).hexdigest()
    dataset = DatasetRecord(
        dataset_id="dst_migration",
        tenant_id="tenant-a",
        project_id="project-a",
        name="Migration E2E",
        status="active",
        created_at=1.0,
        updated_at=2.0,
    )
    version = DatasetVersion(
        version_id="dsv_migration",
        dataset_id=dataset.dataset_id,
        tenant_id="tenant-a",
        project_id="project-a",
        version="1.0.0",
        status="published",
        manifest_sha256="a" * 64,
        asset_ids=["ast_migration"],
        item_count=1,
        created_by="migration-user",
        created_at=1.0,
        updated_at=2.0,
    )
    asset = type(
        "MigrationAsset",
        (),
        {
            "asset_id": "ast_migration",
            "object_key": "media/ast_migration.jpg",
            "sha256": digest,
            "size_bytes": len(content),
            "content_type": "image/jpeg",
            "filename": "ast_migration.jpg",
            "created_at": 1.0,
            "deleted_at": None,
            "original_deleted_at": None,
        },
    )()
    package_path = tmp_path / "migration-package"
    empty_facts = EmptyMigrationFacts()
    await export_data_migration_package(
        state=MigrationState(dataset, version, asset),
        control_plane=empty_facts,
        feedback=empty_facts,
        tenant_id="tenant-a",
        project_id="project-a",
        output_dir=package_path,
        source_version="0.3.0.dev22",
        source_bucket="scenara-media",
    )

    container = build_container(Settings())
    source_ref = ObjectReference(
        bucket="scenara-media",
        key=asset.object_key,
        checksum=f"sha256:{digest}",
        size_bytes=len(content),
        content_type=asset.content_type,
    )
    container.object_storage.register_external(source_ref, content)
    context = RequestContext(
        tenant_id="tenant-a",
        project_id="project-a",
        principal_id="migration-service",
        principal_type="service_account",
        permission_scopes=("data.import.execute", "data.dataset.read"),
        product_entitlements=("scenara.data",),
        request_id="migration-e2e",
        trace_id="0123456789abcdef0123456789abcdef",
    )
    report = container.migrations.import_package(
        FilesystemMigrationPackage(package_path), context
    )
    assert report.status == JobStatus.SUCCEEDED, report.failures
    imported = container.repository.get_dataset_version(
        version.version_id, context.tenant_id, context.project_id
    )
    assert imported.manifest_ref is not None
    assert imported.manifest_ref.checksum != f"sha256:{version.manifest_sha256}"
    members = container.repository.list_version_samples(
        version.version_id, context.tenant_id, context.project_id
    )
    assert [item.sample_id for item in members] == ["ast_migration"]
