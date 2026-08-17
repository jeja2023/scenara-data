"""数据集内部 API（指南 11.1）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, status
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
from scenara_data.api.schemas import (
    CreateDatasetRequest,
    CreateDatasetVersionRequest,
    DatasetPage,
    DatasetVersionPage,
    ErrorEnvelope,
    PatchDatasetRequest,
)
from scenara_data.domain.models import Dataset, DatasetVersion

router = APIRouter(prefix="/internal/v1", tags=["数据集"])

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    409: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
}


@router.post(
    "/datasets",
    response_model=Dataset,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
    summary="创建数据集目录",
)
def create_dataset(
    body: CreateDatasetRequest, container: ContainerDep, context: ContextDep
) -> JSONResponse:
    return idempotent(
        container,
        context=context,
        operation="dataset.create",
        request_value=body.model_dump(mode="json"),
        status_code=status.HTTP_201_CREATED,
        callback=lambda: container.datasets.create_dataset(
            name=body.name,
            description=body.description,
            dataset_id=body.dataset_id,
            labels=body.labels,
            dataset_metadata=body.metadata,
            context=context,
        ),
    )


@router.get("/datasets", response_model=DatasetPage, responses=ERROR_RESPONSES, summary="分页列出数据集")
def list_datasets(
    container: ContainerDep,
    context: ContextDep,
    limit: LimitQuery = 50,
    cursor: CursorQuery = None,
) -> dict[str, Any]:
    offset = offset_of(cursor)
    items, total = container.datasets.list_datasets(context, limit=limit, offset=offset)
    return paged(items, total, offset=offset, limit=limit)


@router.get(
    "/datasets/{dataset_id}", response_model=Dataset, responses=ERROR_RESPONSES, summary="读取数据集"
)
def get_dataset(dataset_id: str, container: ContainerDep, context: ContextDep) -> Dataset:
    return container.datasets.get_dataset(dataset_id, context)


@router.patch(
    "/datasets/{dataset_id}", response_model=Dataset, responses=ERROR_RESPONSES, summary="更新数据集或推进状态"
)
def update_dataset(
    dataset_id: str, body: PatchDatasetRequest, container: ContainerDep, context: ContextDep
) -> JSONResponse:
    return idempotent(
        container,
        context=context,
        operation=f"dataset.update:{dataset_id}",
        request_value=body.model_dump(mode="json"),
        status_code=status.HTTP_200_OK,
        callback=lambda: container.datasets.update_dataset(
            dataset_id,
            context,
            name=body.name,
            description=body.description,
            labels=body.labels,
            dataset_metadata=body.metadata,
            target_status=body.status,
        ),
    )


@router.delete(
    "/datasets/{dataset_id}", response_model=Dataset, responses=ERROR_RESPONSES, summary="归档数据集"
)
def archive_dataset(dataset_id: str, container: ContainerDep, context: ContextDep) -> JSONResponse:
    return idempotent(
        container,
        context=context,
        operation=f"dataset.archive:{dataset_id}",
        request_value={"dataset_id": dataset_id},
        status_code=status.HTTP_200_OK,
        callback=lambda: container.datasets.archive_dataset(dataset_id, context),
    )


@router.post(
    "/datasets/{dataset_id}/versions",
    response_model=DatasetVersion,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
    summary="创建数据集版本",
)
def create_dataset_version(
    dataset_id: str,
    body: CreateDatasetVersionRequest,
    container: ContainerDep,
    context: ContextDep,
) -> JSONResponse:
    return idempotent(
        container,
        context=context,
        operation=f"dataset.version.create:{dataset_id}",
        request_value=body.model_dump(mode="json"),
        status_code=status.HTTP_201_CREATED,
        callback=lambda: container.datasets.create_dataset_version(
            dataset_id=dataset_id,
            version=body.version,
            dataset_version_id=body.dataset_version_id,
            context=context,
        ),
    )


@router.get(
    "/datasets/{dataset_id}/versions",
    response_model=DatasetVersionPage,
    responses=ERROR_RESPONSES,
    summary="分页列出数据集版本",
)
def list_dataset_versions(
    dataset_id: str,
    container: ContainerDep,
    context: ContextDep,
    limit: LimitQuery = 50,
    cursor: CursorQuery = None,
) -> dict[str, Any]:
    offset = offset_of(cursor)
    items, total = container.datasets.list_dataset_versions(
        dataset_id, context, limit=limit, offset=offset
    )
    return paged(items, total, offset=offset, limit=limit)
