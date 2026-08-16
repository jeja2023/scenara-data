"""Dataset Version 内部 API：状态转换、发布、Manifest、引用与访问授权（指南 11.1、11.2）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from scenara_data.api.deps import ContainerDep, ContextDep, idempotent
from scenara_data.api.routers.datasets import ERROR_RESPONSES
from scenara_data.api.schemas import (
    AccessGrantResponse,
    AddSampleRequest,
    CreateAccessGrantRequest,
    DatasetVersionReference,
    PublicationResponse,
    SamplePage,
    TransitionDatasetVersionRequest,
    ValidateDatasetVersionRequest,
    ValidationResponse,
)
from scenara_data.application.errors import ApplicationError
from scenara_data.domain.models import DatasetVersion, DatasetVersionStatus, LineageSnapshot

router = APIRouter(prefix="/internal/v1/dataset-versions", tags=["dataset-versions"])


@router.get(
    "/{dataset_version_id}",
    response_model=DatasetVersion,
    responses=ERROR_RESPONSES,
    summary="读取数据集版本",
)
def get_dataset_version(
    dataset_version_id: str, container: ContainerDep, context: ContextDep
) -> DatasetVersion:
    return container.datasets.get_dataset_version(dataset_version_id, context)


@router.post(
    "/{dataset_version_id}/transition",
    responses=ERROR_RESPONSES,
    summary="按状态机推进数据集版本",
)
def transition_dataset_version(
    dataset_version_id: str,
    body: TransitionDatasetVersionRequest,
    container: ContainerDep,
    context: ContextDep,
) -> JSONResponse:
    def build() -> Any:
        return container.datasets.begin_build(dataset_version_id, context)

    def validate() -> dict[str, Any]:
        value, report = container.datasets.validate_dataset_version(
            dataset_version_id, context, rule_ids=body.rule_ids
        )
        return {"dataset_version": value, "quality_report": report}

    def publish() -> dict[str, Any]:
        value, manifest = container.datasets.publish_dataset_version(dataset_version_id, context)
        return {"dataset_version": value, "manifest": manifest}

    def archive() -> Any:
        return container.datasets.archive_dataset_version(dataset_version_id, context)

    def fail() -> Any:
        return container.datasets.fail_build(
            dataset_version_id, context, reason=body.reason or "构建失败"
        )

    callbacks = {
        DatasetVersionStatus.BUILDING: build,
        DatasetVersionStatus.READY: validate,
        DatasetVersionStatus.PUBLISHED: publish,
        DatasetVersionStatus.ARCHIVED: archive,
        DatasetVersionStatus.FAILED: fail,
    }
    callback = callbacks.get(body.status)
    if callback is None:
        raise ApplicationError(
            "INVALID_STATE_TRANSITION",
            "当前版本转换目标不支持",
            status_code=409,
            details={"target_status": body.status},
        )
    return idempotent(
        container,
        context=context,
        operation=f"dataset.version.transition:{dataset_version_id}",
        request_value=body.model_dump(mode="json"),
        status_code=status.HTTP_200_OK,
        callback=callback,
    )


@router.post(
    "/{dataset_version_id}/samples",
    response_model=DatasetVersion,
    responses=ERROR_RESPONSES,
    summary="向 building 版本加入样本",
)
def add_sample_to_version(
    dataset_version_id: str,
    body: AddSampleRequest,
    container: ContainerDep,
    context: ContextDep,
) -> JSONResponse:
    return idempotent(
        container,
        context=context,
        operation=f"dataset.version.sample.add:{dataset_version_id}",
        request_value=body.model_dump(mode="json"),
        status_code=status.HTTP_200_OK,
        callback=lambda: container.datasets.add_sample_to_version(
            dataset_version_id, body.sample_id, context
        ),
    )


@router.get(
    "/{dataset_version_id}/samples",
    response_model=SamplePage,
    responses=ERROR_RESPONSES,
    summary="列出版本内样本",
)
def list_version_samples(
    dataset_version_id: str, container: ContainerDep, context: ContextDep
) -> dict[str, Any]:
    items = container.datasets.list_version_samples(dataset_version_id, context)
    return {"items": items, "total": len(items), "next_cursor": None}


@router.post(
    "/{dataset_version_id}/validate",
    response_model=ValidationResponse,
    responses=ERROR_RESPONSES,
    summary="执行质量验证并推进到 ready",
)
def validate_dataset_version(
    dataset_version_id: str,
    body: ValidateDatasetVersionRequest,
    container: ContainerDep,
    context: ContextDep,
) -> JSONResponse:
    def validate() -> dict[str, Any]:
        value, report = container.datasets.validate_dataset_version(
            dataset_version_id, context, rule_ids=body.rule_ids
        )
        return {"dataset_version": value, "quality_report": report}

    return idempotent(
        container,
        context=context,
        operation=f"dataset.version.validate:{dataset_version_id}",
        request_value=body.model_dump(mode="json"),
        status_code=status.HTTP_200_OK,
        callback=validate,
    )


@router.post(
    "/{dataset_version_id}/publish",
    response_model=PublicationResponse,
    responses=ERROR_RESPONSES,
    summary="发布不可变数据集版本",
)
def publish_dataset_version(
    dataset_version_id: str, container: ContainerDep, context: ContextDep
) -> JSONResponse:
    def publish() -> dict[str, Any]:
        value, manifest = container.datasets.publish_dataset_version(dataset_version_id, context)
        return {"dataset_version": value, "manifest": manifest}

    return idempotent(
        container,
        context=context,
        operation=f"dataset.version.publish:{dataset_version_id}",
        request_value={"dataset_version_id": dataset_version_id},
        status_code=status.HTTP_200_OK,
        callback=publish,
    )


@router.get(
    "/{dataset_version_id}/reference",
    response_model=DatasetVersionReference,
    responses=ERROR_RESPONSES,
    summary="向模型平台输出 DatasetVersionReference",
)
def get_dataset_version_reference(
    dataset_version_id: str, container: ContainerDep, context: ContextDep
) -> dict[str, Any]:
    return container.datasets.dataset_version_reference(dataset_version_id, context)


@router.get(
    "/{dataset_version_id}/manifest",
    responses=ERROR_RESPONSES,
    summary="下载已校验摘要的不可变 Manifest",
)
def get_dataset_version_manifest(
    dataset_version_id: str, container: ContainerDep, context: ContextDep
) -> dict[str, Any]:
    return container.datasets.read_manifest(dataset_version_id, context)


@router.post(
    "/{dataset_version_id}/access-grants",
    response_model=AccessGrantResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
    summary="为服务账号签发短期数据集访问授权",
)
def create_access_grant(
    dataset_version_id: str,
    body: CreateAccessGrantRequest,
    container: ContainerDep,
    context: ContextDep,
) -> JSONResponse:
    def grant() -> dict[str, Any]:
        value, urls = container.datasets.create_access_grant(
            dataset_version_id,
            service_account_id=body.service_account_id,
            permissions=body.permissions,
            ttl_seconds=body.ttl_seconds,
            context=context,
        )
        return {"grant": value, **urls}

    return idempotent(
        container,
        context=context,
        operation=f"dataset.version.access_grant:{dataset_version_id}",
        request_value=body.model_dump(mode="json"),
        status_code=status.HTTP_201_CREATED,
        callback=grant,
    )


@router.get(
    "/{dataset_version_id}/access-grants",
    responses=ERROR_RESPONSES,
    summary="列出数据集版本访问授权",
)
def list_access_grants(
    dataset_version_id: str, container: ContainerDep, context: ContextDep
) -> dict[str, Any]:
    items = container.datasets.list_access_grants(dataset_version_id, context)
    return {"items": items, "total": len(items), "next_cursor": None}


@router.get(
    "/{dataset_version_id}/lineage-snapshot",
    response_model=LineageSnapshot,
    responses=ERROR_RESPONSES,
    summary="读取版本绑定的血缘快照",
)
def get_lineage_snapshot(
    dataset_version_id: str, container: ContainerDep, context: ContextDep
) -> LineageSnapshot:
    version = container.datasets.get_dataset_version(dataset_version_id, context)
    if version.lineage_snapshot_id is None:
        raise ApplicationError(
            "INVALID_STATE_TRANSITION",
            "数据集版本尚未绑定血缘快照",
            status_code=409,
            details={"dataset_version_id": dataset_version_id},
        )
    return container.lineage.get_snapshot(version.lineage_snapshot_id, context)
