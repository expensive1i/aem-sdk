from __future__ import annotations

import builtins
import os
from pathlib import Path
from typing import TYPE_CHECKING

from .._upload import ProgressCallback, Uploader
from ..types import Competition, CompetitionSubmission, LeaderboardEntry

if TYPE_CHECKING:
    from .._http import HTTPClient


class Competitions:
    """Take part in AEM competitions: join, download the test file, submit predictions.

    >>> c = client.competitions.get("kano-maize-yield-challenge-1a2b3c")
    >>> client.competitions.join(c.id)
    >>> client.competitions.download_test(c.id, "data/")
    >>> sub = client.competitions.submit(c.id, "predictions.csv")
    >>> sub.public_score

    Predictions are scored on AEM's servers against hidden answers that never leave AEM.
    """

    def __init__(self, http: HTTPClient, uploader: Uploader) -> None:
        self._http = http
        self._uploader = uploader

    def list(self, *, kind: str | None = None, search: str | None = None) -> builtins.list[Competition]:
        """Published competitions. `kind` is featured, research, getting-started or community."""
        body = self._http.request("GET", "/competitions", params={"kind": kind, "search": search})
        return [Competition.from_api(c) for c in body.get("competitions") or []]

    def get(self, competition: str) -> Competition:
        """One competition by ID or slug, with whether you've joined and today's submissions."""
        body = self._http.request("GET", f"/competitions/{competition}")
        return Competition.from_api(body.get("competition") or {}, body.get("viewer"))

    def join(self, competition: str) -> None:
        """Join (and accept the rules). Needed before downloading the test file or submitting."""
        self._http.request("POST", f"/competitions/{competition}/join")

    def download_test(self, competition: str, path: str | os.PathLike[str] | None = None) -> Path:
        """Download the test file (inputs only, no answers). Saves to `path` (a file or a folder)."""
        target = Path(path) if path is not None else Path.cwd()
        if target.is_dir():
            target = target / (self.get(competition).test_file_name or "test.csv")
        partial = target.with_name(target.name + ".part")
        with open(partial, "wb") as f:
            self._http.stream_to_file(f"/competitions/{competition}/test-file", f)
        partial.replace(target)
        return target

    def submit(
        self,
        competition: str,
        path: str | os.PathLike[str],
        *,
        note: str | None = None,
        progress: bool | ProgressCallback | None = None,
    ) -> CompetitionSubmission:
        """Upload a predictions CSV and get its score straight away.

        The file needs the competition's ID column and answer column, one row per test row.
        If it can't be scored, the result has ``status == "failed"`` and ``error`` says why;
        that doesn't use up one of today's submissions.
        """
        upload_id = self._uploader.upload(path, kind="data", progress=progress)
        body = self._http.request(
            "POST", f"/competitions/{competition}/submissions", json={"uploadId": upload_id, "note": note or ""}
        )
        return CompetitionSubmission.from_api(body.get("submission") or {})

    def submissions(self, competition: str) -> builtins.list[CompetitionSubmission]:
        """Your submissions, newest first."""
        body = self._http.request("GET", f"/competitions/{competition}/submissions")
        return [CompetitionSubmission.from_api(s) for s in body.get("submissions") or []]

    def leaderboard(self, competition: str, *, final: bool = False) -> builtins.list[LeaderboardEntry]:
        """The public leaderboard, or with ``final=True`` the final one (only once it has closed)."""
        body = self._http.request("GET", f"/competitions/{competition}/leaderboard")
        rows = body.get("private") if final else body.get("public")
        return [LeaderboardEntry.from_api(r) for r in rows or []]
