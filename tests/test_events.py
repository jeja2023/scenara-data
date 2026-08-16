from __future__ import annotations

from datetime import UTC, datetime

from scenara_data.adapters.events import EventTransportSettings, HttpEventPublisher
from scenara_data.adapters.memory import InMemoryOutbox
from scenara_data.application.outbox import OutboxDispatcher
from scenara_data.domain.models import OutboxEvent


class AcceptedResponse:
    status_code = 202


class RecordingCoreClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object], dict[str, str]]] = []

    def post(self, endpoint: str, *, json: dict[str, object], headers: dict[str, str]) -> AcceptedResponse:
        self.calls.append((endpoint, json, headers))
        return AcceptedResponse()


def test_outbox_dispatcher_delivers_the_formal_event_envelope_to_core() -> None:
    event = OutboxEvent(
        event_id="evt_data_1",
        event_type="dataset.version.published",
        event_version="1.0",
        occurred_at=datetime(2026, 8, 16, 4, 0, tzinfo=UTC),
        tenant_id="tenant-a",
        project_id="project-a",
        request_id="req-data-event",
        trace_id="0123456789abcdef0123456789abcdef",
        data={"dataset_id": "dst_1", "dataset_version_id": "dsv_1"},
    )
    outbox = InMemoryOutbox()
    outbox.append(event)
    core = RecordingCoreClient()
    publisher = HttpEventPublisher(
        EventTransportSettings(
            endpoint="http://core/internal/v1/data/events",
            token="data-event-token",
            max_attempts=1,
        ),
        client=core,
    )
    summary = OutboxDispatcher(dispatch=outbox, publisher=publisher).dispatch_once()

    assert (summary.claimed, summary.delivered, summary.failed) == (1, 1, 0)
    assert len(core.calls) == 1
    endpoint, payload, headers = core.calls[0]
    assert endpoint == "http://core/internal/v1/data/events"
    assert payload["event_id"] == event.event_id
    assert payload["event_version"] == "1.0"
    assert headers["authorization"] == "Bearer data-event-token"
    assert headers["idempotency-key"] == event.event_id
    assert headers["x-scenara-tenant-id"] == event.tenant_id
    assert outbox.undelivered() == []
