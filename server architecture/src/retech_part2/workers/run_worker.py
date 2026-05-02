"""Entry point for the RQ worker. Wired to settings-derived Redis URL.

Picks SimpleWorker on Windows (no `os.fork`), regular Worker elsewhere.
SimpleWorker runs each job in the main process — fine for our hackathon
workload, just means a hang in one task blocks the queue (vs. a forked
worker which would isolate that).
"""
from __future__ import annotations

import sys

from redis import Redis
from rq import Queue, SimpleWorker, Worker

from retech_part2._compat import apply_windows_event_loop_policy
from retech_part2.config import get_settings
from retech_part2.logging import configure_logging, get_logger


def main() -> None:
    apply_windows_event_loop_policy()
    configure_logging()
    log = get_logger("worker")
    settings = get_settings()

    connection = Redis.from_url(settings.redis_url)
    queues = [Queue("default", connection=connection)]

    worker_cls = SimpleWorker if sys.platform == "win32" else Worker
    log.info(
        "worker_starting",
        redis_url=settings.redis_url,
        queues=[q.name for q in queues],
        worker_class=worker_cls.__name__,
    )
    worker_cls(queues, connection=connection).work(with_scheduler=False)


if __name__ == "__main__":
    main()
