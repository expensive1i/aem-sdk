from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

import aem

from .conftest import Handler, reply

DS_ID = "11111111-2222-3333-4444-555555555555"
DATASET = {
    "id": DS_ID,
    "name": "aem-demo/malaria-visits",
    "org": "AEM-DEMO",
    "accessTier": "restricted",
    "rowCount": 20000,
    "sizeBytes": 1300000,
    "tags": "Health, Malaria",
    "columns": [{"name": "age", "type": "int", "desc": "Age in years"}],
    "createdAt": "2026-10-01T10:00:00Z",
}

MakeClient = Callable[..., aem.Client]


def test_sends_the_api_key_and_a_user_agent(make_client: MakeClient) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return reply(body={"user": {"id": "u1", "email": "demo@aem.local"}})

    user = make_client(handler).whoami()
    assert user.email == "demo@aem.local"
    assert seen["authorization"] == "Bearer aem_sk_test"
    assert seen["user-agent"].startswith(f"aem-sdk/{aem.__version__}")


def test_search_maps_results_and_skips_empty_params(make_client: MakeClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/datasets"
        assert dict(request.url.params) == {"search": "malaria", "limit": "20", "offset": "0"}
        return reply(body={"datasets": [DATASET], "total": 1})

    [ds] = make_client(handler).datasets.search("malaria")
    assert ds.name == "aem-demo/malaria-visits"
    assert ds.row_count == 20000
    assert ds.tags == ["Health", "Malaria"]
    assert not ds.is_open
    assert ds.created_at is not None and ds.created_at.year == 2026


def test_get_by_name_resolves_the_id_and_reports_access(make_client: MakeClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/datasets":
            return reply(body={"datasets": [{**DATASET, "name": "aem-demo/other", "id": "x"}, DATASET]})
        assert request.url.path == f"/api/datasets/{DS_ID}"
        return reply(body={"dataset": DATASET, "viewer": {"isOwner": False, "access": "pending"}})

    client = make_client(handler)
    ds = client.datasets.get("aem-demo/malaria-visits")
    assert ds.id == DS_ID
    assert ds.your_access == "pending"
    assert [c.name for c in ds.columns] == ["age"]


def test_unknown_dataset_name_is_a_clear_not_found(make_client: MakeClient) -> None:
    client = make_client(lambda request: reply(body={"datasets": []}))
    with pytest.raises(aem.NotFoundError, match="owner/name"):
        client.datasets.get("nobody/nothing")


def test_request_access_sends_the_purpose(make_client: MakeClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST" and request.url.path == f"/api/datasets/{DS_ID}/access"
        assert json.loads(request.content) == {"purpose": "malaria model"}
        return reply(body={"access": {"id": "a1", "datasetId": DS_ID, "status": "pending", "purpose": "malaria model"}})

    access = make_client(handler).datasets.request_access(DS_ID, purpose="malaria model")
    assert access.status == "pending"


@pytest.mark.parametrize(
    ("status", "body", "error"),
    [
        (401, {"error": "Invalid or revoked API key", "code": "invalid_token"}, aem.AuthenticationError),
        (403, {"error": "Only open datasets", "code": "preview_unavailable"}, aem.PreviewUnavailableError),
        (403, {"error": "Dashboard only", "code": "session_required"}, aem.SessionRequiredError),
        (403, {"error": "Not yours", "code": "forbidden"}, aem.PermissionDeniedError),
        (404, {"error": "Dataset not found", "code": "not_found"}, aem.NotFoundError),
        (409, {"error": "Already decided"}, aem.ConflictError),
        (400, {"error": "bad"}, aem.BadRequestError),
    ],
)
def test_errors_become_specific_exceptions(
    make_client: MakeClient, status: int, body: dict[str, Any], error: type[Exception]
) -> None:
    client = make_client(lambda request: reply(status, body))
    with pytest.raises(error) as info:
        client.datasets.preview(DS_ID)
    assert isinstance(info.value, aem.APIError)
    assert info.value.status_code == status


def test_revoked_key_message_says_what_to_do(make_client: MakeClient) -> None:
    client = make_client(lambda request: reply(401, {"error": "Invalid or revoked API key", "code": "invalid_token"}))
    with pytest.raises(aem.AuthenticationError, match="API Keys page"):
        client.whoami()


def test_retries_passing_failures_then_succeeds(make_client: MakeClient) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return reply(503, {"error": "busy", "code": "unavailable"})
        return reply(body={"user": {"id": "u1", "email": "a@b.c"}})

    assert make_client(handler).whoami().email == "a@b.c"
    assert calls["n"] == 3


def test_gives_up_after_max_retries(make_client: MakeClient) -> None:
    client = make_client(lambda request: reply(503, {"error": "busy"}), max_retries=1)
    with pytest.raises(aem.ServerError):
        client.whoami()


def test_switched_off_notebooks_fail_fast_with_a_clear_error(make_client: MakeClient) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return reply(503, {"error": "Notebooks can't run code on this server yet.", "code": "sandbox_unavailable"})

    with pytest.raises(aem.SandboxUnavailableError, match="can't run code") as info:
        make_client(handler, max_retries=3).whoami()
    assert isinstance(info.value, aem.ServerError)
    assert calls["n"] == 1  # not retried: waiting won't switch notebooks on


def test_network_failure_is_a_connection_error(make_client: MakeClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(aem.APIConnectionError):
        make_client(handler).whoami()


def test_run_waits_for_the_code_to_finish(make_client: MakeClient) -> None:
    polls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            assert json.loads(request.content) == {"code": "print(1)"}
            return reply(202, {"execution": {"id": "e1", "status": "running", "outputs": []}})
        polls["n"] += 1
        status = "ok" if polls["n"] >= 2 else "running"
        return reply(
            body={"execution": {"id": "e1", "status": status, "outputs": [{"type": "stream", "name": "stdout", "text": "1\n"}]}}
        )

    result = make_client(handler).notebooks.run("nb1", "print(1)", poll_interval=0)
    assert result.ok and result.text == "1\n"
    assert polls["n"] == 2


def test_create_notebook_resolves_dataset_names(make_client: MakeClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/datasets":
            return reply(body={"datasets": [DATASET]})
        body = json.loads(request.content)
        assert body["datasetIds"] == [DS_ID] and body["title"] == "Malaria"
        return reply(201, {"notebook": {"id": "nb1", "title": "Malaria", "status": "stopped", "datasetIds": [DS_ID]}})

    nb = make_client(handler).notebooks.create("Malaria", datasets=["aem-demo/malaria-visits"])
    assert nb.id == "nb1" and not nb.is_running


def test_download_checks_the_checksum(make_client: MakeClient, tmp_path: Path) -> None:
    payload = b"model-bytes"
    digest = hashlib.sha256(payload).hexdigest()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/exports":
            return reply(body={"exports": [{"id": "x1", "fileName": "m.onnx", "status": "approved", "sha256": digest}]})
        return httpx.Response(
            200, content=payload, headers={"content-type": "application/octet-stream", "x-content-sha256": digest}
        )

    path = make_client(handler).exports.download("x1", tmp_path)
    assert path == tmp_path / "m.onnx" and path.read_bytes() == payload


def test_download_rejects_a_corrupted_file(make_client: MakeClient, tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/exports":
            return reply(body={"exports": [{"id": "x1", "fileName": "m.onnx", "status": "approved", "sha256": "0" * 64}]})
        return httpx.Response(200, content=b"tampered", headers={"content-type": "application/octet-stream"})

    with pytest.raises(aem.AEMError, match="checksum"):
        make_client(handler).exports.download("x1", tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_client_works_as_a_context_manager(make_client: MakeClient) -> None:
    handler: Handler = lambda request: reply(body={"user": {"id": "u1"}})
    with make_client(handler) as client:
        assert client.whoami().id == "u1"
