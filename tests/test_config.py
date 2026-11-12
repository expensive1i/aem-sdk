from __future__ import annotations

from pathlib import Path

import pytest

import aem
from aem import _config


def test_explicit_key_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AEM_API_KEY", "aem_sk_from_env")
    assert _config.resolve_api_key("aem_sk_explicit") == "aem_sk_explicit"


def test_key_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AEM_API_KEY", "aem_sk_from_env")
    assert _config.resolve_api_key(None) == "aem_sk_from_env"


@pytest.mark.parametrize("content", ["aem_sk_from_file\n", "# my key\napi_key = 'aem_sk_from_file'\n"])
def test_key_from_credentials_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, content: str) -> None:
    creds = tmp_path / "credentials"
    creds.write_text(content, encoding="utf-8")
    monkeypatch.setattr(_config, "CREDENTIALS_FILE", creds)
    assert _config.resolve_api_key(None) == "aem_sk_from_file"


def test_missing_key_explains_what_to_do() -> None:
    with pytest.raises(aem.ConfigurationError, match="API Keys page"):
        aem.Client()


def test_rejects_something_that_is_not_an_aem_key() -> None:
    with pytest.raises(aem.ConfigurationError, match="aem_sk_"):
        aem.Client(api_key="sk-openai-something")


def test_repr_never_shows_the_full_key() -> None:
    client = aem.Client(api_key="aem_sk_0123456789abcdef")
    assert "0123456789abcdef" not in repr(client)


def test_base_url_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AEM_BASE_URL", "http://localhost:3000/api/")
    assert aem.Client(api_key="aem_sk_x").base_url == "http://localhost:3000/api"
