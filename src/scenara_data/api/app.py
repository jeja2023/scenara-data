"""FastAPI 应用装配：中间件、统一错误信封与路由注册。

公共路径由 Core API Gateway 提供并代理到这里的 `/internal/v1`；代理不得改变契约语义、
租户/项目边界、请求与追踪上下文或错误码（规范 33、67）。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from scenara_data import __version__, contracts
from scenara_data.api.container import ApplicationContainer, build_container
from scenara_data.api.routers import ROUTERS
from scenara_data.api.security import RequestContextResolver
from scenara_data.application.errors import ApplicationError
from scenara_data.config import Settings, load_settings
from scenara_data.observability.logging import configure_logging, log_event, utc_rfc3339

LOGGER = logging.getLogger("scenara_data.api")

HTTP_STATUS_ERROR_CODES = {
    404: "RESOURCE_NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    413: "PAYLOAD_TOO_LARGE",
    429: "RATE_LIMITED",
}

VALIDATION_ERROR_MESSAGES = {
    "missing": "缺少必填字段",
    "extra_forbidden": "包含不允许的额外字段",
    "string_too_short": "字符串长度不足",
    "string_too_long": "字符串长度超出限制",
    "too_short": "条目数量不足",
    "too_long": "条目数量超出限制",
    "greater_than": "数值必须大于限定值",
    "greater_than_equal": "数值不能小于限定值",
    "less_than": "数值必须小于限定值",
    "less_than_equal": "数值不能大于限定值",
    "literal_error": "输入值不在允许范围内",
    "enum": "输入值不是有效的枚举成员",
    "bool_parsing": "输入值无法解析为布尔值",
    "int_parsing": "输入值无法解析为整数",
    "float_parsing": "输入值无法解析为数字",
    "datetime_parsing": "日期时间格式无效",
    "json_invalid": "JSON 内容无效",
    "list_type": "输入值必须是列表",
    "tuple_type": "输入值必须是元组",
    "dict_type": "输入值必须是对象",
}

DESCRIPTION = (
    "景枢数据平台内部 API：数据集、数据集版本、样本、标注、数据质量、"
    "数据血缘、难例与数据集构建。"
)


def create_app(
    settings: Settings | None = None,
    container: ApplicationContainer | None = None,
) -> FastAPI:
    resolved_settings = settings or load_settings()
    configure_logging()
    resolved_container = container or build_container(resolved_settings)

    application = FastAPI(
        title="景枢数据",
        version=__version__,
        description=DESCRIPTION,
        openapi_tags=[
            {"name": "运维", "description": "存活、就绪与指标探针"},
            {"name": "数据集", "description": "数据集目录"},
            {"name": "数据集版本", "description": "不可变数据集版本与对外引用"},
            {"name": "样本", "description": "样本"},
            {"name": "标注", "description": "标注、修订、任务与复核"},
            {"name": "数据质量", "description": "数据质量规则、运行与报告"},
            {"name": "数据血缘", "description": "数据血缘"},
            {"name": "难例", "description": "难例承接"},
        ],
    )
    application.state.container = resolved_container
    application.state.settings = resolved_settings
    application.state.context_resolver = RequestContextResolver(resolved_settings)
    application.state.contract_version = contracts.CONTRACT_VERSION

    if resolved_settings.cors_allow_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(resolved_settings.cors_allow_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @application.middleware("http")
    async def observe_request(request: Request, call_next: Any) -> Response:
        started = time.perf_counter()
        request_id = _header(request, "x-request-id")
        trace_id = _header(request, "x-trace-id")
        try:
            response = await call_next(request)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
        route = _route_of(request)
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Contract-Version"] = contracts.CONTRACT_VERSION
        labels = {"method": request.method, "route": route, "status": str(response.status_code)}
        resolved_container.metrics.increment("scenara_data_http_requests_total", labels=labels)
        resolved_container.metrics.observe(
            "scenara_data_http_request_duration_ms",
            duration_ms,
            labels={"method": request.method, "route": route},
        )
        log_event(
            LOGGER,
            service=resolved_settings.service_name,
            module="api",
            message="请求处理完成",
            request_id=request_id,
            trace_id=trace_id,
            method=request.method,
            path=route,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response

    @application.exception_handler(ApplicationError)
    async def application_error(request: Request, exc: ApplicationError) -> JSONResponse:
        return _error_response(
            request,
            resolved_container,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )

    @application.exception_handler(RequestValidationError)
    async def request_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = {
            "violations": [
                {
                    "location": ".".join(str(part) for part in item["loc"]),
                    "message": _localized_validation_message(item),
                }
                for item in exc.errors()
            ]
        }
        return _error_response(
            request,
            resolved_container,
            status_code=422,
            code="VALIDATION_FAILED",
            message="请求参数不符合契约",
            details=details,
        )

    @application.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = HTTP_STATUS_ERROR_CODES.get(exc.status_code, "INTERNAL_ERROR")
        return _error_response(
            request,
            resolved_container,
            status_code=exc.status_code,
            code=code,
            message="请求无法处理",
            details={},
        )

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # 未知错误统一映射为已登记的服务端错误码，不泄漏数据库异常、路径或堆栈。
        log_event(
            LOGGER,
            level=logging.ERROR,
            service=resolved_settings.service_name,
            module="api",
            message="请求处理失败",
            request_id=_header(request, "x-request-id"),
            trace_id=_header(request, "x-trace-id"),
            path=_route_of(request),
            error_type=type(exc).__name__,
        )
        return _error_response(
            request,
            resolved_container,
            status_code=500,
            code="INTERNAL_ERROR",
            message="服务内部错误",
            details={},
        )

    for router in ROUTERS:
        application.include_router(router)

    return application


def _header(request: Request, name: str) -> str:
    value = request.headers.get(name)
    return value.strip()[:512] if value and value.strip() else "unassigned"


def _route_of(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return str(path) if path else request.url.path


def _localized_validation_message(item: dict[str, Any]) -> str:
    error_type = str(item.get("type", ""))
    message = str(item.get("msg", ""))
    if error_type in {"value_error", "assertion_error"}:
        for prefix in ("Value error, ", "Assertion failed, "):
            if message.startswith(prefix):
                message = message.removeprefix(prefix)
                break
        if any("\u4e00" <= character <= "\u9fff" for character in message):
            return message
    return VALIDATION_ERROR_MESSAGES.get(error_type, "输入值不符合字段约束")


def _error_response(
    request: Request,
    container: ApplicationContainer,
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any],
) -> JSONResponse:
    if code not in contracts.ERROR_CODES and code not in HTTP_STATUS_ERROR_CODES.values():
        raise ValueError(f"未登记的错误码：{code}")
    container.metrics.increment(
        "scenara_data_http_errors_total", labels={"code": code, "status": str(status_code)}
    )
    payload = {
        "schema_version": contracts.ERROR_ENVELOPE_VERSION,
        "request_id": _header(request, "x-request-id"),
        "error": {"code": code, "message": message, "details": details},
        "occurred_at": utc_rfc3339(),
    }
    return JSONResponse(status_code=status_code, content=jsonable_encoder(payload))


app = create_app()
