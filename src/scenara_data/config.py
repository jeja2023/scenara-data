from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_DATABASE_URL = "postgresql://scenara_data@127.0.0.1:5432/scenara_data"
DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/1"
DEFAULT_OBJECT_STORAGE_ENDPOINT = "http://127.0.0.1:9000"
DEFAULT_DATASET_BUCKET = "scenara-datasets"
DEFAULT_DEV_SERVICE_TOKEN = "scenara-data-dev-token"
DEFAULT_CONSOLE_USERNAME = "admin"
DEFAULT_CONSOLE_SESSION_TTL_SECONDS = 86400
DEFAULT_CONSOLE_SCOPES = (
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

# 规范 63 定义的成熟度阶梯；本仓库未完成目标环境资格验证，最高只能声明 implemented。
MATURITY_LEVELS = ("planned", "seed", "implemented", "qualified", "production_ready")
DECLARED_MATURITY = "implemented"
RUNTIME_MODES = ("memory", "postgres")
DEPLOYMENT_PROFILES = ("development", "production", "standalone")
INSECURE_SERVICE_TOKENS = frozenset(
    {DEFAULT_DEV_SERVICE_TOKEN, "scenara-data-compose-token", "scenara-data-compose-event-token"}
)


@dataclass(frozen=True, slots=True)
class Settings:
    service_name: str = "scenara-data"
    maturity: str = DECLARED_MATURITY
    runtime_mode: str = "memory"
    deployment_profile: str = "development"
    database_url: str = DEFAULT_DATABASE_URL
    redis_url: str | None = None
    object_storage_endpoint: str = DEFAULT_OBJECT_STORAGE_ENDPOINT
    object_storage_region: str = "us-east-1"
    object_storage_access_key: str | None = None
    object_storage_secret_key: str | None = None
    require_object_versioning: bool = False
    dataset_bucket: str = DEFAULT_DATASET_BUCKET
    import_bucket: str = "scenara-data-imports"
    export_bucket: str = "scenara-data-exports"
    manifest_bucket: str = "scenara-data-manifests"
    backup_bucket: str = "scenara-data-backups"
    artifact_bucket: str = "scenara-artifacts"
    trusted_service_token: str = DEFAULT_DEV_SERVICE_TOKEN
    trusted_service_tokens: tuple[str, ...] = ()
    request_context_signing_key: str | None = None
    require_signed_request_context: bool = False
    request_context_max_age_seconds: int = 300
    access_grant_max_ttl_seconds: int = 86400
    outbox_batch_size: int = 100
    outbox_max_attempts: int = 8
    event_producer: str = "scenara-data"
    core_event_endpoint: str | None = None
    core_event_token: str | None = None
    core_event_timeout_seconds: float = 5.0
    allowed_source_systems: tuple[str, ...] = field(default=("scenara", "scenara-core"))
    console_username: str = DEFAULT_CONSOLE_USERNAME
    console_password: str | None = None
    console_session_secret: str | None = None
    console_session_ttl_seconds: int = DEFAULT_CONSOLE_SESSION_TTL_SECONDS
    console_login_enabled: bool = True
    console_login_max_attempts: int = 5
    console_login_window_seconds: int = 300
    console_tenant_id: str = "default"
    console_project_id: str = "default"
    console_scopes: tuple[str, ...] = DEFAULT_CONSOLE_SCOPES
    console_entitlements: tuple[str, ...] = field(default=("scenara.data",))
    serve_frontend: bool = False
    frontend_dist: Path = Path("/app/frontend-dist")
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

    @property
    def is_production_deployment(self) -> bool:
        return self.deployment_profile == "production"

    def __post_init__(self) -> None:
        if not self.trusted_service_tokens:
            object.__setattr__(self, "trusted_service_tokens", (self.trusted_service_token,))
        if self.console_password is None:
            object.__setattr__(self, "console_password", self.trusted_service_token)
        if self.console_session_secret is None:
            object.__setattr__(self, "console_session_secret", self.trusted_service_token)


def _optional(name: str) -> str | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return value.strip()


def _secret(name: str) -> str | None:
    """读取直接注入值或 Docker/Kubernetes 常用的 ``*_FILE`` 密钥挂载。"""
    value = _optional(name)
    file_name = _optional(f"{name}_FILE")
    if value is not None and file_name is not None:
        raise RuntimeError(f"{name} 与 {name}_FILE 不能同时配置")
    if file_name is None:
        return value
    try:
        content = Path(file_name).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"无法读取 {name}_FILE 指定的密钥文件") from exc
    if not content:
        raise RuntimeError(f"{name}_FILE 指定的密钥文件不能为空")
    return content


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


def _bool(name: str, default: bool) -> bool:
    raw = _optional(name)
    if raw is None:
        return default
    normalized = raw.lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} 必须是 true 或 false")


def _csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                item.strip()
                for item in os.getenv(name, ",".join(default)).split(",")
                if item.strip()
            }
        )
    )


