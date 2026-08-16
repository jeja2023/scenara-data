"""Data Quality 与 Data Lineage 内部 API（指南 6.5）。"""

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
from scenara_data.api.routers.datasets import ERROR_RESPONSES
from scenara_data.api.schemas import (
    CreateQualityRuleRequest,
    CreateQualityRunRequest,
    QualityRulePage,
    QualityRunPage,
    QualityRunResponse,
)
from scenara_data.domain.models import DataQualityReport, QualityRule, QualityRun

router = APIRouter(prefix="/internal/v1", tags=["quality"])


@router.post(
    "/quality-rules",
    response_model=QualityRule,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
    summary="登记质量规则",
)
def create_quality_rule(
    body: CreateQualityRuleRequest, container: ContainerDep, context: ContextDep
) -> JSONResponse:
    return idempotent(
        container,
        context=context,
        operation="quality.rule.create",
        request_value=body.model_dump(mode="json"),
        status_code=status.HTTP_201_CREATED,
        callback=lambda: container.quality.create_rule(
            name=body.name,
            rule_type=body.rule_type,
            parameters=body.parameters,
            rule_id=body.rule_id,
            context=context,
        ),
    )


@router.get(
    "/quality-rules", response_model=QualityRulePage, responses=ERROR_RESPONSES, summary="分页列出质量规则"
)
def list_quality_rules(
    container: ContainerDep,
    context: ContextDep,
    limit: LimitQuery = 50,
    cursor: CursorQuery = None,
) -> dict[str, Any]:
    offset = offset_of(cursor)
    items, total = container.quality.list_rules(context, limit=limit, offset=offset)
    return paged(items, total, offset=offset, limit=limit)


@router.post(
    "/quality-runs",
    response_model=QualityRunResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
    summary="对数据集版本执行质量运行",
)
def create_quality_run(
    body: CreateQualityRunRequest, container: ContainerDep, context: ContextDep
) -> JSONResponse:
    def execute() -> dict[str, Any]:
        run, report = container.quality.run_quality(
            body.dataset_version_id, context, rule_ids=body.rule_ids
        )
        return {"quality_run": run, "quality_report": report}

    return idempotent(
        container,
        context=context,
        operation=f"quality.run:{body.dataset_version_id}",
        request_value=body.model_dump(mode="json"),
        status_code=status.HTTP_201_CREATED,
        callback=execute,
    )


@router.get(
    "/quality-runs/{run_id}", response_model=QualityRun, responses=ERROR_RESPONSES, summary="读取质量运行"
)
def get_quality_run(run_id: str, container: ContainerDep, context: ContextDep) -> QualityRun:
    return container.quality.get_run(run_id, context)


@router.get(
    "/quality-runs/{run_id}/issues", responses=ERROR_RESPONSES, summary="列出质量问题"
)
def list_quality_issues(run_id: str, container: ContainerDep, context: ContextDep) -> dict[str, Any]:
    items = container.quality.list_issues(run_id, context)
    return {"items": items, "total": len(items), "next_cursor": None}


@router.get(
    "/dataset-versions/{dataset_version_id}/quality-runs",
    response_model=QualityRunPage,
    responses=ERROR_RESPONSES,
    summary="列出数据集版本的质量运行",
)
def list_version_quality_runs(
    dataset_version_id: str,
    container: ContainerDep,
    context: ContextDep,
    limit: LimitQuery = 50,
    cursor: CursorQuery = None,
) -> dict[str, Any]:
    offset = offset_of(cursor)
    items, total = container.quality.list_runs(
        dataset_version_id, context, limit=limit, offset=offset
    )
    return paged(items, total, offset=offset, limit=limit)


@router.get(
    "/data-quality-reports/{report_id}",
    response_model=DataQualityReport,
    responses=ERROR_RESPONSES,
    summary="读取质量报告",
)
def get_quality_report(
    report_id: str, container: ContainerDep, context: ContextDep
) -> DataQualityReport:
    return container.quality.get_report(report_id, context)
