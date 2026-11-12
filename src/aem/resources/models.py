from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..errors import NotFoundError
from ..types import Model

if TYPE_CHECKING:
    from .._http import HTTPClient

_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


class Models:
    """Find published models. Their weights stay inside AEM; use them from a notebook."""

    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    def search(
        self,
        query: str | None = None,
        *,
        category: str | None = None,
        sort: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Model]:
        body = self._http.request(
            "GET", "/models", params={"search": query, "category": category, "sort": sort, "limit": limit, "offset": offset}
        )
        return [Model.from_api(m) for m in body.get("models") or []]

    def mine(self, *, limit: int = 50) -> list[Model]:
        """Models you published."""
        body = self._http.request("GET", "/models", params={"owner": "me", "limit": limit})
        return [Model.from_api(m) for m in body.get("models") or []]

    def get(self, model: str) -> Model:
        """One model, by name ("owner/name") or id."""
        body = self._http.request("GET", f"/models/{self.resolve_id(model)}")
        return Model.from_api(body.get("model") or {})

    def resolve_id(self, model: str) -> str:
        if _ID.match(model):
            return model
        for candidate in self.search(model, limit=50):
            if candidate.name == model:
                return candidate.id
        raise NotFoundError(
            f"No model named {model!r}. Check the name in the Model Marketplace (it looks like 'owner/name').",
            status_code=404,
            code="not_found",
        )