def load_settings() -> Settings:
    runtime_mode = os.getenv("SCENARA_DATA_RUNTIME_MODE", "memory").strip().lower()
    if runtime_mode not in RUNTIME_MODES:
        raise RuntimeError(f"不支持的 SCENARA_DATA_RUNTIME_MODE：{runtime_mode}")
    deployment_profile = os.getenv("SCENARA_DATA_DEPLOYMENT_PROFILE", "development").strip().lower()
    if deployment_profile not in DEPLOYMENT_PROFILES:
        raise RuntimeError(f"不支持的 SCENARA_DATA_DEPLOYMENT_PROFILE：{deployment_profile}")

    maturity = os.getenv("SCENARA_DATA_MATURITY", DECLARED_MATURITY).strip()
    if maturity not in MATURITY_LEVELS:
        raise RuntimeError(f"不支持的 SCENARA_DATA_MATURITY：{maturity}")
    if MATURITY_LEVELS.index(maturity) > MATURITY_LEVELS.index(DECLARED_MATURITY):
        # 规范 63/72：缺少资格与发布证据时不得对外声明更高成熟度。
        raise RuntimeError(f"当前仓库证据链只支持声明 {DECLARED_MATURITY} 或更低成熟度")

    token = _secret("SCENARA_DATA_TRUSTED_SERVICE_TOKEN") or ""
    if runtime_mode == "postgres":
        if not token:
            raise RuntimeError("PostgreSQL 运行模式必须配置 SCENARA_DATA_TRUSTED_SERVICE_TOKEN")
        if token in INSECURE_SERVICE_TOKENS:
            raise RuntimeError("PostgreSQL 运行模式拒绝使用开发默认服务令牌")
    elif not token:
        token = DEFAULT_DEV_SERVICE_TOKEN
    additional_tokens = _secret("SCENARA_DATA_TRUSTED_SERVICE_TOKENS")
    trusted_tokens = tuple(
        sorted(
            {
                value.strip()
                for value in (token + "," + (additional_tokens or "")).replace("\n", ",").replace("\r", ",").split(",")
                if value.strip()
            }
        )
    )

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

    console_username = os.getenv("SCENARA_DATA_CONSOLE_USERNAME", DEFAULT_CONSOLE_USERNAME).strip()
    if not console_username:
        raise RuntimeError("SCENARA_DATA_CONSOLE_USERNAME 不能为空")
    console_scopes = _csv("SCENARA_DATA_CONSOLE_SCOPES", DEFAULT_CONSOLE_SCOPES)
    if not console_scopes:
        raise RuntimeError("SCENARA_DATA_CONSOLE_SCOPES 不能为空")

    event_endpoint = _optional("SCENARA_DATA_CORE_EVENT_ENDPOINT")
    event_token = _secret("SCENARA_DATA_CORE_EVENT_TOKEN")
    if event_endpoint is not None and not event_token:
        raise RuntimeError("配置事件投递地址时必须同时配置 SCENARA_DATA_CORE_EVENT_TOKEN")
    if runtime_mode == "postgres" and deployment_profile != "standalone" and (not event_endpoint or not event_token):
        raise RuntimeError("PostgreSQL 运行模式要求配置 Core 事件投递地址和服务令牌")

    database_url = _secret("SCENARA_DATA_DATABASE_URL") or DEFAULT_DATABASE_URL
    redis_url = _optional("SCENARA_DATA_REDIS_URL")
    object_storage_endpoint = os.getenv("SCENARA_DATA_S3_ENDPOINT_URL", DEFAULT_OBJECT_STORAGE_ENDPOINT)
    object_storage_access_key = _secret("SCENARA_DATA_S3_ACCESS_KEY_ID")
    object_storage_secret_key = _secret("SCENARA_DATA_S3_SECRET_ACCESS_KEY")

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
    context_signing_key = _secret("SCENARA_DATA_REQUEST_CONTEXT_SIGNING_KEY")
    require_signed_context = _bool(
        "SCENARA_DATA_REQUIRE_SIGNED_REQUEST_CONTEXT", deployment_profile == "production"
    )
    console_login_enabled = _bool(
        "SCENARA_DATA_CONSOLE_LOGIN_ENABLED", deployment_profile != "production"
    )
    console_password = _secret("SCENARA_DATA_CONSOLE_PASSWORD") or token
    console_session_secret = _secret("SCENARA_DATA_CONSOLE_SESSION_SECRET") or token
    if deployment_profile in {"production", "standalone"} and console_login_enabled:
        if len(console_password) < 24 or console_password in trusted_tokens:
            raise RuntimeError("工作台登录密码必须独立且至少包含 24 个字符")
        if (
            len(console_session_secret) < 32
            or console_session_secret in trusted_tokens
            or console_session_secret == context_signing_key
            or console_session_secret == console_password
        ):
            raise RuntimeError("工作台会话签名密钥必须独立且至少包含 32 个字符")
    if deployment_profile == "production":
        if runtime_mode != "postgres":
            raise RuntimeError("生产部署必须使用 PostgreSQL 事实存储模式")
        if database_url == DEFAULT_DATABASE_URL or "sslmode=" not in database_url:
            raise RuntimeError("生产部署必须配置数据库连接地址")
        if any(len(value) < 32 or value in INSECURE_SERVICE_TOKENS for value in trusted_tokens):
            raise RuntimeError("生产部署必须配置至少 32 位且非默认的服务凭据")
        if not context_signing_key or len(context_signing_key) < 32 or context_signing_key in trusted_tokens:
            raise RuntimeError("生产部署必须配置独立且至少 32 位的请求上下文签名密钥")
        if not event_endpoint or not event_endpoint.startswith("https://") or len(event_token or "") < 32:
            raise RuntimeError("生产部署的 Core 事件端点必须使用 HTTPS")
        if not object_storage_endpoint.startswith("https://"):
            raise RuntimeError("生产部署的对象存储端点必须使用 HTTPS")
        if not redis_url or not redis_url.startswith("rediss://"):
            raise RuntimeError("生产部署的 Redis 地址必须使用 rediss:// TLS 连接")
        if not cors_origins or any(not origin.startswith("https://") for origin in cors_origins):
            raise RuntimeError("生产部署必须显式配置 HTTPS CORS 来源")

    return Settings(
        maturity=maturity,
        runtime_mode=runtime_mode,
        deployment_profile=deployment_profile,
        database_url=database_url,
        redis_url=redis_url,
        object_storage_endpoint=object_storage_endpoint,
        object_storage_region=os.getenv("SCENARA_DATA_S3_REGION", "us-east-1"),
        object_storage_access_key=object_storage_access_key,
        object_storage_secret_key=object_storage_secret_key,
        require_object_versioning=_bool(
            "SCENARA_DATA_REQUIRE_OBJECT_VERSIONING", deployment_profile == "production"
        ),
        dataset_bucket=os.getenv("SCENARA_DATA_DATASET_BUCKET", DEFAULT_DATASET_BUCKET),
        import_bucket=os.getenv("SCENARA_DATA_IMPORT_BUCKET", "scenara-data-imports"),
        export_bucket=os.getenv("SCENARA_DATA_EXPORT_BUCKET", "scenara-data-exports"),
        manifest_bucket=os.getenv("SCENARA_DATA_MANIFEST_BUCKET", "scenara-data-manifests"),
        backup_bucket=os.getenv("SCENARA_DATA_BACKUP_BUCKET", "scenara-data-backups"),
        artifact_bucket=os.getenv("SCENARA_DATA_ARTIFACT_BUCKET", "scenara-artifacts"),
        trusted_service_token=token,
        trusted_service_tokens=trusted_tokens,
        request_context_signing_key=context_signing_key,
        require_signed_request_context=require_signed_context,
        request_context_max_age_seconds=_positive_int(
            "SCENARA_DATA_REQUEST_CONTEXT_MAX_AGE_SECONDS", 300
        ),
        access_grant_max_ttl_seconds=_positive_int("SCENARA_DATA_ACCESS_GRANT_MAX_TTL_SECONDS", 86400),
        outbox_batch_size=_positive_int("SCENARA_DATA_OUTBOX_BATCH_SIZE", 100),
        outbox_max_attempts=_positive_int("SCENARA_DATA_OUTBOX_MAX_ATTEMPTS", 8),
        core_event_endpoint=event_endpoint,
        core_event_token=event_token,
        core_event_timeout_seconds=float(_positive_int("SCENARA_DATA_CORE_EVENT_TIMEOUT_SECONDS", 5)),
        allowed_source_systems=source_systems,
        console_username=console_username,
        console_password=console_password,
        console_session_secret=console_session_secret,
        console_session_ttl_seconds=_positive_int(
            "SCENARA_DATA_CONSOLE_SESSION_TTL_SECONDS", DEFAULT_CONSOLE_SESSION_TTL_SECONDS
        ),
        console_login_enabled=console_login_enabled,
        console_login_max_attempts=_positive_int("SCENARA_DATA_CONSOLE_LOGIN_MAX_ATTEMPTS", 5),
        console_login_window_seconds=_positive_int("SCENARA_DATA_CONSOLE_LOGIN_WINDOW_SECONDS", 300),
        console_tenant_id=os.getenv("SCENARA_DATA_CONSOLE_TENANT_ID", "default").strip() or "default",
        console_project_id=os.getenv("SCENARA_DATA_CONSOLE_PROJECT_ID", "default").strip() or "default",
        console_scopes=console_scopes,
        console_entitlements=_csv("SCENARA_DATA_CONSOLE_ENTITLEMENTS", ("scenara.data",)),
        cors_allow_origins=cors_origins,
        serve_frontend=_bool("SCENARA_DATA_SERVE_FRONTEND", False),
        frontend_dist=Path(os.getenv("SCENARA_DATA_FRONTEND_DIST", "/app/frontend-dist")),
    )
