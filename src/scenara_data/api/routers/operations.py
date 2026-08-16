"""运维探针路由（指南 11.3）。

`/livez` 只反映进程存活；`/readyz` 真实检查 PostgreSQL 与必需对象存储依赖；`/metrics`
以 Prometheus 文本格式输出 Provider 中立指标。`/health` 保留为 `/livez` 的兼容别名。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response, status
from fastapi.responses import PlainTextResponse

from scenara_data import __version__
from scenara_data.api.deps import ContainerDep
from scenara_data.observability.logging import utc_rfc3339

router = APIRouter(tags=["operations"])


def _liveness(container: ContainerDep) -> dict[str, str]:
    return {
        "status": "ok",
        "service": container.settings.service_name,
        "version": __version__,
        "maturity": container.settings.maturity,
        "runtime_mode": container.settings.runtime_mode,
        "timestamp": utc_rfc3339(),
    }


@router.get("/livez", summary="进程存活探针")
def livez(container: ContainerDep) -> dict[str, str]:
    return _liveness(container)


@router.get("/health", summary="存活探针兼容别名")
def health(container: ContainerDep) -> dict[str, str]:
    return _liveness(container)


@router.get("/readyz", summary="依赖就绪探针")
def readyz(container: ContainerDep, response: Response) -> dict[str, Any]:
    checks = container.readiness()
    ready = bool(checks) and all(checks.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if ready else "not_ready",
        "service": container.settings.service_name,
        "runtime_mode": container.settings.runtime_mode,
        "checks": checks,
        "timestamp": utc_rfc3339(),
    }


@router.get("/ready", summary="就绪探针兼容别名")
def ready(container: ContainerDep, response: Response) -> dict[str, Any]:
    return readyz(container, response)


@router.get("/metrics", response_class=PlainTextResponse, summary="Prometheus 指标")
def metrics(container: ContainerDep) -> PlainTextResponse:
    return PlainTextResponse(
        container.metrics.render(), media_type="text/plain; version=0.0.4; charset=utf-8"
    )
