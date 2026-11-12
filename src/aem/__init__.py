"""aem-sdk: the official Python library for AEM, the Africa Entelligence Marketplace.

From your own computer::

    import aem
    client = aem.Client()                      # reads AEM_API_KEY
    client.datasets.search("malaria")

Inside an AEM notebook::

    import aem
    df = aem.load_data("aem-demo/malaria-visits")
    aem.save_model(model, "malaria-risk")
"""

from ._version import __version__
from .client import Client
from .errors import (
    AEMError,
    APIConnectionError,
    APIError,
    AuthenticationError,
    BadRequestError,
    ConfigurationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    PreviewUnavailableError,
    RateLimitError,
    SandboxOnlyError,
    SandboxUnavailableError,
    ServerError,
    SessionRequiredError,
)
from .sandbox import in_sandbox, list_datasets, list_models, load_data, model_path, save_model

__all__ = [
    "AEMError",
    "APIConnectionError",
    "APIError",
    "AuthenticationError",
    "BadRequestError",
    "Client",
    "ConfigurationError",
    "ConflictError",
    "NotFoundError",
    "PermissionDeniedError",
    "PreviewUnavailableError",
    "RateLimitError",
    "SandboxOnlyError",
    "SandboxUnavailableError",
    "ServerError",
    "SessionRequiredError",
    "__version__",
    "in_sandbox",
    "list_datasets",
    "list_models",
    "load_data",
    "model_path",
    "save_model",
]
