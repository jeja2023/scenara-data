from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_DATABASE_URL = "postgresql://scenara_data@127.0.0.1:5432/scenara_data"
DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/1"
DEFAULT_OBJECT_STORAGE_ENDPOINT = "http://127.0.0.1:9000"
DEFAULT_DATASET_BUCKET = "scenara-datasets"
DEFAULT_DEV_SERVICE_TOKEN = "scenara-data-dev-token"

# 规范 63 定义的成熟度阶梯；本仓库未完成目标环境资格验证，最高只能声明 implemented。
MATURITY_LEVELS = ("planned", "seed", "implemented", "qualified", "production_ready")
DECLARED_MATURITY = "implemented"
RUNTIME_MODES = ("memory", "postgres")


@dataclass(frozen=True, slots=True)
class Settings:
    service_name: str = "scenara-data"
    maturity: str = DECLARED_MATURITY
    runtime_mode: str = "memory"
    database_url: str = DEFAULT_DATABASE_URL
    redis_url: str | None = None
    object_storage_endpoint: str = DEFAULT_OBJECT_STORAGE_ENDPOINT
    object_storage_region: str = "us-east-1"
    object_storage_access_key: str | None = None
    object_storage_secret_key: str | None = None
    dataset_bucket: str = DEFAULT_DATASET_BUCKET
    import_bucket: str = "scenara-data-imports"
    export_bucket: str = "scenara-data-exports"
    manifest_bucket: str = "scenara-data-manifests"
    backup_bucket: str = "scenara-data-backups"
    artifact_bucket: str = "scenara-artifacts"
    trusted_service_token: str = DEFAULT_DEV_SERVICE_TOKEN
    access_grant_max_ttl_seconds: int = 86400
    outbox_batch_size: int = 100
    outbox_max_attempts: int = 8
    event_producer: str = "scenara-data"
    core_event_endpoint: str | None = None
    core_event_token: str | None = None
    core_event_timeout_seconds: float = 5.0
    allowed_source_systems: tuple[str, ...] = field(default=("scenara", "scenara-core"))
    cors_allow_origins: tuple[str, ...] = field(
        default=(
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:4173",
            "http://localhost:4173",
        )
    )

    @property
    def is_production_candidate(self) -> bool:
        """postgres 运行模式代表真实事实存储，内存模式只用于开发和单元测试。"""
        return self.runtime_mode == "postgres"


def _optional(name: str) -> str | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return value.strip()


def _positive_int(name: str, default: int) -> int:
    raw = _optional(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} 必须是正整数") from exc
    if value <= 0:
        raise RuntimeError(f"{name} 必须是正整数")
    return value


def load_settings() -> Settings:
    runtime_mode = os.getenv("SCENARA_DATA_RUNTIME_MODE", "memory").strip().lower()
    if runtime_mode not in RUNTIME_MODES:
        raise RuntimeError(f"不支持的 SCENARA_DATA_RUNTIME_MODE：{runtime_mode}")

    maturity = os.getenv("SCENARA_DATA_MATURITY", DECLARED_MATURITY).strip()
    if maturity not in MATURITY_LEVELS:
        raise RuntimeError(f"不支持的 SCENARA_DATA_MATURITY：{maturity}")
    if MATURITY_LEVELS.index(maturity) > MATURITY_LEVELS.index(DECLARED_MATURITY):
        # 规范 63/72：缺少资格与发布证据时不得对外声明更高成熟度。
        raise RuntimeError(f"当前仓库证据链只支持声明 {DECLARED_MATURITY} 或更低成熟度")

    token = os.getenv("SCENARA_DATA_TRUSTED_SERVICE_TOKEN", "").strip()
    if runtime_mode == "postgres":
        if not token:
            raise RuntimeError("PostgreSQL 运行模式必须配置 SCENARA_DATA_TRUSTED_SERVICE_TOKEN")
        if token == DEFAULT_DEV_SERVICE_TOKEN:
            raise RuntimeError("PostgreSQL 运行模式拒绝使用开发默认服务令牌")
    elif not token:
        token = DEFAULT_DEV_SERVICE_TOKEN

    source_systems = tuple(
        sorted(
            {
                item.strip()
                for item in os.getenv(
                    "SCENARA_DATA_ALLOWED_SOURCE_SYSTEMS", "scenara,scenara-core"
                ).split(",")
                if item.strip()
            }
        )
    )
    if not source_systems:
        raise RuntimeError("SCENARA_DATA_ALLOWED_SOURCE_SYSTEMS 不能为空")

    event_endpoint = _optional("SCENARA_DATA_CORE_EVENT_ENDPOINT")
    event_token = _optional("SCENARA_DATA_CORE_EVENT_TOKEN")
    if event_endpoint is not None and not event_token:
        raise RuntimeError("配置事件投递地址时必须同时配置 SCENARA_DATA_CORE_EVENT_TOKEN")
    if runtime_mode == "postgres" and (not event_endpoint or not event_token):
        raise RuntimeError("PostgreSQL 运行模式要求配置 Core 事件投递地址和服务令牌")

    cors_origins = tuple(
        sorted(
            {
                item.strip()
                for item in os.getenv(
                    "SCENARA_DATA_CORS_ALLOW_ORIGINS",
                    "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:4173,http://localhost:4173",
                ).split(",")
                if item.strip()
            }
        )
    )

    return Settings(
        maturity=maturity,
        runtime_mode=runtime_mode,
        database_url=os.getenv("SCENARA_DATA_DATABASE_URL", DEFAULT_DATABASE_URL),
        redis_url=_optional("SCENARA_DATA_REDIS_URL"),
        object_storage_endpoint=os.getenv("SCENARA_DATA_S3_ENDPOINT_URL", DEFAULT_OBJECT_STORAGE_ENDPOINT),
        object_storage_region=os.getenv("SCENARA_DATA_S3_REGION", "us-east-1"),
        object_storage_access_key=_optional("SCENARA_DATA_S3_ACCESS_KEY_ID"),
        object_storage_secret_key=_optional("SCENARA_DATA_S3_SECRET_ACCESS_KEY"),
        dataset_bucket=os.getenv("SCENARA_DATA_DATASET_BUCKET", DEFAULT_DATASET_BUCKET),
        import_bucket=os.getenv("SCENARA_DATA_IMPORT_BUCKET", "scenara-data-imports"),
        export_bucket=os.getenv("SCENARA_DATA_EXPORT_BUCKET", "scenara-data-exports"),
        manifest_bucket=os.getenv("SCENARA_DATA_MANIFEST_BUCKET", "scenara-data-manifests"),
        backup_bucket=os.getenv("SCENARA_DATA_BACKUP_BUCKET", "scenara-data-backups"),
        artifact_bucket=os.getenv("SCENARA_DATA_ARTIFACT_BUCKET", "scenara-artifacts"),
        trusted_service_token=token,
        access_grant_max_ttl_seconds=_positive_int("SCENARA_DATA_ACCESS_GRANT_MAX_TTL_SECONDS", 86400),
        outbox_batch_size=_positive_int("SCENARA_DATA_OUTBOX_BATCH_SIZE", 100),
        outbox_max_attempts=_positive_int("SCENARA_DATA_OUTBOX_MAX_ATTEMPTS", 8),
        core_event_endpoint=event_endpoint,
        core_event_token=event_token,
        core_event_timeout_seconds=float(_positive_int("SCENARA_DATA_CORE_EVENT_TIMEOUT_SECONDS", 5)),
        allowed_source_systems=source_systems,
        cors_allow_origins=cors_origins,
    )
