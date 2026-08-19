"""难例承接内部 API（指南 11.1、14）。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from scenara_data.api.deps import ContainerDep, ContextDep, idempotent
from scenara_data.api.routers.datasets import ERROR_RESPONSES
from scenara_data.api.schemas import (
    HardSampleIntakeRequest,
    HardSampleIntakeResponse,
    validate_utc_rfc3339,
)
from scenara_data.application.errors import InputValidationError
from scenara_data.application.hard_samples import IntakeResult
from scenara_data.domain.models import HardSampleHandoff, HardSampleImport, HardSampleManifest
from scenara_data.ports.interfaces import RequestContext

router = APIRouter(prefix="/internal/v1", tags=["难例"])


@router.post(
    "/hard-sample-manifests",
    response_model=HardSampleIntakeResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=ERROR_RESPONSES,
    summary="接收 Core 已批准的难例清单",
)
def ingest_hard_sample_manifest(
    body: HardSampleIntakeRequest, container: ContainerDep, context: ContextDep
) -> JSONResponse:
    manifest = _domain_manifest(body, context)

    def ingest() -> dict[str, object]:
        result = container.hard_samples.ingest_manifest(
            manifest,
            context,
            annotation_schema_id=body.annotation_schema_id,
            build_version=body.build_version,
            publish=body.publish,
        )
        return _intake_payload(result)

    return idempotent(
        container,
        context=context,
        operation="hard_sample.manifest.ingest",
        request_value=body.model_dump(mode="json"),
        status_code=status.HTTP_202_ACCEPTED,
        callback=ingest,
    )


@router.get(
    "/hard-sample-imports/{import_id}",
    response_model=HardSampleImport,
    responses=ERROR_RESPONSES,
    summary="查询难例导入结果",
)
def get_hard_sample_import(
    import_id: str, container: ContainerDep, context: ContextDep
) -> HardSampleImport:
    return container.hard_samples.get_import(import_id, context)


def _intake_payload(result: IntakeResult) -> dict[str, object]:
    record = result.hard_sample_import
    return {
        "import_id": record.import_id,
        "manifest_id": record.manifest_id,
        "status": record.status,
        "accepted_count": record.accepted_count,
        "rejected_count": record.rejected_count,
        "skipped_count": record.skipped_count,
        "sample_ids": list(record.sample_ids),
        "annotation_task_ids": list(record.annotation_task_ids),
        "dataset_version_id": result.dataset_version_id,
        "replayed": result.replayed,
    }


def _domain_manifest(body: HardSampleIntakeRequest, context: RequestContext) -> HardSampleManifest:
    contract = body.manifest
    if (contract.tenant_id, contract.project_id) != (context.tenant_id, context.project_id):
        raise InputValidationError(
            "难例清单 tenant/project 与身份上下文不一致",
            details={"manifest_id": contract.manifest_id},
        )
    sources = {source.feedback_id: source for source in body.sources}
    split_map = {"train": "train", "validation": "query", "test": "gallery"}
    handoffs: list[HardSampleHandoff] = []
    for item in contract.items:
        source = sources[item.feedback_id]
        handoffs.append(
            HardSampleHandoff(
                handoff_id=item.feedback_id,
                source_result_id=source.source_result_id or item.feedback_id,
                source_ref=source.source_ref,
                reason=item.kind,
                approved=True,
                authorized=item.authorized_for_training,
                deidentified=item.deidentified,
                occurred_at=source.occurred_at,
                source_system="scenara",
                source_resource_type=source.source_resource_type,
                media_type=source.media_type,
                person_id=source.person_id,
                camera_id=source.camera_id,
                bbox=source.bbox,
                dataset_split=source.dataset_split or split_map[contract.split],
                captured_at=source.captured_at,
                handoff_metadata={
                    "feedback_id": item.feedback_id,
                    "result_ref": item.result_ref,
                    "model_id": item.model_id,
                    "model_version": item.model_version,
                    "pipeline_id": item.pipeline_id,
                    "pipeline_version": item.pipeline_version,
                    "correction": item.correction,
                    "label_schema": contract.label_schema,
                },
            )
        )
    return HardSampleManifest(
        manifest_id=contract.manifest_id,
        source_system="scenara",
        generated_at=datetime.fromisoformat(validate_utc_rfc3339(contract.created_at)[:-1] + "+00:00"),
        items=tuple(handoffs),
        dataset_id=contract.dataset_id,
        contract_sha256=contract.sha256,
    )
