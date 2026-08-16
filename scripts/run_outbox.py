from __future__ import annotations

import logging
import signal
from threading import Event

from scenara_data.api.container import build_container
from scenara_data.config import load_settings

LOGGER = logging.getLogger("scenara_data.outbox_worker")


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    settings = load_settings()
    if settings.runtime_mode != "postgres":
        raise RuntimeError("the standalone Outbox worker requires postgres runtime mode")
    if not settings.core_event_endpoint or not settings.core_event_token:
        raise RuntimeError("Core event endpoint and token are required for the Outbox worker")
    container = build_container(settings)
    stopped = Event()

    def stop(_: int, __: object) -> None:
        stopped.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    LOGGER.info("outbox worker started")
    while not stopped.is_set():
        summary = container.dispatcher.dispatch_once()
        if summary.has_work:
            LOGGER.info(
                "outbox batch claimed=%s delivered=%s failed=%s dead_lettered=%s",
                summary.claimed,
                summary.delivered,
                summary.failed,
                summary.dead_lettered,
            )
        stopped.wait(0.2 if summary.has_work else 1.0)
    LOGGER.info("outbox worker stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
