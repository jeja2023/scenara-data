from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
import pytest

from scenara_data.api.app import create_app
from scenara_data.config import DEFAULT_DEV_SERVICE_TOKEN, Settings
from scenara_data.domain.models import ObjectReference

ALL_SCOPES = (
    "data.dataset.create",
    "data.dataset.read",
    "data.dataset.update",
    "data.dataset.publish",
    "data.dataset.archive",
    "data.sample.create",
    "data.sample.read",
    "data.annotation.create",
    "data.annotation.review",
    "data.quality.run",
    "data.lineage.read",
    "data.import.execute",
    "data.export.execute",
    "data.hard_sample.import",
)


@dataclass(slots=True)
class ApiClient:
    app: object
    http: httpx.AsyncClient

    async def get(self, url: str, **kwargs: object) -> httpx.Response:
        return await self.http.get(url, **kwargs)

    async def post(self, url: str, **kwargs: object) -> httpx.Response:
        return await self.http.post(url, **kwargs)

    async def patch(self, url: str, **kwargs: object) -> httpx.Response:
        return await self.http.patch(url, **kwargs)


@pytest.fixture
async def client() -> AsyncIterator[ApiClient]:
    application = create_app(Settings())
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield ApiClient(app=application, http=http_client)


def headers(
    *,
    tenant_id: str = "tenant-a",
    project_id: str = "project-a",
    scopes: tuple[str, ...] = ALL_SCOPES,
    idempotency_key: str | None = None,
) -> dict[str, str]:
    result = {
        "Authorization": f"Bearer {DEFAULT_DEV_SERVICE_TOKEN}",
        "X-Scenara-Tenant-Id": tenant_id,
        "X-Scenara-Project-Id": project_id,
        "X-Scenara-Principal-Id": "user-a",
        "X-Scenara-Principal-Type": "user",
        "X-Scenara-Permission-Scopes": ",".join(scopes),
        "X-Scenara-Product-Entitlements": "scenara.data",
        "X-Request-Id": "req-api-workflow",
        "X-Trace-Id": "0123456789abcdef0123456789abcdef",
    }
    if idempotency_key is not None:
        result["Idempotency-Key"] = idempotency_key
    return result


def object_reference(content: bytes, *, key: str) -> ObjectReference:
    return ObjectReference(
        bucket="core-media",
        key=key,
        version="version:source-1",
        checksum=f"sha256:{hashlib.sha256(content).hexdigest()}",
        size_bytes=len(content),
        content_type="image/jpeg",
    )


@pytest.mark.asyncio
async def test_request_validation_error_messages_are_localized(client: ApiClient) -> None:
    response = await client.post(
        "/internal/v1/datasets",
        headers=headers(idempotency_key="localized-validation"),
        json={"name": ""},
    )

    assert response.status_code == 422
    violations = response.json()["error"]["details"]["violations"]
    assert any(item["message"] == "字符串长度不足" for item in violations)


async def create_active_dataset(client: ApiClient, dataset_id: str) -> None:
    created = await client.post(
        "/internal/v1/datasets",
        headers=headers(idempotency_key=f"create-{dataset_id}"),
        json={"dataset_id": dataset_id, "name": dataset_id},
    )
    assert created.status_code == 201, created.text
    activated = await client.patch(
        f"/internal/v1/datasets/{dataset_id}",
        headers=headers(idempotency_key=f"activate-{dataset_id}"),
        json={"status": "active"},
    )
    assert activated.status_code == 200, activated.text


async def create_sample(client: ApiClient, sample_id: str, reference: ObjectReference) -> None:
    response = await client.post(
        "/internal/v1/samples",
        headers=headers(idempotency_key=f"create-{sample_id}"),
        json={
            "sample_id": sample_id,
            "source_ref": reference.model_dump(mode="json"),
            "media_type": "image/jpeg",
            "source_lineage": ["result.source"],
            "source_system": "scenara",
            "source_resource_type": "result",
            "source_resource_id": "result.source",
            "person_id": "person-1",
            "camera_id": "camera-1",
            "bbox": [1.0, 2.0, 30.0, 40.0],
            "dataset_split": "train",
        },
    )
    assert response.status_code == 201, response.text


