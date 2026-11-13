from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .._fingerprint import file_fingerprint
from .._upload import ProgressCallback, Uploader
from ..errors import AEMError, DuplicateFileError, NotFoundError
from ..types import AccessRequest, Column, Dataset, Preview

if TYPE_CHECKING:
    from .._http import HTTPClient

_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


class Datasets:
    """Find datasets and ask for access. The rows themselves stay inside AEM."""

    def __init__(self, http: HTTPClient, uploader: Uploader | None = None) -> None:
        self._http = http
        self._uploader = uploader or Uploader(http)

    def search(
        self,
        query: str | None = None,
        *,
        category: str | None = None,
        access: str | None = None,
        sort: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Dataset]:
        """Search the marketplace. `access` is "open" or "restricted"; `sort` is "popular" or "newest"."""
        body = self._http.request(
            "GET",
            "/datasets",
            params={"search": query, "category": category, "access": access, "sort": sort, "limit": limit, "offset": offset},
        )
        return [Dataset.from_api(d) for d in body.get("datasets") or []]

    def mine(self, *, limit: int = 50) -> list[Dataset]:
        """Datasets you published."""
        body = self._http.request("GET", "/datasets", params={"owner": "me", "limit": limit})
        return [Dataset.from_api(d) for d in body.get("datasets") or []]

    def accessible(self) -> list[Dataset]:
        """Datasets you can attach to a notebook: your own and those you've been approved for."""
        body = self._http.request("GET", "/datasets/accessible")
        return [Dataset.from_api(d) for d in body.get("datasets") or []]

    def get(self, dataset: str) -> Dataset:
        """One dataset, by name ("owner/name") or id, including its schema and your access."""
        dataset_id = self.resolve_id(dataset)
        body = self._http.request("GET", f"/datasets/{dataset_id}")
        return Dataset.from_api(body.get("dataset") or {}, body.get("viewer"))

    def schema(self, dataset: str) -> list[Column]:
        """The dataset's columns and their types."""
        return self.get(dataset).columns

    def preview(self, dataset: str) -> Preview:
        """A few sample rows. Only open datasets have previews."""
        body = self._http.request("GET", f"/datasets/{self.resolve_id(dataset)}/preview")
        return Preview(columns=list(body.get("columns") or []), rows=list(body.get("rows") or []))

    def request_access(self, dataset: str, purpose: str = "") -> AccessRequest:
        """Ask the owner for access. Say what you'll use the data for; owners decide in the dashboard."""
        body = self._http.request("POST", f"/datasets/{self.resolve_id(dataset)}/access", json={"purpose": purpose})
        return AccessRequest.from_api(body.get("access") or {})

    def access_status(self, dataset: str) -> str:
        """Your access: "owner", "approved", "pending", "rejected" or "none"."""
        return self.get(dataset).your_access or "none"

    def publish(
        self,
        path: str | os.PathLike[str],
        *,
        name: str,
        description: str,
        category: str,
        org: str | None = None,
        full_name: str | None = None,
        tags: list[str] | None = None,
        access: str = "restricted",
        price: str | None = None,
        allow_duplicate: bool = False,
        wait: bool = True,
        timeout: float = 900.0,
        progress: bool | ProgressCallback | None = True,
    ) -> Dataset:
        """Publish a CSV or Parquet file as a dataset on AEM.

        ``name`` looks like "your-org/dataset-name". ``access`` is "restricted"
        (you approve each builder, the default) or "open". The rows never leave
        AEM: builders train on them inside sealed notebooks.

        Publishing the exact same file twice raises :class:`aem.DuplicateFileError`
        unless ``allow_duplicate=True``. With ``wait=True`` (default) this returns
        once AEM has read the file's columns and row count.
        """
        file = Path(path)
        if file.suffix.lower() not in (".csv", ".parquet", ".pq"):
            raise AEMError("Datasets must be .csv or .parquet files.")
        if access not in ("restricted", "open"):
            raise AEMError('access must be "restricted" or "open".')
        if not file.is_file():
            raise AEMError(f"No file at {file}.")

        if not allow_duplicate:
            body = self._http.request("POST", "/datasets/duplicate-check", json={"fingerprint": file_fingerprint(file)})
            dup = body.get("duplicate")
            if dup:
                raise DuplicateFileError(
                    f"You already published this file as {dup.get('name')!r}. "
                    "Pass allow_duplicate=True to publish it again anyway.",
                    existing_id=str(dup.get("id", "")),
                    existing_name=str(dup.get("name", "")),
                )

        upload_id = self._uploader.upload(file, kind="data", progress=progress)
        owner = name.split("/", 1)[0] if "/" in name else ""
        body = self._http.request(
            "POST",
            "/datasets/upload/complete",
            json={
                "uploadId": upload_id,
                "name": name,
                "fullName": full_name or "",
                "org": org or owner,
                "description": description,
                "category": category,
                "tags": list(tags or []),
                "price": price or "",
                "access": access,
            },
        )
        dataset = Dataset.from_api(body.get("dataset") or {})
        if not wait:
            return dataset
        return self.wait_until_ready(dataset.id, timeout=timeout)

    def wait_until_ready(self, dataset: str, *, timeout: float = 900.0, poll: float = 3.0) -> Dataset:
        """Wait while AEM reads a newly published file, then return the dataset."""
        deadline = time.monotonic() + timeout
        while True:
            body = self._http.request("GET", f"/datasets/{self.resolve_id(dataset)}")
            current = Dataset.from_api(body.get("dataset") or {}, body.get("viewer"))
            if current.status == "ready":
                return current
            if current.status == "failed":
                reason = (body.get("dataset") or {}).get("statusMessage") or "the file couldn't be read"
                raise AEMError(f"AEM couldn't process {current.name}: {reason}")
            if time.monotonic() > deadline:
                raise AEMError(
                    f"{current.name} is still being processed. Check it later with client.datasets.get({current.id!r})."
                )
            time.sleep(poll)

    def resolve_id(self, dataset: str) -> str:
        """The id for a dataset name such as "aem-demo/malaria-visits" (ids pass straight through)."""
        if _ID.match(dataset):
            return dataset
        for candidate in self.search(dataset, limit=50):
            if candidate.name == dataset:
                return candidate.id
        raise NotFoundError(
            f"No dataset named {dataset!r}. Check the name in the Data Marketplace (it looks like 'owner/name').",
            status_code=404,
            code="not_found",
        )
