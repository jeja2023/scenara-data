"""Sample 内部 API（指南 6.3）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse

from scenara_data.api.deps import (
    ContainerDep,
    ContextDep,
    CursorQuery,
    LimitQuery,
    idempotent,
    offset_of,
    paged,
)
from scenara_data.api.routers.datasets import ERROR_RESPONSES
from scenara_data.api.schemas import CreateSampleRequest, DatasetSplit, SamplePage
from scenara_data.domain.models import Sample

router = APIRouter(prefix="/internal/v1/samples", tags=["samples"])


@router.post(
    "",
    response_model=Sample,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
    summary="创建样本",
)
def create_sample(
    body: CreateSampleRequest, container: ContainerDep, context: ContextDep
) -> JSONResponse:
    return idempotent(
        container,
        context=context,
        operation="sample.create",
        request_value=body.model_dump(mode="json"),
        status_code=status.HTTP_201_CREATED,
        callback=lambda: container.samples.create_sample(
            source_ref=body.source_ref,
            media_type=body.media_type,
            source_lineage=body.source_lineage,
            sample_metadata=body.sample_metadata,
            sample_id=body.sample_id,
            source_system=body.source_system,
            source_resource_type=body.source_resource_type,
            source_resource_id=body.source_resource_id,
            person_id=body.person_id,
            camera_id=body.camera_id,
            bbox=body.bbox,
            dataset_split=body.dataset_split,
            captured_at=body.captured_at,
            context=context,
        ),
    )


@router.get("", response_model=SamplePage, responses=ERROR_RESPONSES, summary="分页列出样本")
def list_samples(
    container: ContainerDep,
    context: ContextDep,
    limit: LimitQuery = 50,
    cursor: CursorQuery = None,
    dataset_split: DatasetSplit | None = Query(default=None),
) -> dict[str, Any]:
    offset = offset_of(cursor)
    items, total = container.samples.list_samples(
        context, limit=limit, offset=offset, dataset_split=dataset_split
    )
    return paged(items, total, offset=offset, limit=limit)


@router.get(
    "/{sample_id}", response_model=Sample, responses=ERROR_RESPONSES, summary="读取样本"
)
def get_sample(sample_id: str, container: ContainerDep, context: ContextDep) -> Sample:
    return container.samples.get_sample(sample_id, context)
