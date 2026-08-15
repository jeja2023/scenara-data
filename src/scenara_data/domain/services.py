from __future__ import annotations

from datetime import datetime

from scenara_data.domain.models import DatasetVersion, DatasetVersionStatus, ObjectReference
from scenara_data.ports.interfaces import AuditPort, DatasetVersionRepository, RequestContext


class DatasetVersionService:
    def __init__(self, repository: DatasetVersionRepository, audit: AuditPort) -> None:
        self._repository = repository
        self._audit = audit

    def publish(
        self,
        dataset_version_id: str,
        manifest_ref: ObjectReference,
        occurred_at: datetime,
        context: RequestContext,
    ) -> DatasetVersion:
        current = self._repository.get(dataset_version_id)
        published = current.transition(
            DatasetVersionStatus.PUBLISHED,
            manifest_ref=manifest_ref,
            occurred_at=occurred_at,
        )
        self._repository.save(published)
        self._audit.record(
            action="dataset.version.publish",
            entity_id=dataset_version_id,
            context=context,
        )
        return published
