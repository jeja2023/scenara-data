"""Annotation 内部 API：标注、追加式修订、任务、分派、复核与服务商（指南 11.1）。"""

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
from scenara_data.api.schemas import (
    AnnotationPage,
    AnnotationProviderPage,
    AnnotationTaskPage,
    AnnotationTaskReviewResponse,
    AppendRevisionRequest,
    CreateAnnotationProviderRequest,
    CreateAnnotationRequest,
    CreateAnnotationTaskRequest,
    ReviewAnnotationRequest,
    ReviewAnnotationTaskRequest,
    RevisionResponse,
    TransitionAnnotationTaskRequest,
)
from scenara_data.domain.models import (
    Annotation,
    AnnotationProvider,
    AnnotationSnapshot,
    AnnotationTask,
    AnnotationTaskStatus,
)

router = APIRouter(prefix="/internal/v1", tags=["annotations"])


@router.post(
    "/annotations",
    response_model=Annotation,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
    summary="创建标注及首个修订",
)
def create_annotation(
    body: CreateAnnotationRequest, container: ContainerDep, context: ContextDep
) -> JSONResponse:
    return idempotent(
        container,
        context=context,
        operation="annotation.create",
        request_value=body.model_dump(mode="json"),
        status_code=status.HTTP_201_CREATED,
        callback=lambda: container.annotations.create_annotation(
            sample_id=body.sample_id,
            schema_id=body.schema_id,
            payload=body.payload,
            annotation_id=body.annotation_id,
            task_id=body.task_id,
            context=context,
        ),
    )


@router.get(
    "/samples/{sample_id}/annotations",
    response_model=AnnotationPage,
    responses=ERROR_RESPONSES,
    summary="列出样本标注",
)
def list_annotations(
    sample_id: str,
    container: ContainerDep,
    context: ContextDep,
    limit: LimitQuery = 50,
    cursor: CursorQuery = None,
) -> dict[str, Any]:
    offset = offset_of(cursor)
    items, total = container.annotations.list_annotations(
        sample_id, context, limit=limit, offset=offset
    )
    return paged(items, total, offset=offset, limit=limit)


@router.post(
    "/annotations/{annotation_id}/revisions",
    response_model=RevisionResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
    summary="追加标注修订（不覆盖已审核修订）",
)
def append_revision(
    annotation_id: str,
    body: AppendRevisionRequest,
    container: ContainerDep,
    context: ContextDep,
) -> JSONResponse:
    def append() -> dict[str, Any]:
        annotation, revision = container.annotations.append_revision(
            annotation_id, payload=body.payload, context=context
        )
        return {"annotation": annotation, "revision": revision}

    return idempotent(
        container,
        context=context,
        operation=f"annotation.revision.append:{annotation_id}",
        request_value=body.model_dump(mode="json"),
        status_code=status.HTTP_201_CREATED,
        callback=append,
    )


@router.get(
    "/annotations/{annotation_id}/revisions",
    responses=ERROR_RESPONSES,
    summary="列出标注修订历史",
)
def list_revisions(
    annotation_id: str, container: ContainerDep, context: ContextDep
) -> dict[str, Any]:
    items = container.annotations.list_revisions(annotation_id, context)
    return {"items": items, "total": len(items), "next_cursor": None}


@router.post(
    "/annotations/{annotation_id}/submit",
    response_model=Annotation,
    responses=ERROR_RESPONSES,
    summary="提交标注进入审核",
)
def submit_annotation(
    annotation_id: str, container: ContainerDep, context: ContextDep
) -> JSONResponse:
    return idempotent(
        container,
        context=context,
        operation=f"annotation.submit:{annotation_id}",
        request_value={"annotation_id": annotation_id},
        status_code=status.HTTP_200_OK,
        callback=lambda: container.annotations.submit_annotation(annotation_id, context),
    )


@router.post(
    "/annotations/{annotation_id}/review",
    response_model=Annotation,
    responses=ERROR_RESPONSES,
    summary="复核标注",
)
def review_annotation(
    annotation_id: str,
    body: ReviewAnnotationRequest,
    container: ContainerDep,
    context: ContextDep,
) -> JSONResponse:
    return idempotent(
        container,
        context=context,
        operation=f"annotation.review:{annotation_id}",
        request_value=body.model_dump(mode="json"),
        status_code=status.HTTP_200_OK,
        callback=lambda: container.annotations.review_annotation(annotation_id, body.status, context),
    )


@router.post(
    "/annotation-tasks",
    response_model=AnnotationTask,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
    summary="创建标注任务",
)
def create_annotation_task(
    body: CreateAnnotationTaskRequest, container: ContainerDep, context: ContextDep
) -> JSONResponse:
    return idempotent(
        container,
        context=context,
        operation="annotation.task.create",
        request_value=body.model_dump(mode="json"),
        status_code=status.HTTP_201_CREATED,
        callback=lambda: container.annotations.create_task(
            dataset_id=body.dataset_id,
            schema_id=body.schema_id,
            sample_ids=body.sample_ids,
            task_id=body.task_id,
            provider_id=body.provider_id,
            metadata=body.metadata,
            context=context,
        ),
    )


