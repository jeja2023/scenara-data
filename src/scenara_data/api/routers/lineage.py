"""Data Lineage 内部 API。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from scenara_data.api.deps import ContainerDep, ContextDep
from scenara_data.api.routers.datasets import ERROR_RESPONSES
from scenara_data.api.schemas import LineagePage
from scenara_data.domain.models import LineageSnapshot

router = APIRouter(prefix="/internal/v1", tags=["lineage"])


@router.get(
    "/lineage/{entity_id}",
    response_model=LineagePage,
    responses=ERROR_RESPONSES,
    summary="查询实体血缘边",
)
def get_lineage(entity_id: str, container: ContainerDep, context: ContextDep) -> dict[str, Any]:
    items = container.lineage.list_lineage(entity_id, context)
    return {"items": items, "total": len(items), "next_cursor": None}


@router.get(
    "/lineage-snapshots/{snapshot_id}",
    response_model=LineageSnapshot,
    responses=ERROR_RESPONSES,
    summary="读取血缘快照",
)
def get_lineage_snapshot(
    snapshot_id: str, container: ContainerDep, context: ContextDep
) -> LineageSnapshot:
    return container.lineage.get_snapshot(snapshot_id, context)
