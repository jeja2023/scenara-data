from __future__ import annotations

import hashlib
import importlib
import os
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from scenara_data.api.app import create_app
from scenara_data.config import Settings
from scenara_data.domain.models import ObjectReference

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"


def integration_settings() -> Settings:
    return Settings(
        runtime_mode="postgres",
        database_url=os.getenv(
            "SCENARA_DATA_INTEGRATION_DATABASE_URL",
            "postgresql://scenara_data:data-dev-only@127.0.0.1:5432/scenara_data",
        ),
        redis_url=os.getenv("SCENARA_DATA_INTEGRATION_REDIS_URL", "redis://127.0.0.1:6379/1"),
        object_storage_endpoint=os.getenv(
            "SCENARA_DATA_INTEGRATION_S3_ENDPOINT_URL", "http://127.0.0.1:9000"
        ),
        object_storage_access_key=os.getenv(
            "SCENARA_DATA_INTEGRATION_S3_ACCESS_KEY_ID", "scenara-data"
        ),
        object_storage_secret_key=os.getenv(
            "SCENARA_DATA_INTEGRATION_S3_SECRET_ACCESS_KEY", "data-dev-only"
        ),
        trusted_service_token=os.getenv("SCENARA_DATA_INTEGRATION_SERVICE_TOKEN", "integration-token"),
        core_event_endpoint=os.getenv(
            "SCENARA_DATA_INTEGRATION_EVENT_ENDPOINT", "http://127.0.0.1:18080/internal/v1/data/events"
        ),
        core_event_token=os.getenv(
            "SCENARA_DATA_INTEGRATION_EVENT_TOKEN", "integration-event-token"
        ),
    )