@router.get(
    "/annotation-tasks",
    response_model=AnnotationTaskPage,
    responses=ERROR_RESPONSES,
    summary="分页列出标注任务",
)
def list_annotation_tasks(
    container: ContainerDep,
    context: ContextDep,
    limit: LimitQuery = 50,
    cursor: CursorQuery = None,
    dataset_id: str | None = Query(default=None, max_length=128),
    task_status: AnnotationTaskStatus | None = Query(default=None, alias="status"),
) -> dict[str, Any]:
    offset = offset_of(cursor)
    items, total = container.annotations.list_tasks(
        context,
        limit=limit,
        offset=offset,
        dataset_id=dataset_id,
        status=None if task_status is None else str(task_status),
    )
    return paged(items, total, offset=offset, limit=limit)


@router.get(
    "/annotation-tasks/{task_id}",
    response_model=AnnotationTask,
    responses=ERROR_RESPONSES,
    summary="读取标注任务",
)
def get_annotation_task(
    task_id: str, container: ContainerDep, context: ContextDep
) -> AnnotationTask:
    return container.annotations.get_task(task_id, context)


@router.post(
    "/annotation-tasks/{task_id}/transition",
    response_model=AnnotationTask,
    responses=ERROR_RESPONSES,
    summary="推进标注任务状态并登记分派",
)
def transition_annotation_task(
    task_id: str,
    body: TransitionAnnotationTaskRequest,
    container: ContainerDep,
    context: ContextDep,
) -> JSONResponse:
    return idempotent(
        container,
        context=context,
        operation=f"annotation.task.transition:{task_id}",
        request_value=body.model_dump(mode="json"),
        status_code=status.HTTP_200_OK,
        callback=lambda: container.annotations.transition_task(
            task_id, body.status, context, assignee_principal_id=body.assignee_principal_id
        ),
    )


@router.post(
    "/annotation-tasks/{task_id}/review",
    response_model=AnnotationTaskReviewResponse,
    responses=ERROR_RESPONSES,
    summary="复核标注任务",
)
def review_annotation_task(
    task_id: str,
    body: ReviewAnnotationTaskRequest,
    container: ContainerDep,
    context: ContextDep,
) -> JSONResponse:
    def review() -> dict[str, Any]:
        task, record = container.annotations.review_task(
            task_id,
            decision=body.decision,
            comment=body.comment,
            revision_id=body.revision_id,
            consistency_score=body.consistency_score,
            context=context,
        )
        return {"task": task, "review": record}

    return idempotent(
        container,
        context=context,
        operation=f"annotation.task.review:{task_id}",
        request_value=body.model_dump(mode="json"),
        status_code=status.HTTP_200_OK,
        callback=review,
    )


@router.get(
    "/annotation-tasks/{task_id}/assignments",
    responses=ERROR_RESPONSES,
    summary="列出标注任务分派",
)
def list_assignments(task_id: str, container: ContainerDep, context: ContextDep) -> dict[str, Any]:
    items = container.annotations.list_assignments(task_id, context)
    return {"items": items, "total": len(items), "next_cursor": None}


@router.get(
    "/annotation-tasks/{task_id}/reviews",
    responses=ERROR_RESPONSES,
    summary="列出标注任务复核记录",
)
def list_reviews(task_id: str, container: ContainerDep, context: ContextDep) -> dict[str, Any]:
    items = container.annotations.list_reviews(task_id, context)
    return {"items": items, "total": len(items), "next_cursor": None}


@router.post(
    "/annotation-providers",
    response_model=AnnotationProvider,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
    summary="登记标注服务商",
)
def create_provider(
    body: CreateAnnotationProviderRequest, container: ContainerDep, context: ContextDep
) -> JSONResponse:
    return idempotent(
        container,
        context=context,
        operation="annotation.provider.create",
        request_value=body.model_dump(mode="json"),
        status_code=status.HTTP_201_CREATED,
        callback=lambda: container.annotations.create_provider(
            name=body.name,
            provider_type=body.provider_type,
            provider_id=body.provider_id,
            config_ref=body.config_ref,
            endpoint=body.endpoint,
            context=context,
        ),
    )


@router.post(
    "/annotation-providers/{provider_id}/probe",
    response_model=AnnotationProvider,
    responses=ERROR_RESPONSES,
    summary="检查标注服务商配置状态",
)
def probe_provider(
    provider_id: str, container: ContainerDep, context: ContextDep
) -> JSONResponse:
    return idempotent(
        container,
        context=context,
        operation=f"annotation.provider.probe:{provider_id}",
        request_value={"provider_id": provider_id},
        status_code=status.HTTP_200_OK,
        callback=lambda: container.annotations.probe_provider(provider_id, context),
    )


@router.get(
    "/annotation-providers",
    response_model=AnnotationProviderPage,
    responses=ERROR_RESPONSES,
    summary="分页列出标注服务商",
)
def list_providers(
    container: ContainerDep,
    context: ContextDep,
    limit: LimitQuery = 50,
    cursor: CursorQuery = None,
) -> dict[str, Any]:
    offset = offset_of(cursor)
    items, total = container.annotations.list_providers(context, limit=limit, offset=offset)
    return paged(items, total, offset=offset, limit=limit)


@router.get(
    "/annotation-snapshots/{snapshot_id}",
    response_model=AnnotationSnapshot,
    responses=ERROR_RESPONSES,
    summary="读取发布时冻结的标注快照",
)
def get_annotation_snapshot(
    snapshot_id: str, container: ContainerDep, context: ContextDep
) -> AnnotationSnapshot:
    return container.annotations.get_annotation_snapshot(snapshot_id, context)
