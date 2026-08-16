from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from scenara_data.adapters.memory import (
    InMemoryAuditPort,
    InMemoryDataRepository,
    InMemoryIdempotencyStore,
    InMemoryObjectStorage,
    InMemoryOutbox,
    PresignedUrlError,
)
from scenara_data.domain.models import AuditRecord, Dataset, OutboxEvent
from scenara_data.ports.interfaces import IdempotencyRecord

NOW = datetime(2026, 8, 16, 1, 0, tzinfo=UTC)


def test_memory_transaction_rolls_back_domain_audit_outbox_and_idempotency() -> None:
    repository = InMemoryDataRepository()
    audit = InMemoryAuditPort()
    outbox = InMemoryOutbox()
    idempotency = InMemoryIdempotencyStore()
    repository.register_transaction_participant(audit)
    repository.register_transaction_participant(outbox)
    repository.register_transaction_participant(idempotency)

    dataset = Dataset(
        dataset_id="dst_rollback",
        name="rollback",
        tenant_id="tenant-a",
        project_id="project-a",
        created_by="user-a",
        created_at=NOW,
    )
    audit_record = AuditRecord(
        audit_id="aud_rollback",
        action="dataset.create",
        entity_type="dataset",
        entity_id=dataset.dataset_id,
        organization_id="tenant-a",
        project_id="project-a",
        principal_id="user-a",
        request_id="req-rollback",
        trace_id="trace-rollback",
        occurred_at=NOW,
        result="succeeded",
        after=dataset.model_dump(mode="json"),
    )
    event = OutboxEvent(
        event_id="evt_rollback",
        event_type="dataset.created",
        event_version="1.0",
        occurred_at=NOW,
        producer="scenara-data",
        tenant_id="tenant-a",
        project_id="project-a",
        request_id="req-rollback",
        trace_id="trace-rollback",
        data={"dataset_id": dataset.dataset_id},
    )

    with pytest.raises(RuntimeError, match="rollback"):
        with repository.transaction():
            repository.add_dataset(dataset)
            audit.record(audit_record)
            outbox.append(event)
            idempotency.save(
                IdempotencyRecord(
                    scope="tenant-a:project-a:user-a:dataset.create",
                    key="rollback",
                    request_hash="request-hash",
                    status_code=201,
                    response_payload={"dataset_id": dataset.dataset_id},
                )
            )
            raise RuntimeError("rollback")

    with pytest.raises(KeyError):
        repository.get_dataset(dataset.dataset_id, "tenant-a", "project-a")
    assert audit.records == []
    assert outbox.events == []
    assert idempotency.get("tenant-a:project-a:user-a:dataset.create", "rollback") is None


def test_presigned_memory_url_supports_escaped_object_keys_and_expiry() -> None:
    storage = InMemoryObjectStorage(signing_key=b"test-signing-key")
    reference = storage.put_immutable(
        "datasets/person 1/image sample.jpg", b"content", "image/jpeg"
    )
    url = storage.presign_read(reference, 60)

    assert storage.resolve_presigned(url) == b"content"
    with pytest.raises(PresignedUrlError, match="过期"):
        storage.resolve_presigned(url, now=datetime.now(UTC) + timedelta(minutes=2))


def test_outbox_claim_uses_a_lease_to_avoid_parallel_duplicate_delivery() -> None:
    outbox = InMemoryOutbox()
    event = OutboxEvent(
        event_id="evt_claim_lease",
        event_type="dataset.created",
        event_version="1.0",
        occurred_at=NOW,
        producer="scenara-data",
        tenant_id="tenant-a",
        project_id="project-a",
        request_id="req-claim",
        trace_id="trace-claim",
        data={"dataset_id": "dst_claim"},
    )
    outbox.append(event)

    first = outbox.claim_pending(limit=1, now=NOW)
    parallel = outbox.claim_pending(limit=1, now=NOW)
    expired_lease = outbox.claim_pending(limit=1, now=NOW + timedelta(seconds=31))

    assert [item.event.event_id for item in first] == [event.event_id]
    assert parallel == []
    assert [item.event.event_id for item in expired_lease] == [event.event_id]
