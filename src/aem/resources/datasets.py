from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..errors import NotFoundError
from ..types import AccessRequest, Column, Dataset, Preview

if TYPE_CHECKING:
    from .._http import HTTPClient

_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


class Datasets:
    """Find datasets and ask for access. The rows themselves stay inside AEM."""

    def __init__(self, http: HTTPClient) -> None:
        self._http = http

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