async def create_building_version(
    client: ApiClient, *, dataset_id: str, version_id: str, sample_id: str
) -> None:
    created = await client.post(
        f"/internal/v1/datasets/{dataset_id}/versions",
        headers=headers(idempotency_key=f"create-{version_id}"),
        json={"dataset_version_id": version_id, "version": "1.0.0"},
    )
    assert created.status_code == 201, created.text
    building = await client.post(
        f"/internal/v1/dataset-versions/{version_id}/transition",
        headers=headers(idempotency_key=f"build-{version_id}"),
        json={"status": "building"},
    )
    assert building.status_code == 200, building.text
    membership = await client.post(
        f"/internal/v1/dataset-versions/{version_id}/samples",
        headers=headers(idempotency_key=f"sample-{version_id}"),
        json={"sample_id": sample_id},
    )
    assert membership.status_code == 200, membership.text


@pytest.mark.asyncio
async def test_authentication_authorization_and_tenant_isolation(client: ApiClient) -> None:
    unauthenticated = await client.get("/internal/v1/datasets")
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "UNAUTHENTICATED"

    forbidden = await client.post(
        "/internal/v1/datasets",
        headers=headers(scopes=("data.dataset.read",), idempotency_key="forbidden-create"),
        json={"dataset_id": "dst_forbidden", "name": "forbidden"},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"] == {
        "code": "FORBIDDEN",
        "message": "当前身份没有执行该操作的权限",
        "details": {"required_permission": "data.dataset.create"},
    }

    created = await client.post(
        "/internal/v1/datasets",
        headers=headers(idempotency_key="tenant-create"),
        json={"dataset_id": "dst_tenant", "name": "tenant scoped"},
    )
    assert created.status_code == 201

    hidden = await client.get(
        "/internal/v1/datasets/dst_tenant",
        headers=headers(tenant_id="tenant-b", project_id="project-b"),
    )
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_idempotency_replays_the_original_response_and_rejects_changed_payload(
    client: ApiClient,
) -> None:
    request_headers = headers(idempotency_key="dataset-idempotency")
    payload = {"dataset_id": "dst_idempotency", "name": "first"}

    first = await client.post("/internal/v1/datasets", headers=request_headers, json=payload)
    replay = await client.post("/internal/v1/datasets", headers=request_headers, json=payload)
    conflict = await client.post(
        "/internal/v1/datasets",
        headers=request_headers,
        json={"dataset_id": "dst_idempotency", "name": "changed"},
    )

    assert first.status_code == 201
    assert first.headers["X-Idempotent-Replay"] == "false"
    assert replay.status_code == 201
    assert replay.headers["X-Idempotent-Replay"] == "true"
    assert replay.json() == first.json()
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    listed = await client.get("/internal/v1/datasets", headers=headers())
    assert listed.status_code == 200
    assert listed.json()["total"] == 1


