"""数据质量应用服务（指南 6.5、M5）。"""

from __future__ import annotations

from collections.abc import Sequence

from scenara_data.application.errors import ConflictError, InputValidationError, ResourceNotFoundError
from scenara_data.application.support import ApplicationService, Clock, new_id, transactional, utc_now
from scenara_data.domain.models import (
    DataQualityReport,
    DatasetVersion,
    JobStatus,
    QualityIssue,
    QualityRule,
    QualityRun,
    QualityStatus,
    Sample,
)
from scenara_data.domain.services import (
    aggregate_quality_status,
    default_quality_rules,
    evaluate_quality_rules,
    quality_score,
)
from scenara_data.ports.interfaces import (
    AnnotationRepository,
    AuditPort,
    DatasetRepository,
    ObjectStorageProvider,
    OutboxPort,
    QualityRepository,
    RequestContext,
    SampleRepository,
    UnitOfWork,
)


class QualityService(ApplicationService):
    def __init__(
        self,
        *,
        unit_of_work: UnitOfWork,
        quality: QualityRepository,
        datasets: DatasetRepository,
        samples: SampleRepository,
        annotations: AnnotationRepository,
        object_storage: ObjectStorageProvider,
        audit: AuditPort,
        outbox: OutboxPort,
        clock: Clock = utc_now,
    ) -> None:
        super().__init__(unit_of_work=unit_of_work, audit=audit, outbox=outbox, clock=clock)
        self._quality = quality
        self._datasets = datasets
        self._samples = samples
        self._annotations = annotations
        self._object_storage = object_storage

    # ------------------------------------------------------------ 质量规则

    @transactional
    def create_rule(
        self,
        *,
        name: str,
        rule_type: str,
        parameters: dict[str, object],
        context: RequestContext,
        rule_id: str | None = None,
    ) -> QualityRule:
        self._require(context, "data.quality.run")
        value = QualityRule(
            rule_id=rule_id or new_id("dqu"),
            name=name,
            rule_type=rule_type,
            parameters=dict(parameters),
        )
        try:
            self._quality.add_quality_rule(value, context.organization_id, context.project_id)
        except ValueError as exc:
            raise ConflictError("质量规则标识已存在", details={"rule_id": value.rule_id}) from exc
        return value

    def list_rules(
        self, context: RequestContext, *, limit: int, offset: int
    ) -> tuple[list[QualityRule], int]:
        self._require(context, "data.dataset.read")
        return self._quality.list_quality_rules(
            context.organization_id, context.project_id, limit=limit, offset=offset
        )

    # ------------------------------------------------------------ 质量运行

    @transactional
    def run_quality(
        self,
        dataset_version_id: str,
        context: RequestContext,
        *,
        rule_ids: tuple[str, ...] = (),
    ) -> tuple[QualityRun, DataQualityReport]:
        self._require(context, "data.quality.run")
        version = self._require_version(dataset_version_id, context)
        rules = self._resolve_rules(rule_ids, context)
        samples = self._samples.list_version_samples(
            dataset_version_id, context.organization_id, context.project_id
        )
        created_at = self._clock()
        run = QualityRun(
            run_id=new_id("dqn"),
            dataset_version_id=dataset_version_id,
            status=JobStatus.QUEUED,
            rule_ids=tuple(rule.rule_id for rule in rules),
            created_by=context.principal_id,
            created_at=created_at,
        )
        self._quality.add_quality_run(run, context.organization_id, context.project_id)
        run = run.transition(JobStatus.RUNNING, occurred_at=created_at)
        self._quality.update_quality_run(run, context.organization_id, context.project_id)
        report = self._execute(run, version, rules, samples, context)
        return self._quality.get_quality_run(run.run_id, context.organization_id, context.project_id), report

    def get_run(self, run_id: str, context: RequestContext) -> QualityRun:
        self._require(context, "data.dataset.read")
        try:
            return self._quality.get_quality_run(run_id, context.organization_id, context.project_id)
        except KeyError as exc:
            raise ResourceNotFoundError("quality_run", run_id) from exc

    def list_runs(
        self, dataset_version_id: str, context: RequestContext, *, limit: int, offset: int
    ) -> tuple[list[QualityRun], int]:
        self._require(context, "data.dataset.read")
        self._require_version(dataset_version_id, context)
        return self._quality.list_quality_runs(
            dataset_version_id, context.organization_id, context.project_id, limit=limit, offset=offset
        )

    def list_issues(self, run_id: str, context: RequestContext) -> list[QualityIssue]:
        self._require(context, "data.dataset.read")
        self.get_run(run_id, context)
        return self._quality.list_quality_issues(run_id, context.organization_id, context.project_id)

    def get_report(self, report_id: str, context: RequestContext) -> DataQualityReport:
        self._require(context, "data.dataset.read")
        try:
            return self._quality.get_quality_report(report_id, context.organization_id, context.project_id)
        except KeyError as exc:
            raise ResourceNotFoundError("data_quality_report", report_id) from exc

    # ------------------------------------------------------------------ 内部

    def _execute(
        self,
        run: QualityRun,
        version: DatasetVersion,
        rules: Sequence[QualityRule],
        samples: Sequence[Sample],
        context: RequestContext,
    ) -> DataQualityReport:
        checksum_failures = self._verify_content(samples)
        annotations = self._annotations.list_sample_annotations(
            [sample.sample_id for sample in samples], context.organization_id, context.project_id
        )
        checks, issues = evaluate_quality_rules(
            rules, samples=samples, annotations=annotations, checksum_failures=checksum_failures
        )
        if not checks:
            raise InputValidationError("质量运行必须至少执行一条规则")
        occurred_at = self._clock()
        issue_ids: list[str] = []
        for rule_id, severity, message, sample_id in issues:
            issue = QualityIssue(
                issue_id=new_id("dqi"),
                quality_run_id=run.run_id,
                rule_id=rule_id,
                sample_id=sample_id,
                severity=severity,  # type: ignore[arg-type]
                message=message,
            )
            self._quality.add_quality_issue(
                issue,
                context.organization_id,
                context.project_id,
            )
            issue_ids.append(issue.issue_id)
        status = aggregate_quality_status(checks)
        report = DataQualityReport(
            report_id=new_id("dqr"),
            dataset_version_id=version.dataset_version_id,
            status=status,
            checks=checks,
            created_by=context.principal_id,
            created_at=occurred_at,
            quality_run_id=run.run_id,
            quality_score=quality_score(checks),
            issue_ids=tuple(issue_ids),
        )
        self._quality.add_quality_report(report, context.organization_id, context.project_id)
        completed = run.transition(
            JobStatus.SUCCEEDED if status != QualityStatus.FAILED else JobStatus.FAILED,
            occurred_at=occurred_at,
            report_id=report.report_id,
            error_message=None if status != QualityStatus.FAILED else "数据质量规则未通过",
        )
        self._quality.update_quality_run(completed, context.organization_id, context.project_id)
        self._emit(
            "quality.completed" if status != QualityStatus.FAILED else "quality.failed",
            context,
            occurred_at,
            {
                "quality_run_id": run.run_id,
                "report_id": report.report_id,
                "dataset_version_id": version.dataset_version_id,
                "status": status,
                "quality_score": report.quality_score,
            },
        )
        return report

    def _verify_content(self, samples: Sequence[Sample]) -> tuple[str, ...]:
        failures: list[str] = []
        for sample in samples:
            reference = sample.content_ref or sample.source_ref
            try:
                self._object_storage.read_verified(reference)
            except (FileNotFoundError, ValueError):
                failures.append(sample.sample_id)
        return tuple(failures)

    def _resolve_rules(self, rule_ids: tuple[str, ...], context: RequestContext) -> tuple[QualityRule, ...]:
        if not rule_ids:
            return default_quality_rules()
        resolved: list[QualityRule] = []
        for rule_id in rule_ids:
            try:
                resolved.append(
                    self._quality.get_quality_rule(rule_id, context.organization_id, context.project_id)
                )
            except KeyError as exc:
                raise ResourceNotFoundError("quality_rule", rule_id) from exc
        return tuple(resolved)

    def _require_version(self, dataset_version_id: str, context: RequestContext) -> DatasetVersion:
        try:
            return self._datasets.get_dataset_version(
                dataset_version_id, context.organization_id, context.project_id
            )
        except KeyError as exc:
            raise ResourceNotFoundError("dataset_version", dataset_version_id) from exc
