"""Cross-platform compatibility shims.

On Windows, the default ``ProactorEventLoop`` deserialises asyncpg socket
cleanup poorly when an event loop dies and a new one is created — connections
created on the dead loop blow up with ``'NoneType' has no attribute 'send'``
during teardown. This affects any process that calls ``asyncio.run()`` more
than once over its lifetime (workers consuming successive RQ jobs, the
drop-folder watcher firing on each new file, the test suite, etc.).

The fix is to use the ``SelectorEventLoop``, which doesn't suffer from the
same teardown ordering issue. asyncpg supports both loop types.

Call ``apply_windows_event_loop_policy()`` at process entry — once is enough
for the whole process. Idempotent.
"""
from __future__ import annotations

import asyncio
import sys


def apply_windows_event_loop_policy() -> None:
    if sys.platform != "win32":
        return
    current = asyncio.get_event_loop_policy()
    if isinstance(current, asyncio.WindowsSelectorEventLoopPolicy):
        return
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
