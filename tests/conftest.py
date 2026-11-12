from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

import aem

Handler = Callable[[httpx.Request], httpx.Response]


def reply(status: int = 200, body: Any = None, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(
        status,
        content=json.dumps(body if body is not None else {}).encode(),
        headers={"content-type": "application/json", **(headers or {})},
    )


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """Tests never read the developer's real key, address or credentials file."""
    monkeypatch.delenv("AEM_API_KEY", raising=False)
    monkeypatch.delenv("AEM_BASE_URL", raising=False)
    monkeypatch.setattr("aem._config.CREDENTIALS_FILE", tmp_path / "no-credentials")
    monkeypatch.setattr("aem._http.time.sleep", lambda _s: None)  # no real waiting on retries


@pytest.fixture
def make_client() -> Callable[[Handler], aem.Client]:
    def _make(handler: Handler, **kwargs: Any) -> aem.Client:
        return aem.Client(
            api_key="aem_sk_test", base_url="https://aem.test/api", transport=httpx.MockTransport(handler), **kwargs
        )

    return _make
