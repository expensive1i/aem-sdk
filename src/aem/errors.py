"""Errors raised by aem-sdk.

Every error is an :class:`AEMError`, so ``except aem.AEMError`` catches them all.
API errors carry the HTTP status and AEM's error code (for example
``"invalid_token"``) and a message that says what to do next.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "AEMError",
    "APIConnectionError",
    "APIError",
    "AuthenticationError",
    "BadRequestError",
    "ConfigurationError",
    "ConflictError",
    "DuplicateFileError",
    "NotFoundError",
    "PermissionDeniedError",
    "PreviewUnavailableError",
    "RateLimitError",
    "SandboxOnlyError",
    "SandboxUnavailableError",
    "ServerError",
    "SessionRequiredError",
]


class AEMError(Exception):
    """Base class for every aem-sdk error."""


class ConfigurationError(AEMError):
    """The client is missing something it needs, such as an API key."""


class APIConnectionError(AEMError):
    """AEM couldn't be reached (network problem or timeout)."""


class SandboxOnlyError(AEMError):
    """The call only works inside an AEM notebook, where the data lives."""


class APIError(AEMError):
    """AEM answered with an error."""

    def __init__(self, message: str, *, status_code: int, code: str | None = None, body: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.body = body

    def __str__(self) -> str:
        return self.message

    def __repr__(self) -> str:
        return f"{type(self).__name__}(status_code={self.status_code}, code={self.code!r}, message={self.message!r})"


class AuthenticationError(APIError):
    """401: the API key is missing, invalid or revoked."""


class PermissionDeniedError(APIError):
    """403: you're signed in but not allowed to do this."""


class SessionRequiredError(PermissionDeniedError):
    """403: this action can only be done in the AEM dashboard, not with an API key."""


class PreviewUnavailableError(PermissionDeniedError):
    """403: row previews are only available for open datasets."""


class NotFoundError(APIError):
    """404: the dataset, model, notebook or export doesn't exist (or isn't visible to you)."""


class ConflictError(APIError):
    """409: the request clashes with the current state, e.g. a decision already made."""


class DuplicateFileError(AEMError):
    """You already published this exact file. Pass ``allow_duplicate=True`` to publish it again."""

    def __init__(self, message: str, *, existing_id: str, existing_name: str) -> None:
        super().__init__(message)
        self.existing_id = existing_id
        self.existing_name = existing_name


class BadRequestError(APIError):
    """400 or 422: something in the request is invalid."""


class RateLimitError(APIError):
    """429: too many requests; slow down and try again shortly."""


class ServerError(APIError):
    """5xx: something went wrong on AEM's side."""


class SandboxUnavailableError(ServerError):
    """503: this AEM server can't run notebook code yet. Notebooks can still be created and edited."""


_HINTS = {
    "invalid_token": "Your API key is invalid or has been revoked. Create a new one on the API Keys page of the AEM dashboard.",
    "auth_required": "No API key was sent. Pass api_key=... to aem.Client() or set the AEM_API_KEY environment variable.",
    "session_required": "This can only be done in the AEM dashboard, not with an API key.",
    "preview_unavailable": "Row previews are only available for open datasets. Use the schema, or work with the data in an AEM notebook.",
    "rate_limited": "Too many requests. Wait a moment and try again.",
    "sandbox_unavailable": (
        "Notebooks can't run code on this AEM server yet. You can still create and edit notebooks; "
        "running them will work once notebook hosting is switched on."
    ),
}


def error_from_response(status_code: int, body: Any) -> APIError:
    """Turn an AEM error response into the matching exception."""
    message = ""
    code = None
    if isinstance(body, dict):
        message = str(body.get("error") or body.get("message") or "")
        code = body.get("code")
    # Known codes get a fuller message that says what to do next.
    message = _HINTS.get(code or "", message)
    if not message:
        message = f"AEM returned HTTP {status_code}."

    cls: type[APIError]
    if status_code == 401:
        cls = AuthenticationError
    elif status_code == 403:
        cls = {"session_required": SessionRequiredError, "preview_unavailable": PreviewUnavailableError}.get(
            code or "", PermissionDeniedError
        )
    elif status_code == 404:
        cls = NotFoundError
    elif status_code == 409:
        cls = ConflictError
    elif status_code == 429:
        cls = RateLimitError
    elif status_code in (400, 422):
        cls = BadRequestError
    elif code == "sandbox_unavailable":
        cls = SandboxUnavailableError
    elif status_code >= 500:
        cls = ServerError
    else:
        cls = APIError
    return cls(message, status_code=status_code, code=code, body=body)
