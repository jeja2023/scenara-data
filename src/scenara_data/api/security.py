"""身份上下文解析（规范 39、67；指南 10）。

Data 不持有正式 IAM 身份事实；生产路径验证 Core 信任的服务间凭据并解析透传上下文，
本地工作台会话仅服务独立前端直连场景。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from dataclasses import dataclass
from uuid import uuid4

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
CONTEXT_TIMESTAMP_HEADER = "x-scenara-context-timestamp"
CONTEXT_SIGNATURE_HEADER = "x-scenara-context-signature"

PRINCIPAL_TYPES = frozenset({"user", "service_account"})
CONSOLE_TOKEN_PREFIX = "scenara-data-console"


@dataclass(frozen=True, slots=True)
class ConsoleSession:
    token: str
    session_id: str
    username: str
    tenant_id: str
    project_id: str
    principal_type: str
    permission_scopes: tuple[str, ...]
    product_entitlements: tuple[str, ...]
    issued_at: int
    expires_at: int


def verify_console_login(settings: Settings, username: str, password: str) -> None:
    expected_username = settings.console_username
    expected_password = settings.console_password
    if (
        not username
        or not password
        or not expected_username
        or not expected_password
        or not secrets.compare_digest(username, expected_username)
        or not secrets.compare_digest(password, expected_password)
    ):
        raise AuthenticationError("用户名或密码错误")


def issue_console_session(settings: Settings, username: str, *, now: int | None = None) -> ConsoleSession:
    issued_at = int(time.time()) if now is None else now
    expires_at = issued_at + settings.console_session_ttl_seconds
    payload = {
        "version": 1,
        "session_id": f"dcs_{uuid4().hex}",
        "username": username,
        "tenant_id": settings.console_tenant_id,
        "project_id": settings.console_project_id,
        "principal_type": "user",
        "permission_scopes": list(settings.console_scopes),
        "product_entitlements": list(settings.console_entitlements),
        "issued_at": issued_at,
        "expires_at": expires_at,
    }
    encoded = _b64encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    signature = _sign_console_payload(settings, encoded)
    return _session_from_payload(f"{CONSOLE_TOKEN_PREFIX}.{encoded}.{signature}", payload)


def authenticate_console_session(settings: Settings, token: str) -> ConsoleSession:
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != CONSOLE_TOKEN_PREFIX:
        raise AuthenticationError()
    encoded_payload, signature = parts[1], parts[2]
    expected_signature = _sign_console_payload(settings, encoded_payload)
    if not secrets.compare_digest(signature, expected_signature):
        raise AuthenticationError()
    try:
        payload = json.loads(_b64decode(encoded_payload).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise AuthenticationError() from exc
    session = _session_from_payload(token, payload)
    if session.expires_at <= int(time.time()):
        raise AuthenticationError("登录会话已过期")
    return session


class RequestContextResolver:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def __call__(self, request: Request) -> RequestContext:
        console_session = self._console_session(request)
        if console_session is not None:
            return RequestContext(
                tenant_id=console_session.tenant_id,
                project_id=console_session.project_id,
                principal_id=console_session.username,
                permission_scopes=console_session.permission_scopes,
                request_id=self._required(request, REQUEST_ID_HEADER),
                trace_id=self._trace_id(request),
                principal_type=console_session.principal_type,
                product_entitlements=console_session.product_entitlements,
                idempotency_key=self._idempotency_key(request),
            )
        self._authenticate_service(request)
        tenant_id = self._required(request, TENANT_HEADER)
        project_id = self._required(request, PROJECT_HEADER)
        principal_id = self._required(request, PRINCIPAL_HEADER)
        principal_type = self._required(request, PRINCIPAL_TYPE_HEADER)
        if principal_type not in PRINCIPAL_TYPES:
            raise InputValidationError(
                "主体类型未登记", details={"principal_type": principal_type}
            )
        scopes = self._scopes(request)
        entitlements = self._entitlements(request)
        request_id = self._required(request, REQUEST_ID_HEADER)
        trace_id = self._trace_id(request)
        self._verify_context_signature(
            request,
            tenant_id=tenant_id,
            project_id=project_id,
            principal_id=principal_id,
            principal_type=principal_type,
            scopes=scopes,
            entitlements=entitlements,
            request_id=request_id,
            trace_id=trace_id,
        )
        return RequestContext(
            tenant_id=tenant_id,
            project_id=project_id,
            principal_id=principal_id,
            permission_scopes=scopes,
            request_id=request_id,
            trace_id=trace_id,
            principal_type=principal_type,
            product_entitlements=entitlements,
            idempotency_key=self._idempotency_key(request),
        )

    def _console_session(self, request: Request) -> ConsoleSession | None:
        scheme, _, credential = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not credential:
            raise AuthenticationError()
        if self._matches_service_token(credential):
            return None
        return authenticate_console_session(self._settings, credential)

    def _authenticate_service(self, request: Request) -> None:
        scheme, _, credential = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not credential or not self._matches_service_token(credential):
            raise AuthenticationError()

    def _matches_service_token(self, credential: str) -> bool:
        return any(secrets.compare_digest(credential, expected) for expected in self._settings.trusted_service_tokens)

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
            value = explicit.strip()
            if not re.fullmatch(r"[0-9a-f]{32}", value):
                raise InputValidationError("X-Trace-Id 必须是 32 位小写十六进制")
            return value
        extracted = extract_trace_id(request.headers.get("traceparent"))
        if extracted is None:
            raise InputValidationError("缺少 X-Trace-Id 或合法 traceparent")
        return extracted

    def _verify_context_signature(
        self,
        request: Request,
        *,
        tenant_id: str,
        project_id: str,
        principal_id: str,
        principal_type: str,
        scopes: tuple[str, ...],
        entitlements: tuple[str, ...],
        request_id: str,
        trace_id: str,
    ) -> None:
        """验证 Core 对身份上下文的短时 HMAC 声明，避免 bearer 持有者伪造范围。"""
        if not self._settings.require_signed_request_context:
            return
        signing_key = self._settings.request_context_signing_key
        if not signing_key:
            raise AuthenticationError("服务端未配置请求上下文签名密钥")
        raw_timestamp = self._signature_header(request, CONTEXT_TIMESTAMP_HEADER, max_length=32)
        try:
            timestamp = int(raw_timestamp)
        except ValueError as exc:
            raise AuthenticationError("请求上下文签名时间无效") from exc
        if abs(int(time.time()) - timestamp) > self._settings.request_context_max_age_seconds:
            raise AuthenticationError("请求上下文签名已过期")
        signature = self._signature_header(request, CONTEXT_SIGNATURE_HEADER, max_length=128)
        expected = sign_request_context(
            signing_key,
            method=request.method,
            path=request.url.path,
            tenant_id=tenant_id,
            project_id=project_id,
            principal_id=principal_id,
            principal_type=principal_type,
            scopes=scopes,
            entitlements=entitlements,
            request_id=request_id,
            trace_id=trace_id,
            timestamp=timestamp,
        )
        if not secrets.compare_digest(signature, expected):
            raise AuthenticationError("请求上下文签名无效")

    @staticmethod
    def _signature_header(request: Request, name: str, *, max_length: int) -> str:
        value = request.headers.get(name)
        if value is None or not value.strip() or len(value) > max_length:
            raise AuthenticationError("缺少或无效的请求上下文签名")
        return value.strip()

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


def _sign_console_payload(settings: Settings, encoded_payload: str) -> str:
    secret = settings.console_session_secret or settings.trusted_service_token
    digest = hmac.new(secret.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(digest)


def sign_request_context(
    signing_key: str,
    *,
    method: str,
    path: str,
    tenant_id: str,
    project_id: str,
    principal_id: str,
    principal_type: str,
    scopes: tuple[str, ...],
    entitlements: tuple[str, ...],
    request_id: str,
    trace_id: str,
    timestamp: int,
) -> str:
    """生成 Core 与本地联调工具共用的身份上下文 HMAC-SHA256 签名。"""
    payload = {
        "entitlements": sorted(set(entitlements)),
        "method": method.upper(),
        "path": path,
        "principal_id": principal_id,
        "principal_type": principal_type,
        "project_id": project_id,
        "request_id": request_id,
        "scopes": sorted(set(scopes)),
        "tenant_id": tenant_id,
        "timestamp": timestamp,
        "trace_id": trace_id,
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(signing_key.encode("utf-8"), encoded, hashlib.sha256).hexdigest()


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _session_from_payload(token: str, payload: object) -> ConsoleSession:
    if not isinstance(payload, dict):
        raise AuthenticationError()
    try:
        version = payload["version"]
        session_id = payload["session_id"]
        username = payload["username"]
        tenant_id = payload["tenant_id"]
        project_id = payload["project_id"]
        principal_type = payload["principal_type"]
        scopes = payload["permission_scopes"]
        entitlements = payload["product_entitlements"]
        issued_at = payload["issued_at"]
        expires_at = payload["expires_at"]
    except KeyError as exc:
        raise AuthenticationError() from exc
    if version != 1 or principal_type not in PRINCIPAL_TYPES:
        raise AuthenticationError()
    if not all(isinstance(item, str) and item.strip() for item in (session_id, username, tenant_id, project_id)):
        raise AuthenticationError()
    if not isinstance(scopes, list) or not all(isinstance(item, str) and item.strip() for item in scopes):
        raise AuthenticationError()
    if not isinstance(entitlements, list) or not all(isinstance(item, str) and item.strip() for item in entitlements):
        raise AuthenticationError()
    if not isinstance(issued_at, int) or not isinstance(expires_at, int) or expires_at <= issued_at:
        raise AuthenticationError()
    return ConsoleSession(
        token=token,
        session_id=session_id,
        username=username,
        tenant_id=tenant_id,
        project_id=project_id,
        principal_type=principal_type,
        permission_scopes=tuple(sorted(set(scopes))),
        product_entitlements=tuple(sorted(set(entitlements))),
        issued_at=issued_at,
        expires_at=expires_at,
    )
