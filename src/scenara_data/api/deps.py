"""API 依赖：请求上下文、分页参数与幂等响应包装。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from scenara_data.api.container import ApplicationContainer
from scenara_data.api.pagination import decode_cursor, encode_cursor
from scenara_data.application.idempotency import request_digest
from scenara_data.ports.interfaces import RequestContext


def get_container(request: Request) -> ApplicationContainer:
    container = getattr(request.app.state, "container", None)
    if container is None:  # pragma: no cover - 应用装配失败属于启动期错误
        raise RuntimeError("application container is not configured")
    return container


def get_context(request: Request) -> RequestContext:
    resolver = request.app.state.context_resolver
    return resolver(request)


ContainerDep = Annotated[ApplicationContainer, Depends(get_container)]
ContextDep = Annotated[RequestContext, Depends(get_context)]
LimitQuery = Annotated[int, Query(ge=1, le=100)]
CursorQuery = Annotated[str | None, Query(max_length=256)]


def paged(items: list[Any], total: int, *, offset: int, limit: int) -> dict[str, Any]:
    return {"items": items, "total": total, "next_cursor": encode_cursor(offset, limit, total)}


def offset_of(cursor: str | None) -> int:
    return decode_cursor(cursor)


def idempotent(
    container: ApplicationContainer,
    *,
    context: RequestContext,
    operation: str,
    request_value: Any,
    status_code: int,
    callback: Callable[[], Any],
) -> JSONResponse:
    """写操作统一走 Idempotency-Key 重放保护（规范 33）。"""

    def execute() -> dict[str, Any]:
        value = callback()
        return jsonable_encoder(value.model_dump(mode="json") if hasattr(value, "model_dump") else value)

    resolved_status, payload, replayed = container.idempotency.execute(
        context=context,
        operation=operation,
        request_hash=request_digest(request_value),
        status_code=status_code,
        callback=execute,
    )
    return JSONResponse(
        status_code=resolved_status,
        content=payload,
        headers={"X-Idempotent-Replay": "true" if replayed else "false"},
    )
