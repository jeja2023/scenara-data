"""Dataset Builder（指南 2、M6）。

Builder 只编排既有 Dataset Version 状态机：创建版本 -> building -> 加入样本 -> 质量验证 ->
可选发布。它不绕过不可变性、质量门禁和审计。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from scenara_data.application.datasets import DatasetService
from scenara_data.application.errors import InputValidationError
from scenara_data.domain.models import DatasetManifest, DatasetVersion
from scenara_data.ports.interfaces import RequestContext


@dataclass(frozen=True, slots=True)
class BuildResult:
    dataset_version: DatasetVersion
    quality_report_id: str | None
    manifest: DatasetManifest | None


class DatasetBuilderService:
    def __init__(self, *, datasets: DatasetService) -> None:
        self._datasets = datasets

    def build_version(
        self,
        *,
        dataset_id: str,
        version: str,
        sample_ids: Sequence[str],
        context: RequestContext,
        publish: bool = False,
        rule_ids: tuple[str, ...] = (),
        dataset_version_id: str | None = None,
    ) -> BuildResult:
        if not sample_ids:
            raise InputValidationError("数据集构建必须至少包含一个样本")
        if len(set(sample_ids)) != len(sample_ids):
            raise InputValidationError("数据集构建样本不能重复")
        created = self._datasets.create_dataset_version(
            dataset_id=dataset_id,
            version=version,
            context=context,
            dataset_version_id=dataset_version_id,
        )
        self._datasets.begin_build(created.dataset_version_id, context)
        for sample_id in sample_ids:
            self._datasets.add_sample_to_version(created.dataset_version_id, sample_id, context)
        ready, report = self._datasets.validate_dataset_version(
            created.dataset_version_id, context, rule_ids=rule_ids
        )
        if not publish:
            return BuildResult(dataset_version=ready, quality_report_id=report.report_id, manifest=None)
        published, manifest = self._datasets.publish_dataset_version(created.dataset_version_id, context)
        return BuildResult(
            dataset_version=published, quality_report_id=report.report_id, manifest=manifest
        )
