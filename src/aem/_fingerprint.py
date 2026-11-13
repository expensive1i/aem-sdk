"""A quick file fingerprint, to spot the same file being published twice.

SHA-256 of "<size>\\n" + the first MiB + the last MiB. It must stay identical
to go-aem's internal/dataset/fingerprint.go and the website's
src/lib/fileFingerprint.ts, so all three recognise the same file.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

_MIB = 1 << 20


def file_fingerprint(path: str | os.PathLike[str]) -> str:
    file = Path(path)
    size = file.stat().st_size
    digest = hashlib.sha256(f"{size}\n".encode())
    with open(file, "rb") as f:
        digest.update(f.read(min(size, _MIB)))
        f.seek(max(0, size - _MIB))
        digest.update(f.read())
    return digest.hexdigest()
