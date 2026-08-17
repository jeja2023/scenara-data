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
        raise RuntimeError("独立 Outbox 工作进程要求使用 PostgreSQL 运行模式")
    if not settings.core_event_endpoint or not settings.core_event_token:
        raise RuntimeError("Outbox 工作进程必须配置 Core 事件端点和令牌")
    container = build_container(settings)
    stopped = Event()

    def stop(_: int, __: object) -> None:
        stopped.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    LOGGER.info("Outbox 工作进程已启动")
    while not stopped.is_set():
        summary = container.dispatcher.dispatch_once()
        if summary.has_work:
            LOGGER.info(
                "Outbox 批次：已领取=%s，已投递=%s，失败=%s，进入死信=%s",
                summary.claimed,
                summary.delivered,
                summary.failed,
                summary.dead_lettered,
            )
        stopped.wait(0.2 if summary.has_work else 1.0)
    LOGGER.info("Outbox 工作进程已停止")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
