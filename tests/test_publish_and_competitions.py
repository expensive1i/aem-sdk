from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

import aem
from aem._fingerprint import file_fingerprint

from .conftest import reply

MakeClient = Callable[..., aem.Client]
DS = "11111111-2222-3333-4444-555555555555"


def test_fingerprint_matches_the_server_rule(tmp_path: Path) -> None:
    f = tmp_path / "a.csv"
    f.write_bytes(b"plot_id,yield\np1,10\n")
    # Same reference value as go-aem's fingerprint_test.go.
    assert file_fingerprint(f) == "df175694f58ed45d67775133b6285083d9f897854a4924055a374ca3f2f41bd2"


def test_publish_uploads_completes_and_waits(make_client: MakeClient, tmp_path: Path) -> None:
    f = tmp_path / "crops.csv"
    f.write_text("a,b\n1,2\n")
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/duplicate-check"):
            return reply(body={"duplicate": None})
        if request.url.path.endswith("/upload/init"):
            return reply(body={"uploadId": "up1", "strategy": "backend"})
        if request.url.path.endswith("/upload/stream"):
            return reply(body={"uploadId": "up1"})
        if request.url.path.endswith("/upload/complete"):
            sent = json.loads(request.content)
            assert sent["uploadId"] == "up1" and sent["org"] == "kano" and sent["access"] == "restricted"
            return reply(body={"dataset": {"id": DS, "name": "kano/crops", "status": "processing"}})
        return reply(body={"dataset": {"id": DS, "name": "kano/crops", "status": "ready", "rowCount": 1}})

    ds = make_client(handler).datasets.publish(
        f, name="kano/crops", description="Maize yields per plot.", category="Agriculture", progress=False
    )
    assert ds.status == "ready" and ds.row_count == 1
    assert calls[0].endswith("/duplicate-check")


def test_publishing_the_same_file_twice_is_refused(make_client: MakeClient, tmp_path: Path) -> None:
    f = tmp_path / "crops.csv"
    f.write_text("a,b\n1,2\n")

    def handler(request: httpx.Request) -> httpx.Response:
        return reply(body={"duplicate": {"id": DS, "name": "kano/crops"}})

    with pytest.raises(aem.DuplicateFileError, match="kano/crops") as info:
        make_client(handler).datasets.publish(f, name="kano/again", description="x" * 30, category="Agriculture", progress=False)
    assert info.value.existing_id == DS


def test_large_files_go_to_azure_in_blocks(make_client: MakeClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("aem._upload.SINGLE_PUT_MAX", 10)
    monkeypatch.setattr("aem._upload.BLOCK_SIZE", 8)
    monkeypatch.setattr("aem._upload.time.sleep", lambda _s: None)
    f = tmp_path / "big.csv"
    f.write_bytes(b"x" * 20)  # 3 blocks of 8, 8, 4
    azure: list[str] = []
    failed_once = [False]

    def storage(request: httpx.Request) -> httpx.Response:
        azure.append(str(request.url))
        assert "authorization" not in request.headers  # the AEM key never goes to storage
        if "blockid" in str(request.url) and not failed_once[0]:
            failed_once[0] = True
            return httpx.Response(503)
        return httpx.Response(201)

    def handler(request: httpx.Request) -> httpx.Response:
        return reply(body={"uploadId": "up9", "strategy": "direct", "uploadUrl": "https://store.test/blob?sig=1"})

    client = make_client(handler)  # the AEM connection is made before storage is swapped in
    real_client = httpx.Client
    monkeypatch.setattr("aem._upload.httpx.Client", lambda **kw: real_client(transport=httpx.MockTransport(storage), **kw))

    seen: list[int] = []
    upload_id = client.datasets._uploader.upload(f, progress=lambda sent, total: seen.append(sent))
    assert upload_id == "up9"
    assert sum("comp=block&" in u for u in azure) == 4  # 3 blocks + 1 retry
    assert azure[-1].endswith("comp=blocklist")
    assert seen[-1] == 20


def test_competition_join_submit_and_leaderboard(make_client: MakeClient, tmp_path: Path) -> None:
    preds = tmp_path / "preds.csv"
    preds.write_text("plot_id,yield\np1,10\n")

    def handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if p.endswith("/upload/init"):
            return reply(body={"uploadId": "u1", "strategy": "backend"})
        if p.endswith("/upload/stream"):
            return reply(body={})
        if p.endswith("/submissions") and request.method == "POST":
            return reply(201, {"submission": {"id": "s1", "status": "scored", "publicScore": 5.0, "fileName": "preds.csv"}})
        if p.endswith("/leaderboard"):
            return reply(body={"public": [{"rank": 1, "displayName": "Ada L.", "score": 5, "entries": 1, "isYou": True}]})
        if p.endswith("/join"):
            return reply(body={"joined": True})
        return reply(
            body={
                "competition": {"id": "c1", "title": "Kano", "phase": "open", "maxDailySubmissions": 3},
                "viewer": {"joined": True, "submissionsToday": 1},
            }
        )

    client = make_client(handler)
    c = client.competitions.get("c1")
    assert c.is_open and c.joined and c.submissions_left_today == 2
    client.competitions.join("c1")
    sub = client.competitions.submit("c1", preds, progress=False)
    assert sub.scored and sub.public_score == 5.0 and sub.private_score is None
    board = client.competitions.leaderboard("c1")
    assert board[0].is_you and board[0].score == 5