@pytest.mark.asyncio
async def test_dataset_version_publish_freezes_manifest_and_exposes_model_reference(
    client: ApiClient,
) -> None:
    content = b"person re-identification sample"
    reference = object_reference(content, key="incoming/person 1.jpg")
    client.app.state.container.object_storage.register_external(reference, content)

    await create_active_dataset(client, "dst_lifecycle")
    await create_sample(client, "smp_lifecycle", reference)
    await create_building_version(
        client,
        dataset_id="dst_lifecycle",
        version_id="dsv_lifecycle",
        sample_id="smp_lifecycle",
    )

    validated = await client.post(
        "/internal/v1/dataset-versions/dsv_lifecycle/validate",
        headers=headers(idempotency_key="validate-lifecycle"),
        json={},
    )
    assert validated.status_code == 200, validated.text
    assert validated.json()["dataset_version"]["status"] == "ready"
    assert validated.json()["quality_report"]["status"] == "passed"

    published = await client.post(
        "/internal/v1/dataset-versions/dsv_lifecycle/publish",
        headers=headers(idempotency_key="publish-lifecycle"),
    )
    assert published.status_code == 200, published.text
    version = published.json()["dataset_version"]
    assert version["status"] == "published"
    assert version["sample_count"] == 1
    assert version["manifest_sha256"] == version["manifest_ref"]["checksum"]
    assert version["quality_report_id"]
    assert version["lineage_snapshot_id"]
    assert version["annotation_snapshot_id"]

    manifest = await client.get(
        "/internal/v1/dataset-versions/dsv_lifecycle/manifest", headers=headers()
    )
    assert manifest.status_code == 200
    assert manifest.json()["sample_count"] == 1
    assert manifest.json()["split_counts"] == {"train": 1}
    assert manifest.json()["samples"][0]["content_ref"]["bucket"] == "scenara-datasets"

    grant = await client.post(
        "/internal/v1/dataset-versions/dsv_lifecycle/access-grants",
        headers=headers(idempotency_key="grant-lifecycle"),
        json={
            "service_account_id": "service-model",
            "permissions": ["manifest.read"],
            "ttl_seconds": 300,
        },
    )
    assert grant.status_code == 201, grant.text
    assert grant.json()["manifest_url"].startswith("https://object-storage.invalid/")

    model_reference = await client.get(
        "/internal/v1/dataset-versions/dsv_lifecycle/reference", headers=headers()
    )
    assert model_reference.status_code == 200
    reference_payload = model_reference.json()
    assert reference_payload["schema_version"] == "1.0"
    assert reference_payload["dataset_id"] == "dst_lifecycle"
    assert reference_payload["version"] == "1.0.0"
    assert reference_payload["manifest_sha256"] == version["manifest_ref"]["checksum"].removeprefix("sha256:")
    assert reference_payload["manifest_uri"].endswith(reference_payload["manifest_sha256"])
    assert reference_payload["lineage_refs"]
    assert reference_payload["authorization_id"] == grant.json()["grant"]["grant_id"]
    assert reference_payload["authorized_consumer_repository_ids"] == ["scenara-model"]

    immutable = await client.post(
        "/internal/v1/dataset-versions/dsv_lifecycle/samples",
        headers=headers(idempotency_key="mutate-published"),
        json={"sample_id": "smp_lifecycle"},
    )
    assert immutable.status_code == 409
    assert immutable.json()["error"]["code"] == "INVALID_STATE_TRANSITION"

    audit = client.app.state.container.audit
    outbox = client.app.state.container.outbox
    assert "dataset.version.publish" in audit.actions()
    assert "dataset.version.published" in outbox.event_types()


@pytest.mark.asyncio
async def test_failed_quality_run_is_persisted_and_bound_to_failed_version(client: ApiClient) -> None:
    missing = object_reference(b"missing", key="missing/sample.jpg")
    await create_active_dataset(client, "dst_quality_failure")
    await create_sample(client, "smp_quality_failure", missing)
    await create_building_version(
        client,
        dataset_id="dst_quality_failure",
        version_id="dsv_quality_failure",
        sample_id="smp_quality_failure",
    )

    response = await client.post(
        "/internal/v1/dataset-versions/dsv_quality_failure/validate",
        headers=headers(idempotency_key="validate-quality-failure"),
        json={},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["dataset_version"]["status"] == "failed"
    assert payload["quality_report"]["status"] == "failed"
    assert payload["dataset_version"]["quality_report_id"] == payload["quality_report"]["report_id"]
    assert payload["quality_report"]["issue_ids"]
    assert all(value.startswith("dqi_") for value in payload["quality_report"]["issue_ids"])

    run_id = payload["quality_report"]["quality_run_id"]
    issues = await client.get(f"/internal/v1/quality-runs/{run_id}/issues", headers=headers())
    assert issues.status_code == 200
    assert {item["issue_id"] for item in issues.json()["items"]} == set(
        payload["quality_report"]["issue_ids"]
    )

    stored = await client.get(
        "/internal/v1/dataset-versions/dsv_quality_failure", headers=headers()
    )
    assert stored.status_code == 200
    assert stored.json()["status"] == "failed"