def headers(idempotency_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.getenv('SCENARA_DATA_INTEGRATION_SERVICE_TOKEN', 'integration-token')}",
        "X-Scenara-Tenant-Id": "tenant-a",
        "X-Scenara-Project-Id": "project-a",
        "X-Scenara-Principal-Id": "integration-user",
        "X-Scenara-Principal-Type": "service_account",
        "X-Scenara-Permission-Scopes": ",".join(
            [
                "data.dataset.create",
                "data.dataset.read",
                "data.dataset.update",
                "data.dataset.publish",
                "data.sample.create",
                "data.sample.read",
                "data.quality.run",
                "data.export.execute",
            ]
        ),
        "X-Scenara-Product-Entitlements": "scenara.data",
        "X-Request-Id": f"req-{idempotency_key}",
        "X-Trace-Id": "0123456789abcdef0123456789abcdef",
        "Idempotency-Key": idempotency_key,
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_redis_and_s3_dependencies_work_together() -> None:
    if os.getenv("SCENARA_RUN_INTEGRATION") != "1":
        pytest.skip("设置 SCENARA_RUN_INTEGRATION=1 后运行真实的 PostgreSQL/Redis/MinIO 集成测试")
    boto3 = pytest.importorskip("boto3")
    botocore = pytest.importorskip("botocore")
    settings = integration_settings()
    prepare_postgres_schema(settings.database_url)
    app = create_app(settings=settings)
    app.state.container.lock = scenara_redis_lock(settings.redis_url or "redis://127.0.0.1:6379/1")
    suffix = uuid4().hex[:8]
    dataset_id = f"dst_integration_{suffix}"
    sample_id = f"smp_integration_{suffix}"
    version_id = f"dsv_integration_{suffix}"
    object_key = f"incoming/integration-{suffix}.jpg"

    content = b"integration-sample"
    digest = hashlib.sha256(content).hexdigest()
    client = boto3.client(
        "s3",
        endpoint_url=settings.object_storage_endpoint,
        region_name=settings.object_storage_region,
        aws_access_key_id=settings.object_storage_access_key,
        aws_secret_access_key=settings.object_storage_secret_key,
    )
    for bucket in {
        settings.dataset_bucket,
        settings.manifest_bucket,
        settings.import_bucket,
        settings.export_bucket,
        settings.artifact_bucket,
    }:
        try:
            client.create_bucket(Bucket=bucket)
        except botocore.exceptions.ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code not in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
                raise
    client.put_object(
        Bucket="scenara-datasets",
        Key=object_key,
        Body=content,
        ContentType="image/jpeg",
        Metadata={"sha256": digest},
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as api:
        ready = await api.get("/readyz")
        assert ready.status_code == 200, ready.text
        checks = ready.json()["checks"]
        assert checks == {"repository": True, "object_storage": True, "lock": True}

        created = await api.post(
            "/internal/v1/datasets",
            headers=headers("create-dataset"),
            json={"dataset_id": dataset_id, "name": f"Integration dataset {suffix}"},
        )
        assert created.status_code == 201, created.text
        activated = await api.patch(
            f"/internal/v1/datasets/{dataset_id}",
            headers=headers("activate-dataset"),
            json={"status": "active"},
        )
        assert activated.status_code == 200, activated.text

        sample = await api.post(
            "/internal/v1/samples",
            headers=headers("create-sample"),
            json={
                "sample_id": sample_id,
                "source_ref": {
                    "bucket": "scenara-datasets",
                    "key": object_key,
                    "version": None,
                    "checksum": f"sha256:{digest}",
                    "size_bytes": len(content),
                    "content_type": "image/jpeg",
                },
                "media_type": "image/jpeg",
                "source_lineage": ["integration.result"],
                "source_system": "scenara",
                "source_resource_type": "media_asset",
                "source_resource_id": "ast_integration",
                "dataset_split": "train",
            },
        )
        assert sample.status_code == 201, sample.text

        version = await api.post(
            f"/internal/v1/datasets/{dataset_id}/versions",
            headers=headers("create-version"),
            json={"dataset_version_id": version_id, "version": "1.0.0"},
        )
        assert version.status_code == 201, version.text
        building = await api.post(
            f"/internal/v1/dataset-versions/{version_id}/transition",
            headers=headers("transition-building"),
            json={"status": "building"},
        )
        assert building.status_code == 200, building.text
        membership = await api.post(
            f"/internal/v1/dataset-versions/{version_id}/samples",
            headers=headers("version-sample"),
            json={"sample_id": sample_id},
        )
        assert membership.status_code == 200, membership.text
        validated = await api.post(
            f"/internal/v1/dataset-versions/{version_id}/validate",
            headers=headers("validate-version"),
            json={},
        )
        assert validated.status_code == 200, validated.text
        published = await api.post(
            f"/internal/v1/dataset-versions/{version_id}/publish",
            headers=headers("publish-version"),
        )
        assert published.status_code == 200, published.text
        manifest = published.json()["manifest"]
        manifest_ref = ObjectReference.model_validate(manifest["manifest_ref"])

    storage = app.state.container.object_storage
    payload = storage.read_verified(manifest_ref)
    assert sample_id.encode("ascii") in payload
    assert manifest_ref.bucket == settings.manifest_bucket


def scenara_redis_lock(redis_url: str):
    redis = importlib.import_module("redis")
    from scenara_data.adapters.redis import RedisLockProvider

    client = redis.Redis.from_url(redis_url, protocol=2)
    return RedisLockProvider(redis_url, client=client)


def prepare_postgres_schema(database_url: str) -> None:
    psycopg = importlib.import_module("psycopg")
    with psycopg.connect(database_url, autocommit=True) as connection, connection.cursor() as cursor:
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
            digest = hashlib.sha256(content).hexdigest()
            cursor.execute("SELECT sha256 FROM data_schema_migrations WHERE version = %s", (version,))
            previous = cursor.fetchone()
            if previous is not None:
                if previous[0] != digest:
                    raise RuntimeError(f"已应用的迁移 {version} 发生变化")
                continue
            cursor.execute(content.decode("utf-8"))
            cursor.execute(
                "INSERT INTO data_schema_migrations (version, sha256) VALUES (%s, %s)",
                (version, digest),
            )
