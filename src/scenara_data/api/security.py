"""身份上下文解析（规范 39、67；指南 10）。

Data 不签发身份，只验证 Core 信任的服务间凭据并解析透传上下文，然后对领域资源独立授权。
"""

from __future__ import annotations

import secrets

from fastapi import Request

from scenara_data.application.errors import AuthenticationError, InputValidationError
from scenara_data.config import Settings
from scenara_data.observability.tracing import extract_trace_id
from scenara_data.ports.interfaces import RequestContext

MAX_HEADER_LENGTH = 512
MAX_SCOPES = 64

TENANT_HEADER = "x-scenara-tenant-id"
PROJECT_HEADER = "x-scenara-project-id"
PRINCIPAL_HEADER = "x-scenara-principal-id"
PRINCIPAL_TYPE_HEADER = "x-scenara-principal-type"
SCOPES_HEADER = "x-scenara-permission-scopes"
ENTITLEMENTS_HEADER = "x-scenara-product-entitlements"
REQUEST_ID_HEADER = "x-request-id"
TRACE_ID_HEADER = "x-trace-id"

PRINCIPAL_TYPES = frozenset({"user", "service_account"})


class RequestContextResolver:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def __call__(self, request: Request) -> RequestContext:
        self._authenticate(request)
        tenant_id = self._required(request, TENANT_HEADER)
        project_id = self._required(request, PROJECT_HEADER)
        principal_id = self._required(request, PRINCIPAL_HEADER)
        principal_type = self._required(request, PRINCIPAL_TYPE_HEADER)
        if principal_type not in PRINCIPAL_TYPES:
            raise InputValidationError(
                "主体类型未登记", details={"principal_type": principal_type}
            )
        return RequestContext(
            tenant_id=tenant_id,
            project_id=project_id,
            principal_id=principal_id,
            permission_scopes=self._scopes(request),
            request_id=self._required(request, REQUEST_ID_HEADER),
            trace_id=self._trace_id(request),
            principal_type=principal_type,
            product_entitlements=self._entitlements(request),
            idempotency_key=self._idempotency_key(request),
        )

    def _authenticate(self, request: Request) -> None:
        scheme, _, credential = request.headers.get("authorization", "").partition(" ")
        expected = self._settings.trusted_service_token
        if (
            scheme.lower() != "bearer"
            or not credential
            or not expected
            or not secrets.compare_digest(credential, expected)
        ):
            raise AuthenticationError()

    def _scopes(self, request: Request) -> tuple[str, ...]:
        raw = self._required(request, SCOPES_HEADER, max_length=2048)
        scopes = tuple(sorted({item.strip() for item in raw.replace(" ", ",").split(",") if item.strip()}))
        if not scopes:
            raise InputValidationError("权限范围不能为空")
        if len(scopes) > MAX_SCOPES:
            raise InputValidationError("权限范围数量超出上限")
        return scopes

    def _entitlements(self, request: Request) -> tuple[str, ...]:
        raw = self._required(request, ENTITLEMENTS_HEADER, max_length=1024)
        return tuple(sorted({item.strip() for item in raw.split(",") if item.strip()}))

    def _trace_id(self, request: Request) -> str:
        explicit = request.headers.get(TRACE_ID_HEADER)
        if explicit and explicit.strip():
            return explicit.strip()[:MAX_HEADER_LENGTH]
        extracted = extract_trace_id(request.headers.get("traceparent"))
        if extracted is None:
            raise InputValidationError("缺少 X-Trace-Id 或合法 traceparent")
        return extracted

    @staticmethod
    def _idempotency_key(request: Request) -> str | None:
        value = request.headers.get("idempotency-key")
        if value is None or not value.strip():
            return None
        key = value.strip()
        if len(key) > 200:
            raise InputValidationError("Idempotency-Key 过长")
        return key

    @staticmethod
    def _required(request: Request, name: str, *, max_length: int = MAX_HEADER_LENGTH) -> str:
        value = request.headers.get(name)
        if value is None or not value.strip():
            raise InputValidationError(f"缺少请求头 {name}")
        if len(value) > max_length:
            raise InputValidationError(f"请求头 {name} 过长")
        return value.strip()
