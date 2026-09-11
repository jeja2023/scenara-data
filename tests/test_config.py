from __future__ import annotations

import pytest

from scenara_data.config import load_settings


def test_production_profile_requires_transport_security_and_signed_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {
        "SCENARA_DATA_DEPLOYMENT_PROFILE": "production",
        "SCENARA_DATA_RUNTIME_MODE": "postgres",
        "SCENARA_DATA_DATABASE_URL": "postgresql://data:password@db.example/scenara?sslmode=verify-full",
        "SCENARA_DATA_REDIS_URL": "rediss://redis.example:6380/1",
        "SCENARA_DATA_S3_ENDPOINT_URL": "https://s3.example",
        "SCENARA_DATA_TRUSTED_SERVICE_TOKEN": "a" * 32,
        "SCENARA_DATA_REQUEST_CONTEXT_SIGNING_KEY": "b" * 32,
        "SCENARA_DATA_CORE_EVENT_ENDPOINT": "https://core.example/internal/v1/data/events",
        "SCENARA_DATA_CORE_EVENT_TOKEN": "c" * 32,
        "SCENARA_DATA_CORS_ALLOW_ORIGINS": "https://console.example",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    settings = load_settings()

    assert settings.is_production_deployment
    assert settings.require_signed_request_context
    assert settings.require_object_versioning
    assert not settings.console_login_enabled


def test_production_profile_rejects_plaintext_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "SCENARA_DATA_DEPLOYMENT_PROFILE": "production",
        "SCENARA_DATA_RUNTIME_MODE": "postgres",
        "SCENARA_DATA_DATABASE_URL": "postgresql://data:password@db.example/scenara?sslmode=require",
        "SCENARA_DATA_REDIS_URL": "redis://redis.example:6379/1",
        "SCENARA_DATA_S3_ENDPOINT_URL": "https://s3.example",
        "SCENARA_DATA_TRUSTED_SERVICE_TOKEN": "a" * 32,
        "SCENARA_DATA_REQUEST_CONTEXT_SIGNING_KEY": "b" * 32,
        "SCENARA_DATA_CORE_EVENT_ENDPOINT": "https://core.example/internal/v1/data/events",
        "SCENARA_DATA_CORE_EVENT_TOKEN": "c" * 32,
        "SCENARA_DATA_CORS_ALLOW_ORIGINS": "https://console.example",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    with pytest.raises(RuntimeError, match="rediss"):
        load_settings()


def test_standalone_profile_does_not_require_core_event_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "SCENARA_DATA_DEPLOYMENT_PROFILE": "standalone",
        "SCENARA_DATA_RUNTIME_MODE": "postgres",
        "SCENARA_DATA_DATABASE_URL": "postgresql://data:password@db.example/scenara?sslmode=verify-full",
        "SCENARA_DATA_REDIS_URL": "rediss://redis.example:6380/1",
        "SCENARA_DATA_S3_ENDPOINT_URL": "https://s3.example",
        "SCENARA_DATA_TRUSTED_SERVICE_TOKEN": "a" * 32,
        "SCENARA_DATA_REQUEST_CONTEXT_SIGNING_KEY": "b" * 32,
        "SCENARA_DATA_CONSOLE_PASSWORD": "c" * 32,
        "SCENARA_DATA_CONSOLE_SESSION_SECRET": "d" * 32,
        "SCENARA_DATA_SERVE_FRONTEND": "true",
        "SCENARA_DATA_FRONTEND_DIST": "/tmp/scenara-data-frontend",
        "SCENARA_DATA_CORS_ALLOW_ORIGINS": "https://data.example",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("SCENARA_DATA_CORE_EVENT_ENDPOINT", raising=False)
    monkeypatch.delenv("SCENARA_DATA_CORE_EVENT_TOKEN", raising=False)

    settings = load_settings()

    assert settings.deployment_profile == "standalone"
    assert settings.console_login_enabled
    assert settings.serve_frontend
    assert settings.core_event_endpoint is None


def test_production_console_requires_independent_session_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "SCENARA_DATA_DEPLOYMENT_PROFILE": "production",
        "SCENARA_DATA_RUNTIME_MODE": "postgres",
        "SCENARA_DATA_DATABASE_URL": "postgresql://data:password@db.example/scenara?sslmode=verify-full",
        "SCENARA_DATA_REDIS_URL": "rediss://redis.example:6380/1",
        "SCENARA_DATA_S3_ENDPOINT_URL": "https://s3.example",
        "SCENARA_DATA_TRUSTED_SERVICE_TOKEN": "a" * 32,
        "SCENARA_DATA_REQUEST_CONTEXT_SIGNING_KEY": "b" * 32,
        "SCENARA_DATA_CORE_EVENT_ENDPOINT": "https://core.example/internal/v1/data/events",
        "SCENARA_DATA_CORE_EVENT_TOKEN": "c" * 32,
        "SCENARA_DATA_CORS_ALLOW_ORIGINS": "https://console.example",
        "SCENARA_DATA_CONSOLE_LOGIN_ENABLED": "true",
        "SCENARA_DATA_CONSOLE_PASSWORD": "d" * 32,
        "SCENARA_DATA_CONSOLE_SESSION_SECRET": "a" * 32,
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    with pytest.raises(RuntimeError, match="会话签名密钥"):
        load_settings()
