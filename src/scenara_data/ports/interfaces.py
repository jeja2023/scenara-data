from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from scenara_data.domain.models import DatasetVersion, ObjectReference


@dataclass(frozen=True, slots=True)
class RequestContext:
    organization_id: str
    project_id: str
    principal_id: str
    permission_scopes: tuple[str, ...]
    request_id: str
    trace_id: str
    idempotency_key: str | None = None


class DatasetVersionRepository(Protocol):
    def get(self, dataset_version_id: str) -> DatasetVersion: ...

    def save(self, value: DatasetVersion) -> None: ...


class ObjectStorageProvider(Protocol):
    def put_immutable(self, key: str, content: bytes, content_type: str) -> ObjectReference: ...

    def read_verified(self, reference: ObjectReference) -> bytes: ...


class AuditPort(Protocol):
    def record(self, *, action: str, entity_id: str, context: RequestContext) -> None: ...
