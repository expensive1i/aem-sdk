from __future__ import annotations

import builtins
import time
from typing import TYPE_CHECKING, Any

from ..types import Execution, Export, Notebook

if TYPE_CHECKING:
    from .._http import HTTPClient
    from .datasets import Datasets
    from .models import Models


class Notebooks:
    """Run your code next to the data, inside a sealed AEM sandbox."""

    def __init__(self, http: HTTPClient, datasets: Datasets, models: Models) -> None:
        self._http = http
        self._datasets = datasets
        self._models = models

    def list(self) -> builtins.list[Notebook]:
        body = self._http.request("GET", "/notebooks")
        return [Notebook.from_api(n) for n in body.get("notebooks") or []]

    def get(self, notebook_id: str) -> Notebook:
        body = self._http.request("GET", f"/notebooks/{notebook_id}")
        return Notebook.from_api(body.get("notebook") or {})

    def create(
        self,
        title: str,
        *,
        datasets: builtins.list[str] | None = None,
        models: builtins.list[str] | None = None,
        description: str = "",
    ) -> Notebook:
        """Create a notebook with datasets and models attached (names like "owner/name", or ids).

        You can attach datasets you own or have been approved for.
        """
        body = self._http.request(
            "POST",
            "/notebooks",
            json={
                "title": title,
                "description": description,
                "datasetIds": [self._datasets.resolve_id(d) for d in datasets or []],
                "modelIds": [self._models.resolve_id(m) for m in models or []],
            },
        )
        return Notebook.from_api(body.get("notebook") or {})

    def delete(self, notebook_id: str) -> None:
        self._http.request("DELETE", f"/notebooks/{notebook_id}")

    def start(self, notebook_id: str) -> Notebook:
        """Start the notebook's sandbox. Attached datasets are mounted read-only."""
        body = self._http.request("POST", f"/notebooks/{notebook_id}/start")
        return Notebook.from_api(body.get("notebook") or {})

    def stop(self, notebook_id: str) -> None:
        self._http.request("POST", f"/notebooks/{notebook_id}/stop")

    def run(
        self, notebook_id: str, code: str, *, wait: bool = True, timeout: float = 600, poll_interval: float = 1.0
    ) -> Execution:
        """Run Python code in the notebook's sandbox (start it first).

        By default this waits until the code finishes and returns its output.
        Pass wait=False to get the running execution back straight away and check
        it later with execution(). Large outputs are trimmed so raw data can't be
        printed out of the sandbox.
        """
        body = self._http.request("POST", f"/notebooks/{notebook_id}/execute", json={"code": code})
        execution = Execution.from_api(body.get("execution") or {})
        if not wait:
            return execution
        deadline = time.monotonic() + timeout
        while not execution.done:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"The code was still running after {timeout:.0f}s. It keeps running in AEM; "
                    f"check it with client.notebooks.execution({notebook_id!r}, {execution.id!r})."
                )
            time.sleep(poll_interval)
            execution = self.execution(notebook_id, execution.id)
        return execution

    def execution(self, notebook_id: str, execution_id: str) -> Execution:
        body = self._http.request("GET", f"/notebooks/{notebook_id}/executions/{execution_id}")
        return Execution.from_api(body.get("execution") or {})

    def interrupt(self, notebook_id: str) -> None:
        """Stop the code that's running right now (the sandbox keeps running)."""
        self._http.request("POST", f"/notebooks/{notebook_id}/interrupt")

    def outputs(self, notebook_id: str) -> builtins.list[dict[str, Any]]:
        """Files saved to /outputs with aem.save_model(), ready to export."""
        body = self._http.request("GET", f"/notebooks/{notebook_id}/outputs")
        return list(body.get("files") or [])

    def request_export(self, notebook_id: str, file_name: str) -> Export:
        """Ask to take a saved model out of the sandbox. Each dataset owner approves it first."""
        body = self._http.request("POST", f"/notebooks/{notebook_id}/exports", json={"fileName": file_name})
        return Export.from_api(body.get("export") or {})
