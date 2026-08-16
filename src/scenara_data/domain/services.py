"""领域服务：不依赖仓储、对象存储和 HTTP 的纯规则。

Manifest 内容、质量判定、快照摘要和 Core 状态映射都在这里确定，保证同一输入始终得到
同一摘要（规范 12、38；指南 6、7、13）。
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

from scenara_data.domain.models import (
    CORE_DATASET_STATUS_MAP,
    CORE_DATASET_VERSION_STATUS_MAP,
    Annotation,
    AnnotationStatus,
    DatasetStatus,
    DatasetVersionStatus,
    ObjectReference,
    QualityCheck,
    QualityRule,
    QualityStatus,
    Sample,
)

MANIFEST_SCHEMA_VERSION = "1.0"
UNSPECIFIED_SPLIT = "unspecified"
#: 人物重识别样本必备字段（规范 18；指南 6.3）。
REID_REQUIRED_FIELDS = ("person_id", "camera_id", "bbox", "dataset_split")


def canonical_json(payload: Any) -> bytes:
    """确定性 JSON 编码：排序键、无空格、ASCII 转义。"""
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_of(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def rfc3339(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return moment.isoformat().replace("+00:00", "Z")


def manifest_object_key(dataset_id: str, version: str) -> str:
    return f"datasets/{dataset_id}/{version}/manifest.json"


def sample_object_key(dataset_id: str, version: str, sample_id: str, source_key: str) -> str:
    suffix = PurePosixPath(source_key).suffix or ".bin"
    return f"datasets/{dataset_id}/{version}/samples/{sample_id}{suffix}"


def split_counts(samples: Sequence[Sample]) -> dict[str, int]:
    counter = Counter(sample.dataset_split or UNSPECIFIED_SPLIT for sample in samples)
    return dict(sorted(counter.items()))


def build_manifest_payload(
    *,
    manifest_id: str,
    dataset_id: str,
    dataset_version_id: str,
    version: str,
    created_at: datetime,
    samples: Sequence[Sample],
    materialized: Mapping[str, ObjectReference],
    frozen_annotations: Mapping[str, Sequence[tuple[str, str]]] | None = None,
    quality_report_id: str | None = None,
    lineage_snapshot_id: str | None = None,
    annotation_snapshot_id: str | None = None,
) -> dict[str, Any]:
    """构造不可变 Manifest 文档；样本按 sample_id 排序保证摘要稳定。"""
    ordered = sorted(samples, key=lambda item: item.sample_id)
    missing = [sample.sample_id for sample in ordered if sample.sample_id not in materialized]
    if missing:
        raise ValueError(f"manifest requires materialized content for samples: {missing}")
    annotations = frozen_annotations or {}
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_id": manifest_id,
        "dataset_id": dataset_id,
        "dataset_version_id": dataset_version_id,
        "version": version,
        "created_at": rfc3339(created_at),
        "sample_count": len(ordered),
        "split_counts": split_counts(ordered),
        "quality_report_id": quality_report_id,
        "lineage_snapshot_id": lineage_snapshot_id,
        "annotation_snapshot_id": annotation_snapshot_id,
        "samples": [
            {
                "sample_id": sample.sample_id,
                "media_type": sample.media_type,
                "media_kind": sample.media_kind or sample.media_type,
                "content_ref": materialized[sample.sample_id].model_dump(mode="json"),
                "content_sha256": materialized[sample.sample_id].checksum,
                "source_ref": sample.source_ref.model_dump(mode="json"),
                "source_system": sample.source_system,
                "source_resource_type": sample.source_resource_type,
                "source_resource_id": sample.source_resource_id,
                "source_lineage": list(sample.source_lineage),
                "person_id": sample.person_id,
                "camera_id": sample.camera_id,
                "bbox": list(sample.bbox) if sample.bbox else None,
                "dataset_split": sample.dataset_split,
                "captured_at": rfc3339(sample.captured_at) if sample.captured_at else None,
                "annotations": [
                    {"annotation_id": annotation_id, "revision_id": revision_id}
                    for annotation_id, revision_id in sorted(annotations.get(sample.sample_id, ()))
                ],
                "metadata": sample.sample_metadata,
            }
            for sample in ordered
        ],
    }


def lineage_snapshot_checksum(lineage_ids: Iterable[str]) -> str:
    return sha256_of(canonical_json(sorted(lineage_ids)))


def annotation_snapshot_checksum(entries: Iterable[tuple[str, str]]) -> str:
    return sha256_of(canonical_json(sorted([list(entry) for entry in entries])))


def map_core_dataset_status(value: str) -> DatasetStatus:
    """Core 旧状态到 Data 状态的显式映射；未登记状态必须失败而不是静默兼容。"""
    try:
        return CORE_DATASET_STATUS_MAP[value.strip().lower()]
    except KeyError as exc:
        raise ValueError(f"unmapped core dataset status: {value}") from exc


def map_core_dataset_version_status(value: str) -> DatasetVersionStatus:
    try:
        return CORE_DATASET_VERSION_STATUS_MAP[value.strip().lower()]
    except KeyError as exc:
        raise ValueError(f"unmapped core dataset version status: {value}") from exc


def default_quality_rules() -> tuple[QualityRule, ...]:
    """未显式选择规则时使用的发布前最小规则集。"""
    return (
        QualityRule(
            rule_id="rule.sample_count_min",
            name="数据集版本至少包含一个样本",
            rule_type="sample_count_min",
            parameters={"minimum": 1},
        ),
        QualityRule(
            rule_id="rule.content_checksum",
            name="样本内容摘要可验证",
            rule_type="content_checksum",
            parameters={},
        ),
        QualityRule(
            rule_id="rule.unique_content",
            name="同一版本内样本内容不重复",
            rule_type="unique_content",
            parameters={},
        ),
    )


def evaluate_quality_rules(
    rules: Sequence[QualityRule],
    *,
    samples: Sequence[Sample],
    annotations: Sequence[Annotation] = (),
    checksum_failures: Sequence[str] = (),
) -> tuple[tuple[QualityCheck, ...], tuple[tuple[str, str, str, str | None], ...]]:
    """执行质量规则。

    返回 `(checks, issues)`；`issues` 元素为 `(rule_id, severity, message, sample_id)`，
    由应用层落库为 `QualityIssue`。规则未通过时不抛异常，由调用方按状态机决定后续动作。
    """
    checks: list[QualityCheck] = []
    issues: list[tuple[str, str, str, str | None]] = []
    accepted = {
        annotation.sample_id
        for annotation in annotations
        if annotation.status == AnnotationStatus.ACCEPTED
    }

    for rule in rules:
        if not rule.active:
            continue
        if rule.rule_type == "sample_count_min":
            minimum = int(rule.parameters.get("minimum", 1))
            passed = len(samples) >= minimum
            checks.append(
                QualityCheck(
                    check_id=rule.rule_id,
                    status=QualityStatus.PASSED if passed else QualityStatus.FAILED,
                    message=(
                        f"样本数量 {len(samples)} 满足下限 {minimum}"
                        if passed
                        else f"样本数量 {len(samples)} 低于下限 {minimum}"
                    ),
                    measured_value=len(samples),
                )
            )
            if not passed:
                issues.append((rule.rule_id, "error", f"样本数量不足：{len(samples)} < {minimum}", None))
        elif rule.rule_type == "content_checksum":
            failures = list(checksum_failures)
            passed = not failures
            checks.append(
                QualityCheck(
                    check_id=rule.rule_id,
                    status=QualityStatus.PASSED if passed else QualityStatus.FAILED,
                    message=("所有样本对象摘要验证通过" if passed else "存在对象缺失或摘要不匹配的样本"),
                    measured_value=len(failures),
                )
            )
            issues.extend((rule.rule_id, "error", "样本对象不存在或摘要不匹配", item) for item in failures)
        elif rule.rule_type == "unique_content":
            duplicates = _duplicate_checksums(samples)
            passed = not duplicates
            checks.append(
                QualityCheck(
                    check_id=rule.rule_id,
                    status=QualityStatus.PASSED if passed else QualityStatus.WARNING,
                    message=("样本内容摘要唯一" if passed else "存在内容重复的样本"),
                    measured_value=len(duplicates),
                )
            )
            for sample_id in duplicates:
                issues.append((rule.rule_id, "warning", "样本内容与同版本其他样本重复", sample_id))
        elif rule.rule_type == "split_present":
            required = tuple(str(item) for item in rule.parameters.get("splits", ("train", "query", "gallery")))
            present = split_counts(samples)
            missing = [item for item in required if present.get(item, 0) <= 0]
            passed = not missing
            checks.append(
                QualityCheck(
                    check_id=rule.rule_id,
                    status=QualityStatus.PASSED if passed else QualityStatus.FAILED,
                    message=("必需 split 齐备" if passed else f"缺少 split：{missing}"),
                    measured_value=json.dumps(present, sort_keys=True),
                )
            )
            if not passed:
                issues.append((rule.rule_id, "error", f"缺少必需 split：{missing}", None))
        elif rule.rule_type == "annotation_coverage":
            minimum_ratio = float(rule.parameters.get("minimum_ratio", 1.0))
            covered = sum(1 for sample in samples if sample.sample_id in accepted)
            ratio = (covered / len(samples)) if samples else 0.0
            passed = ratio >= minimum_ratio
            checks.append(
                QualityCheck(
                    check_id=rule.rule_id,
                    status=QualityStatus.PASSED if passed else QualityStatus.FAILED,
                    message=f"已接受标注覆盖率 {ratio:.4f}，下限 {minimum_ratio:.4f}",
                    measured_value=round(ratio, 6),
                )
            )
            if not passed:
                issues.extend(
                    (rule.rule_id, "error", "样本缺少已接受标注", sample.sample_id)
                    for sample in samples
                    if sample.sample_id not in accepted
                )
        elif rule.rule_type == "reid_fields_required":
            incomplete = [
                sample.sample_id
                for sample in samples
                if any(getattr(sample, field) is None for field in REID_REQUIRED_FIELDS)
            ]
            passed = not incomplete
            checks.append(
                QualityCheck(
                    check_id=rule.rule_id,
                    status=QualityStatus.PASSED if passed else QualityStatus.FAILED,
                    message=("人物重识别必备字段齐备" if passed else "存在缺少 ReID 必备字段的样本"),
                    measured_value=len(incomplete),
                )
            )
            issues.extend(
                (rule.rule_id, "error", f"缺少 ReID 必备字段之一：{REID_REQUIRED_FIELDS}", item)
                for item in incomplete
            )
        else:
            checks.append(
                QualityCheck(
                    check_id=rule.rule_id,
                    status=QualityStatus.FAILED,
                    message=f"未登记的质量规则类型：{rule.rule_type}",
                    measured_value=rule.rule_type,
                )
            )
            issues.append((rule.rule_id, "error", f"未登记的质量规则类型：{rule.rule_type}", None))

    return tuple(checks), tuple(issues)


def aggregate_quality_status(checks: Sequence[QualityCheck]) -> QualityStatus:
    if any(check.status == QualityStatus.FAILED for check in checks):
        return QualityStatus.FAILED
    if any(check.status == QualityStatus.WARNING for check in checks):
        return QualityStatus.WARNING
    return QualityStatus.PASSED


def quality_score(checks: Sequence[QualityCheck]) -> float:
    """兼容输入用的汇总分值；不作为长期唯一数据模型（指南 6.5）。"""
    if not checks:
        return 0.0
    weights = {QualityStatus.PASSED: 1.0, QualityStatus.WARNING: 0.5, QualityStatus.FAILED: 0.0}
    return round(sum(weights[check.status] for check in checks) / len(checks) * 100, 2)


def _duplicate_checksums(samples: Sequence[Sample]) -> list[str]:
    counts = Counter(sample.source_ref.checksum for sample in samples)
    duplicated = {checksum for checksum, count in counts.items() if count > 1}
    return sorted(sample.sample_id for sample in samples if sample.source_ref.checksum in duplicated)
