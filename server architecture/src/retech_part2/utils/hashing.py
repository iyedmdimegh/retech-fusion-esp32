from __future__ import annotations

import hashlib
from pathlib import Path

_BUFFER_SIZE = 1024 * 1024  # 1 MiB


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_BUFFER_SIZE):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
