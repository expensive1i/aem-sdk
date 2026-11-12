"""Where the client finds its API key and AEM's address."""

from __future__ import annotations

import os
from pathlib import Path

from .errors import ConfigurationError

# The AEM website's API. Requests go through the website, which passes an API
# key on to the backend. Override with AEM_BASE_URL (e.g. for local testing:
# http://localhost:3000/api).
DEFAULT_BASE_URL = "https://marketplace.entelligence.africa/api"

KEY_PREFIX = "aem_sk_"
CREDENTIALS_FILE = Path.home() / ".aem" / "credentials"


def resolve_api_key(explicit: str | None) -> str:
    """The API key, from (in order) the argument, AEM_API_KEY, or ~/.aem/credentials."""
    key = explicit or os.environ.get("AEM_API_KEY") or _read_credentials_file()
    if not key:
        raise ConfigurationError(
            "No AEM API key found. Create one on the API Keys page of the AEM dashboard, then either "
            "pass it as aem.Client(api_key='aem_sk_...') or set the AEM_API_KEY environment variable."
        )
    key = key.strip()
    if not key.startswith(KEY_PREFIX):
        raise ConfigurationError(
            f"That doesn't look like an AEM API key (they start with '{KEY_PREFIX}'). "
            "Copy the full key from the API Keys page of the AEM dashboard."
        )
    return key


def resolve_base_url(explicit: str | None) -> str:
    return (explicit or os.environ.get("AEM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def mask(key: str) -> str:
    """Show only the start of a key, e.g. in error messages and repr()."""
    return key[: len(KEY_PREFIX) + 4] + "..."


def _read_credentials_file() -> str | None:
    """Reads ~/.aem/credentials: either just the key, or a line 'api_key = aem_sk_...'."""
    try:
        text = CREDENTIALS_FILE.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            name, _, value = line.partition("=")
            if name.strip() == "api_key":
                return value.strip().strip("\"'")
            continue
        return line
    return None
