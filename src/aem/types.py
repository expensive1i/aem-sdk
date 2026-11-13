"""The objects aem-sdk returns: small, typed and read-only."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

__all__ = [
    "AccessRequest",
    "Column",
    "Competition",
    "CompetitionSubmission",
    "Dataset",
    "Execution",
    "Export",
    "LeaderboardEntry",
    "Model",
    "Notebook",
    "Output",
    "Preview",
    "User",
]


def _time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    return [t.strip() for t in str(value or "").split(",") if t.strip()]


@dataclass(frozen=True)
class User:
    id: str
    email: str
    first_name: str
    last_name: str
    organization: str
    role: str

    @classmethod
    def from_api(cls, d: dict[str, Any]) -> User:
        return cls(
            id=d.get("id", ""),
            email=d.get("email", ""),
            first_name=d.get("firstName", ""),
            last_name=d.get("lastName", ""),
            organization=d.get("organization", ""),
            role=d.get("role", ""),
        )


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    nullable: str = ""
    key: str = ""
    description: str = ""

    @classmethod
    def from_api(cls, d: dict[str, Any]) -> Column:
        return cls(
            name=d.get("name", ""),
            type=d.get("type", ""),
            nullable=d.get("nullable", ""),
            key=d.get("key", ""),
            description=d.get("desc", ""),
        )


@dataclass(frozen=True)
class Dataset:
    """A dataset in the AEM marketplace. Its rows stay inside AEM."""

    id: str
    name: str
    org: str
    description: str
    category: str
    tags: list[str]
    format: str
    status: str
    access_tier: str
    size_bytes: int
    row_count: int
    price_per_query: str
    license: str
    likes: int
    queries: int
    columns: list[Column] = field(default_factory=list)
    your_access: str | None = None  # none | pending | approved | rejected | owner (only from datasets.get)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def is_open(self) -> bool:
        return self.access_tier == "open"

    @classmethod
    def from_api(cls, d: dict[str, Any], viewer: dict[str, Any] | None = None) -> Dataset:
        access = None
        if viewer:
            access = "owner" if viewer.get("isOwner") else viewer.get("access")
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            org=d.get("org", ""),
            description=d.get("description", ""),
            category=d.get("category", ""),
            tags=_tags(d.get("tags")),
            format=d.get("format", ""),
            status=d.get("status", ""),
            access_tier=d.get("accessTier", ""),
            size_bytes=int(d.get("sizeBytes") or 0),
            row_count=int(d.get("rowCount") or 0),
            price_per_query=d.get("pricePerQuery", ""),
            license=d.get("license", ""),
            likes=int(d.get("likesCount") or 0),
            queries=int(d.get("queriesCount") or 0),
            columns=[Column.from_api(c) for c in d.get("columns") or []],
            your_access=access,
            created_at=_time(d.get("createdAt")),
            updated_at=_time(d.get("updatedAt")),
        )


@dataclass(frozen=True)
class Preview:
    """A few sample rows of an open dataset."""

    columns: list[str]
    rows: list[dict[str, str]]

    def to_pandas(self) -> Any:
        """The sample as a pandas DataFrame (needs `pip install "aem-sdk[pandas]"`)."""
        import pandas as pd

        return pd.DataFrame(self.rows, columns=self.columns)


@dataclass(frozen=True)
class AccessRequest:
    id: str
    dataset_id: str
    status: str  # pending | approved | rejected
    purpose: str
    created_at: datetime | None = None

    @classmethod
    def from_api(cls, d: dict[str, Any]) -> AccessRequest:
        return cls(
            id=d.get("id", ""),
            dataset_id=d.get("datasetId", ""),
            status=d.get("status", ""),
            purpose=d.get("purpose", ""),
            created_at=_time(d.get("createdAt")),
        )


@dataclass(frozen=True)
class Model:
    """A model in the AEM Model Marketplace. Its weights stay inside AEM."""

    id: str
    name: str
    org: str
    description: str
    category: str
    framework: str
    tags: list[str]
    params: str
    context_length: str
    access_tier: str
    price_per_query: str
    likes: int
    weights_format: str = ""
    weights_size_bytes: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_api(cls, d: dict[str, Any]) -> Model:
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            org=d.get("org", ""),
            description=d.get("description", ""),
            category=d.get("category", ""),
            framework=d.get("framework", ""),
            tags=_tags(d.get("tags")),
            params=d.get("params", ""),
            context_length=d.get("contextLength", ""),
            access_tier=d.get("accessTier", ""),
            price_per_query=d.get("pricePerQuery", ""),
            likes=int(d.get("likesCount") or 0),
            weights_format=d.get("weightsFormat") or "",
            weights_size_bytes=int(d.get("weightsSizeBytes") or 0),
            created_at=_time(d.get("createdAt")),
            updated_at=_time(d.get("updatedAt")),
        )


@dataclass(frozen=True)
class Notebook:
    id: str
    title: str
    description: str
    status: str  # running | stopped
    dataset_ids: list[str]
    model_ids: list[str]
    created_at: datetime | None = None

    @property
    def is_running(self) -> bool:
        return self.status == "running"

    @classmethod
    def from_api(cls, d: dict[str, Any]) -> Notebook:
        return cls(
            id=d.get("id", ""),
            title=d.get("title", ""),
            description=d.get("description", ""),
            status=d.get("status", ""),
            dataset_ids=list(d.get("datasetIds") or []),
            model_ids=list(d.get("modelIds") or []),
            created_at=_time(d.get("createdAt")),
        )


@dataclass(frozen=True)
class Output:
    type: str  # stream | result | image | error | notice
    name: str = ""
    text: str = ""
    data: str = ""  # base64 PNG for images
    ename: str = ""

    @classmethod
    def from_api(cls, d: dict[str, Any]) -> Output:
        return cls(
            type=d.get("type", ""),
            name=d.get("name", ""),
            text=d.get("text", ""),
            data=d.get("data", ""),
            ename=d.get("ename", ""),
        )


@dataclass(frozen=True)
class Execution:
    """The result of running code in a notebook's sandbox."""

    id: str
    status: str  # running | ok | error | interrupted | failed
    outputs: list[Output]
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def done(self) -> bool:
        return self.status != "running"

    @property
    def text(self) -> str:
        """Everything the code printed or returned, as one string."""
        return "".join(o.text for o in self.outputs if o.text)

    @classmethod
    def from_api(cls, d: dict[str, Any]) -> Execution:
        return cls(
            id=d.get("id", ""),
            status=d.get("status", ""),
            outputs=[Output.from_api(o) for o in d.get("outputs") or []],
            truncated=bool(d.get("truncated")),
        )


