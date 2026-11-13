"""The HTTP layer: one connection pool, retries for passing failures, clear errors."""

from __future__ import annotations

import platform
import random
import time
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any, BinaryIO, cast

import httpx

from ._version import __version__
from .errors import APIConnectionError, error_from_response

RETRY_STATUSES = {429, 502, 503, 504}


class HTTPClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float,
        max_retries: int,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.max_retries = max_retries
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            transport=transport,
            headers={
                "Authorization": f"Bearer {api_key}",
                "User-Agent": f"aem-sdk/{__version__} python/{platform.python_version()}",
                "Accept": "application/json",
            },
        )

    def close(self) -> None:
        self._client.close()

    def request(self, method: str, path: str, *, params: dict[str, Any] | None = None, json: Any = None) -> Any:
        """Send a request and return the decoded JSON body, or raise an aem error."""
        response = self._send(method, path, params=params, json=json)
        if not response.content:
            return {}
        return response.json()

    def upload_file(self, path: str, file: Path, size: int, report: Callable[[int, int], None] | None = None) -> Any:
        """Stream a file to the API as multipart form data (used when AEM has no Azure storage)."""
        sent = [0]

        def on_read(n: int) -> None:
            sent[0] += n
            if report:
                report(min(sent[0], size), size)

        try:
            with open(file, "rb") as f:
                response = self._client.post(
                    path,
                    # httpx only calls read() on it, so it stands in for a file.
                    files={"file": (file.name, cast("IO[bytes]", _ProgressReader(f, on_read)), "application/octet-stream")},
                    timeout=httpx.Timeout(60.0, write=None, read=600.0),
                )
        except httpx.TransportError as exc:
            raise APIConnectionError(f"Upload interrupted: {exc}") from exc
        if response.status_code >= 400:
            raise error_from_response(response.status_code, _json_or_none(response))
        return response.json() if response.content else {}

    def stream_to_file(self, path: str, destination: Any) -> httpx.Headers:
        """Download a file response into an open binary file. Returns the response headers."""
        attempt = 0
        while True:
            try:
                with self._client.stream("GET", path) as response:
                    if response.status_code >= 400:
                        response.read()
                        if _retryable(response) and attempt < self.max_retries:
                            attempt += 1
                            time.sleep(_backoff(attempt, response))
                            continue
                        raise error_from_response(response.status_code, _json_or_none(response))
                    for chunk in response.iter_bytes():
                        destination.write(chunk)
                    return response.headers
            except httpx.TransportError as exc:
                if attempt >= self.max_retries:
                    raise APIConnectionError(f"Couldn't reach AEM: {exc}") from exc
                attempt += 1
                time.sleep(_backoff(attempt, None))

    def _send(self, method: str, path: str, *, params: dict[str, Any] | None, json: Any) -> httpx.Response:
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        attempt = 0
        while True:
            try:
                response = self._client.request(method, path, params=clean, json=json)
            except httpx.TransportError as exc:
                if attempt >= self.max_retries:
                    raise APIConnectionError(f"Couldn't reach AEM: {exc}") from exc
                attempt += 1
                time.sleep(_backoff(attempt, None))
                continue

            if _retryable(response) and attempt < self.max_retries:
                attempt += 1
                time.sleep(_backoff(attempt, response))
                continue
            if response.status_code >= 400:
                raise error_from_response(response.status_code, _json_or_none(response))
            return response


def _retryable(response: httpx.Response) -> bool:
    """A passing failure worth retrying. Notebooks being switched off isn't one."""
    if response.status_code not in RETRY_STATUSES:
        return False
    body = _json_or_none(response)
    return not (isinstance(body, dict) and body.get("code") == "sandbox_unavailable")


class _ProgressReader:
    """A file wrapper that reports each read, for upload progress."""

    def __init__(self, f: BinaryIO, on_read: Callable[[int], None]) -> None:
        self._f, self._on_read = f, on_read

    def read(self, n: int = -1) -> bytes:
        chunk = self._f.read(n)
        self._on_read(len(chunk))
        return chunk


def _json_or_none(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def _backoff(attempt: int, response: httpx.Response | None) -> float:
    """Seconds to wait before retry number `attempt`: Retry-After if given, else 0.5s, 1s, 2s... with jitter."""
    if response is not None:
        retry_after = response.headers.get("retry-after")
        if retry_after and retry_after.isdigit():
            return min(float(retry_after), 30.0)
    base = min(0.5 * float(2 ** (attempt - 1)), 8.0)
    return base * (0.75 + random.random() / 2)
