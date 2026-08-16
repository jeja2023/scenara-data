from __future__ import annotations

from typing import Any


class ApplicationError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class AuthenticationError(ApplicationError):
    def __init__(self, message: str = "身份凭据无效") -> None:
        super().__init__("UNAUTHENTICATED", message, status_code=401)


class AuthorizationError(ApplicationError):
    def __init__(self, permission: str) -> None:
        super().__init__(
            "FORBIDDEN",
            "当前身份没有执行该操作的权限",
            status_code=403,
            details={"required_permission": permission},
        )


class ResourceNotFoundError(ApplicationError):
    def __init__(self, entity: str, entity_id: str) -> None:
        super().__init__(
            "RESOURCE_NOT_FOUND",
            "请求的资源不存在",
            status_code=404,
            details={"entity": entity, "entity_id": entity_id},
        )


class ConflictError(ApplicationError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__("RESOURCE_CONFLICT", message, status_code=409, details=details)


class ImmutableResourceError(ApplicationError):
    def __init__(self, entity_id: str) -> None:
        super().__init__(
            "IMMUTABLE_RESOURCE",
            "已发布资源不可修改，请创建新版本",
            status_code=409,
            details={"entity_id": entity_id},
        )


class IdempotencyConflictError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            "IDEMPOTENCY_CONFLICT",
            "同一幂等键已用于不同的请求",
            status_code=409,
        )


class InvalidStateError(ApplicationError):
    def __init__(self, message: str) -> None:
        super().__init__("INVALID_STATE_TRANSITION", message, status_code=409)


class InputValidationError(ApplicationError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__("VALIDATION_FAILED", message, status_code=422, details=details)


class DependencyUnavailableError(ApplicationError):
    def __init__(self, dependency: str) -> None:
        super().__init__(
            "DEPENDENCY_UNAVAILABLE",
            "依赖服务暂时不可用",
            status_code=503,
            details={"dependency": dependency},
        )
