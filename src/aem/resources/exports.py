from __future__ import annotations

import builtins
import hashlib
import os
from pathlib import Path
from typing import TYPE_CHECKING

from ..errors import AEMError, NotFoundError
from ..types import Export

if TYPE_CHECKING:
    from .._http import HTTPClient


class Exports:
    """Trained models leaving the sandbox. Downloadable once every data owner approves."""

    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    def list(self) -> builtins.list[Export]:
        body = self._http.request("GET", "/exports")
        return [Export.from_api(e) for e in body.get("exports") or []]

    def get(self, export_id: str) -> Export:
        for export in self.list():
            if export.id == export_id:
                return export
        raise NotFoundError(f"No export with id {export_id!r}.", status_code=404, code="not_found")

    def download(self, export_id: str, path: str | os.PathLike[str] | None = None) -> Path:
        """Download an approved export. Saves to `path` (a file or a folder), or the current folder.

        The file's SHA-256 is checked against the one AEM recorded when it left the sandbox.
        """
        export = self.get(export_id)
        target = Path(path) if path is not None else Path.cwd()
        if target.is_dir():
            target = target / export.file_name
        partial = target.with_name(target.name + ".part")
        with open(partial, "wb") as f:
            headers = self._http.stream_to_file(f"/exports/{export_id}/download", f)
        expected = headers.get("x-content-sha256") or export.sha256
        if expected and _sha256(partial) != expected.lower():
            partial.unlink(missing_ok=True)
            raise AEMError("The downloaded file doesn't match its recorded checksum. Please try again.")
        partial.replace(target)
        return target


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()