@dataclass(frozen=True)
class Export:
    """A trained model file on its way out of the sandbox. Downloadable once approved."""

    id: str
    notebook_id: str
    file_name: str
    size_bytes: int
    sha256: str
    status: str  # pending | approved | rejected
    dataset_ids: list[str]
    created_at: datetime | None = None

    @property
    def approved(self) -> bool:
        return self.status == "approved"

    @classmethod
    def from_api(cls, d: dict[str, Any]) -> Export:
        return cls(
            id=d.get("id", ""),
            notebook_id=d.get("notebookId", ""),
            file_name=d.get("fileName", ""),
            size_bytes=int(d.get("sizeBytes") or 0),
            sha256=d.get("sha256", ""),
            status=d.get("status", ""),
            dataset_ids=list(d.get("datasetIds") or []),
            created_at=_time(d.get("createdAt")),
        )


@dataclass(frozen=True)
class Competition:
    """A competition: predict the answers for a test file; scored on AEM's servers."""

    id: str
    slug: str
    title: str
    summary: str
    description: str
    rules: str
    kind: str  # featured | research | getting-started | community
    host: str
    metric: str  # accuracy | f1 | auc | rmse | mae | logloss
    metric_name: str
    higher_is_better: bool
    id_column: str
    target_column: str
    public_pct: int
    max_daily_submissions: int
    test_file_name: str
    test_rows: int
    prize_usd: float
    phase: str  # draft | upcoming | open | closed
    participants: int
    submissions: int
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    dataset_id: str | None = None
    joined: bool = False  # only from competitions.get
    is_host: bool = False
    submissions_today: int = 0

    @property
    def is_open(self) -> bool:
        return self.phase == "open"

    @property
    def submissions_left_today(self) -> int:
        return max(0, self.max_daily_submissions - self.submissions_today)

    @classmethod
    def from_api(cls, d: dict[str, Any], viewer: dict[str, Any] | None = None) -> Competition:
        v = viewer or {}
        return cls(
            id=d.get("id", ""),
            slug=d.get("slug", ""),
            title=d.get("title", ""),
            summary=d.get("summary", ""),
            description=d.get("description", ""),
            rules=d.get("rules", ""),
            kind=d.get("kind", ""),
            host=d.get("hostName", ""),
            metric=d.get("metric", ""),
            metric_name=d.get("metricName", ""),
            higher_is_better=bool(d.get("higherIsBetter")),
            id_column=d.get("idColumn", ""),
            target_column=d.get("targetColumn", ""),
            public_pct=int(d.get("publicPct") or 0),
            max_daily_submissions=int(d.get("maxDailySubmissions") or 0),
            test_file_name=d.get("testFileName", ""),
            test_rows=int(d.get("testRows") or 0),
            prize_usd=float(d.get("prizeUsd") or 0),
            phase=d.get("phase", ""),
            participants=int(d.get("participantsCount") or 0),
            submissions=int(d.get("submissionsCount") or 0),
            starts_at=_time(d.get("startsAt")),
            ends_at=_time(d.get("endsAt")),
            dataset_id=d.get("datasetId") or None,
            joined=bool(v.get("joined")),
            is_host=bool(v.get("isHost")),
            submissions_today=int(v.get("submissionsToday") or 0),
        )


@dataclass(frozen=True)
class CompetitionSubmission:
    """One predictions file and its score. `private_score` appears once the competition closes."""

    id: str
    file_name: str
    status: str  # scored | failed
    public_score: float | None = None
    private_score: float | None = None
    error: str | None = None
    note: str | None = None
    created_at: datetime | None = None

    @property
    def scored(self) -> bool:
        return self.status == "scored"

    @classmethod
    def from_api(cls, d: dict[str, Any]) -> CompetitionSubmission:
        pub, priv = d.get("publicScore"), d.get("privateScore")
        return cls(
            id=d.get("id", ""),
            file_name=d.get("fileName", ""),
            status=d.get("status", ""),
            public_score=None if pub is None else float(pub),
            private_score=None if priv is None else float(priv),
            error=d.get("error") or None,
            note=d.get("note") or None,
            created_at=_time(d.get("createdAt")),
        )


@dataclass(frozen=True)
class LeaderboardEntry:
    rank: int
    name: str
    score: float
    entries: int
    is_you: bool
    last_at: datetime | None = None

    @classmethod
    def from_api(cls, d: dict[str, Any]) -> LeaderboardEntry:
        return cls(
            rank=int(d.get("rank") or 0),
            name=d.get("displayName", ""),
            score=float(d.get("score") or 0),
            entries=int(d.get("entries") or 0),
            is_you=bool(d.get("isYou")),
            last_at=_time(d.get("lastAt")),
        )
