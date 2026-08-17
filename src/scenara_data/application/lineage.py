"""数据血缘应用服务（指南 6.5、M5）。"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime

from scenara_data.application.errors import ResourceNotFoundError
from scenara_data.application.support import ApplicationService, Clock, new_id, transactional, utc_now
from scenara_data.domain.models import LineageLink, LineageSnapshot
from scenara_data.domain.services import lineage_snapshot_checksum
from scenara_data.ports.interfaces import (
    AuditPort,
    LineageRepository,
    OutboxPort,
    RequestContext,
    UnitOfWork,
)


class LineageService(ApplicationService):
    def __init__(
        self,
        *,
        unit_of_work: UnitOfWork,
        lineage: LineageRepository,
        audit: AuditPort,
        outbox: OutboxPort,
        clock: Clock = utc_now,
    ) -> None:
        super().__init__(unit_of_work=unit_of_work, audit=audit, outbox=outbox, clock=clock)
        self._lineage = lineage

    def list_lineage(self, entity_id: str, context: RequestContext) -> list[LineageLink]:
        self._require(context, "data.lineage.read")
        return self._lineage.list_lineage(entity_id, context.organization_id, context.project_id)

    @transactional
    def record_edges(
        self,
        edges: Iterable[tuple[str, str, str, str, str]],
        context: RequestContext,
        *,
        occurred_at: datetime,
    ) -> tuple[str, ...]:
        """登记血缘边；元素为 `(source_type, source_id, target_type, target_id, relation)`。"""
        lineage_ids: list[str] = []
        for source_type, source_id, target_type, target_id, relation in edges:
            link = LineageLink(
                lineage_id=new_id("lin"),
                source_entity_type=source_type,
                source_entity_id=source_id,
                target_entity_type=target_type,
                target_entity_id=target_id,
                relation=relation,
                created_at=occurred_at,
            )
            self._lineage.add_lineage_link(link, context.organization_id, context.project_id)
            lineage_ids.append(link.lineage_id)
        return tuple(lineage_ids)

    def create_snapshot(
        self,
        *,
        dataset_version_id: str,
        lineage_ids: Sequence[str],
        context: RequestContext,
        occurred_at: datetime,
    ) -> LineageSnapshot:
        snapshot = LineageSnapshot(
            snapshot_id=new_id("lns"),
            dataset_version_id=dataset_version_id,
            lineage_ids=tuple(sorted(lineage_ids)),
            checksum=lineage_snapshot_checksum(lineage_ids),
            created_at=occurred_at,
        )
        self._lineage.add_lineage_snapshot(snapshot, context.organization_id, context.project_id)
        return snapshot

    def get_snapshot(self, snapshot_id: str, context: RequestContext) -> LineageSnapshot:
        self._require(context, "data.lineage.read")
        try:
            return self._lineage.get_lineage_snapshot(
                snapshot_id, context.organization_id, context.project_id
            )
        except KeyError as exc:
            raise ResourceNotFoundError("lineage_snapshot", snapshot_id) from exc
