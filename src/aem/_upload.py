"""Uploading files to AEM: datasets to publish, and competition predictions.

AEM decides how a file is sent. With Azure storage it hands out a short-lived
upload link and the file goes straight to storage: in one request up to
32 MB, otherwise in 8 MB blocks that are retried on failure and then joined.
Without Azure the file is streamed to the API. Either way the result is an
upload ID that the publish or submit call then uses.
"""

from __future__ import annotations

import base64
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote
from xml.sax.saxutils import escape

import httpx

from .errors import AEMError, APIConnectionError

if TYPE_CHECKING:
    from ._http import HTTPClient

#: Called with (bytes sent, total bytes) as the upload goes.
ProgressCallback = Callable[[int, int], None]

SINGLE_PUT_MAX = 32 << 20
BLOCK_SIZE = 8 << 20
BLOCK_RETRIES = 4


def print_progress(name: str) -> ProgressCallback:
    """A progress callback that prints "Uploading name: 42%" on one line."""
    last = [-1]

    def show(sent: int, total: int) -> None:
        pct = 100 if total == 0 else int(sent * 100 / total)
        if pct != last[0]:
            last[0] = pct
            end = "\n" if pct >= 100 else ""
            print(f"\rUploading {name}: {pct}%", end=end, file=sys.stderr, flush=True)

    return show


def _resolve(progress: bool | ProgressCallback | None, name: str) -> ProgressCallback | None:
    if progress is True:
        return print_progress(name)
    if callable(progress):
        return progress
    return None


class Uploader:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    def upload(self, path: str | os.PathLike[str], *, kind: str = "data", progress: bool | ProgressCallback | None = None) -> str:
        """Upload a file and return its upload ID. `kind` is "data" or "model"."""
        file = Path(path)
        if not file.is_file():
            raise AEMError(f"No file at {file}.")
        size = file.stat().st_size
        if size == 0:
            raise AEMError(f"{file.name} is empty.")
        report = _resolve(progress, file.name)

        init = self._http.request("POST", "/datasets/upload/init", json={"fileName": file.name, "fileSize": size, "kind": kind})
        upload_id = str(init.get("uploadId") or "")
        if not upload_id:
            raise AEMError("AEM didn't start the upload. Please try again.")

        if init.get("strategy") == "direct" and init.get("uploadUrl"):
            _upload_to_azure(str(init["uploadUrl"]), file, size, report)
        else:
            self._http.upload_file(f"/datasets/upload/stream?uploadId={upload_id}", file, size, report)
        return upload_id


def _block_id(i: int) -> str:
    # Azure needs base64 IDs of equal length for every block (same as the website).
    return base64.b64encode(f"block-{i:06d}".encode()).decode()


def _azure_put(client: httpx.Client, url: str, content: Any, headers: dict[str, str]) -> None:
    for attempt in range(BLOCK_RETRIES + 1):
        try:
            response = client.put(url, content=content() if callable(content) else content, headers=headers)
        except httpx.TransportError as exc:
            if attempt >= BLOCK_RETRIES:
                raise APIConnectionError(f"Upload interrupted: {exc}") from exc
        else:
            if response.status_code < 300:
                return
            if response.status_code not in (408, 429, 500, 502, 503, 504) or attempt >= BLOCK_RETRIES:
                raise AEMError(f"Upload to storage failed (HTTP {response.status_code}). Please try again.")
        time.sleep(0.5 * 2**attempt)


def _upload_to_azure(url: str, file: Path, size: int, report: ProgressCallback | None) -> None:
    sent = [0]

    def advance(n: int) -> None:
        sent[0] += n
        if report:
            report(min(sent[0], size), size)

    # No AEM auth header here: the link itself grants write access to one blob.
    with httpx.Client(timeout=httpx.Timeout(60.0, write=300.0)) as azure, open(file, "rb") as f:
        if size <= SINGLE_PUT_MAX:
            data = f.read()
            _azure_put(azure, url, data, {"x-ms-blob-type": "BlockBlob", "Content-Type": "application/octet-stream"})
            advance(size)
            return

        join = "&" if "?" in url else "?"
        count = (size + BLOCK_SIZE - 1) // BLOCK_SIZE
        for i in range(count):
            f.seek(i * BLOCK_SIZE)
            block = f.read(BLOCK_SIZE)
            _azure_put(azure, f"{url}{join}comp=block&blockid={quote(_block_id(i), safe='')}", block, {})
            advance(len(block))
        blocks = "".join(f"<Latest>{escape(_block_id(i))}</Latest>" for i in range(count))
        body = f'<?xml version="1.0" encoding="utf-8"?><BlockList>{blocks}</BlockList>'
        _azure_put(azure, f"{url}{join}comp=blocklist", body.encode(), {"Content-Type": "application/xml"})
