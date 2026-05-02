"""Drop-folder watcher.

Watches ``inbox/xlsx/`` and ``inbox/pdf/`` for new files. On creation:
  1. wait for the file to stabilise (avoid acting while it's still being written),
  2. SHA-256 it,
  3. dedup against `meta.ingestion_jobs` and enqueue an RQ task
     (delegated to :mod:`retech_part2.workers.enqueue`).

Observer choice — Windows + WSL2:
The default :class:`watchdog.observers.Observer` uses ReadDirectoryChangesW on
Windows and inotify on Linux. Both are unreliable on Windows-mounted volumes
and WSL2's 9P/CIFS mounts — events sometimes never fire. We detect those
environments and fall back to :class:`PollingObserver`, which scans the
directory at a fixed interval and always works (at the cost of latency).
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from watchdog.events import FileCreatedEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

from retech_part2._compat import apply_windows_event_loop_policy
from retech_part2.config import get_settings
from retech_part2.db import reset_db_cache_for_new_loop
from retech_part2.logging import configure_logging, get_logger
from retech_part2.utils.files import ensure_dir
from retech_part2.utils.hashing import sha256_file
from retech_part2.workers.enqueue import (
    EXT_TO_JOB_TYPE,
    UnsupportedExtension,
    enqueue_file,
)

log = get_logger("watcher")

STABILITY_MAX_ATTEMPTS = 30
STABILITY_DELAY_SECONDS = 0.5
POLLING_INTERVAL_SECONDS = 2.0


def _is_windows_or_wsl() -> bool:
    """Detect environments where the native FS watcher is flaky."""
    if sys.platform == "win32":
        return True
    # WSL detection via /proc/version
    try:
        with open("/proc/version", "r", encoding="utf-8") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def _wait_for_stable(path: Path) -> bool:
    """Poll the file size until it stops changing. Returns True if stable."""
    last_size = -1
    for _ in range(STABILITY_MAX_ATTEMPTS):
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            return False
        if size > 0 and size == last_size:
            return True
        last_size = size
        time.sleep(STABILITY_DELAY_SECONDS)
    return last_size > 0  # accept whatever we have if writer is super slow


class _InboxHandler(FileSystemEventHandler):
    def __init__(self) -> None:
        super().__init__()
        # Track files we've already processed (during this watcher session).
        # File-hash dedup in the DB is the durable check; this is just to
        # avoid re-acting on watchdog's occasional duplicate events for the
        # same path.
        self._seen_paths: set[str] = set()

    def on_created(self, event: FileCreatedEvent) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        ext = path.suffix.lower()
        if ext not in EXT_TO_JOB_TYPE:
            log.debug("watcher_ignored_ext", path=str(path), ext=ext)
            return
        key = str(path.resolve())
        if key in self._seen_paths:
            return
        self._seen_paths.add(key)

        log.info("watcher_event_received", path=str(path))
        if not _wait_for_stable(path):
            log.warning("watcher_file_disappeared_or_empty", path=str(path))
            self._seen_paths.discard(key)
            return

        # Hash + enqueue. Run inside a sync wrapper since we're in a watchdog
        # worker thread, not an event loop.
        try:
            import asyncio
            file_hash = sha256_file(path)
            reset_db_cache_for_new_loop()
            result = asyncio.run(enqueue_file(path, file_hash=file_hash))
            log.info(
                "watcher_enqueued",
                path=str(path),
                job_id=str(result.job_id),
                deduped=result.deduped,
                status=result.status,
            )
        except UnsupportedExtension as e:
            log.warning("watcher_unsupported", path=str(path), error=str(e))
        except Exception as e:
            log.exception("watcher_enqueue_failed", path=str(path), error=str(e))
            # Drop from seen so the next event has a chance to retry.
            self._seen_paths.discard(key)


def _make_observer() -> Observer | PollingObserver:
    if _is_windows_or_wsl():
        log.info(
            "watcher_polling_observer_selected",
            reason="windows or WSL detected; native FS watcher is unreliable on these mounts",
            interval_s=POLLING_INTERVAL_SECONDS,
        )
        return PollingObserver(timeout=POLLING_INTERVAL_SECONDS)
    log.info("watcher_native_observer_selected")
    return Observer()


def main() -> None:
    apply_windows_event_loop_policy()
    configure_logging()
    settings = get_settings()

    xlsx_dir = ensure_dir(settings.inbox_xlsx_path)
    pdf_dir = ensure_dir(settings.inbox_pdf_path)

    handler = _InboxHandler()
    observer = _make_observer()
    observer.schedule(handler, str(xlsx_dir), recursive=False)
    observer.schedule(handler, str(pdf_dir), recursive=False)
    observer.start()
    log.info(
        "watcher_started",
        xlsx_dir=str(xlsx_dir),
        pdf_dir=str(pdf_dir),
        observer=type(observer).__name__,
        pid=os.getpid(),
    )

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("watcher_stopping")
        observer.stop()
    observer.join()
    log.info("watcher_stopped")


if __name__ == "__main__":
    main()
