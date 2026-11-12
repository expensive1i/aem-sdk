from __future__ import annotations

from types import TracebackType
from typing import TYPE_CHECKING

import httpx

from ._config import mask, resolve_api_key, resolve_base_url
from ._http import HTTPClient
from .resources import Datasets, Exports, Models, Notebooks
from .types import User

__all__ = ["Client"]

if TYPE_CHECKING:
    from typing_extensions import Self  # type-checking only; not needed at runtime


class Client:
    """Talk to AEM from your own code.

    >>> import aem
    >>> client = aem.Client()            # reads AEM_API_KEY
    >>> client.datasets.search("malaria")

    The API key is read from, in order: the ``api_key`` argument, the
    ``AEM_API_KEY`` environment variable, or ``~/.aem/credentials``.
    Restricted data never leaves AEM: run your code next to it with
    ``client.notebooks``, and download only approved results with ``client.exports``.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = resolve_api_key(api_key)
        self.base_url = resolve_base_url(base_url)
        self._http = HTTPClient(
            base_url=self.base_url, api_key=self._api_key, timeout=timeout, max_retries=max_retries, transport=transport
        )
        self.datasets = Datasets(self._http)
        self.models = Models(self._http)
        self.notebooks = Notebooks(self._http, self.datasets, self.models)
        self.exports = Exports(self._http)

    def whoami(self) -> User:
        """The account this API key belongs to."""
        body = self._http.request("GET", "/auth/me")
        return User.from_api(body.get("user") or {})

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"aem.Client(base_url={self.base_url!r}, api_key={mask(self._api_key)!r})"
