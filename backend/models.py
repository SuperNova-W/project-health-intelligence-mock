"""Privacy-safe Beanie documents and frontend-compatible response contracts."""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any, ClassVar, Literal

from beanie import Document, PydanticObjectId
from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    computed_field,
    model_validator,
)
from pymongo import ASCENDING, IndexModel

from .errors import EvidenceTraceError, ImmutableSnapshotError, PrivacyViolationError


PROJECT_SLUG = StringConstraints(
    strip_whitespace=True,
    min_length=1,
    max_length=80,
    pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
)
ProjectId = str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalized_key(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


_FORBIDDEN_PRIVACY_KEYS = {
    "contributoridentity",
    "contributoridentities",
    "authoridentityref",
    "authoridentity",
    "giteausername",
    "giteausernames",
    "percontributormetrics",
    "perpersonmetrics",
    "commitsbyuser",
    "additionsbyuser",
    "deletionsbyuser",
    "commitsbycontributor",
    "additionsbycontributor",
    "deletionsbycontributor",
    "identitymap",
}


def _find_forbidden_privacy_key(value: Any, path: str = "payload") -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = _normalized_key(str(key))
            if normalized in _FORBIDDEN_PRIVACY_KEYS:
                return f"{path}.{key}"
            if "perperson" in normalized or "bycontributor" in normalized:
                return f"{path}.{key}"
            nested = _find_forbidden_privacy_key(child, f"{path}.{key}")
            if nested:
                return nested
    elif isinstance(value, (list, tuple, set)):
        for index, child in enumerate(value):
            nested = _find_forbidden_privacy_key(child, f"{path}[{index}]")
            if nested:
                return nested
    return None


class PrivacySafeModel(BaseModel):
    """Mixin for rejecting contributor identities and per-person metrics."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    @model_validator(mode="before")
    @classmethod
    def reject_individual_level_data(cls, value: Any) -> Any:
        forbidden_path = _find_forbidden_privacy_key(value)
        if forbidden_path:
            raise PrivacyViolationError(
                f"individual contributor data is prohibited at {forbidden_path}"
            )
        return value

    def public_dump(self) -> dict[str, Any]:
        """Serialize a response with null privacy-gated metrics omitted."""

        return self.model_dump(mode="json", by_alias=True, exclude_none=True)

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(*args, **kwargs)


class LifecycleState(StrEnum):
    NEW = "new"
    ACTIVE = "active"
    MAINTENANCE = "maintenance"
    PAUSED = "paused"
    ARCHIVED = "archived"


class AttentionStatus(StrEnum):
    CLEAR = "clear"
    WATCH = "watch"
    AT_RISK = "at_risk"
    INSUFFICIENT_DATA = "insufficient_data"
    PLANNED_PAUSE = "planned_pause"


class WarningSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class FeedbackCategory(StrEnum):
    HELPFUL = "helpful"
    NOT_USEFUL = "not_useful"
    FALSE_POSITIVE = "false_positive"
    MISSED_RISK = "missed_risk"
    PLANNED_PAUSE = "planned_pause"
    EXPECTED_CYCLE = "expected_cycle"
    DATA_QUALITY = "data_quality"
    RISK_CONFIRMED = "risk_confirmed"
    RISK_RESOLVED = "risk_resolved"


class Role(StrEnum):
    ADMIN = "admin"
    PORTFOLIO_LEADER = "portfolio_leader"
    PROJECT_LEAD = "project_lead"


class PHIDocument(Document):
    """Common Beanie document configuration."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    @model_validator(mode="before")
    @classmethod
    def reject_individual_level_data(cls, value: Any) -> Any:
        forbidden_path = _find_forbidden_privacy_key(value)
        if forbidden_path:
            raise PrivacyViolationError(
                f"individual contributor data is prohibited at {forbidden_path}"
            )
        return value

    def public_dump(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(*args, **kwargs)


class RepositoryRef(PrivacySafeModel):
    gitea_repo_id: str = Field(min_length=1, max_length=160)
    repo_slug: str = Field(min_length=1, max_length=240)


class SharedRepositoryRef(RepositoryRef):
    shared_with_project_ids: list[ProjectId] = Field(default_factory=list, max_length=100)


class PlannedPause(PrivacySafeModel):
    starts_on: date
    ends_on: date | None = None
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_range(self) -> "PlannedPause":
        if self.ends_on is not None and self.ends_on < self.starts_on:
            raise ValueError("planned pause ends_on must be on or after starts_on")
        return self

    def overlaps(self, week_start: date, week_end: date) -> bool:
        return self.starts_on <= week_end and (
            self.ends_on is None or self.ends_on >= week_start
        )


class ScoringDecision(PrivacySafeModel):
    suppressed: bool
    status: AttentionStatus | None = None
    reason: str | None = None


class ProjectDocument(PHIDocument):
    project_id: ProjectId = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    display_name: str = Field(min_length=1, max_length=200)
    lifecycle_state: LifecycleState = LifecycleState.NEW
    created_at: datetime = Field(default_factory=utc_now)
    archived_at: datetime | None = None
    data_owner_user_id: str | None = Field(default=None, min_length=1, max_length=200)
    non_goals_ack: bool = False
    planned_pauses: list[PlannedPause] = Field(default_factory=list, max_length=100)

    class Settings:
        name = "projects"
        indexes = [IndexModel([("project_id", ASCENDING)], unique=True)]

    def scoring_decision(self, week_start: date, week_end: date) -> ScoringDecision:
        """Short-circuit pause/lifecycle state before any rule evaluation."""

        if self.lifecycle_state == LifecycleState.PAUSED:
            return ScoringDecision(
                suppressed=True,
                status=AttentionStatus.PLANNED_PAUSE,
                reason="project lifecycle is paused",
            )
        if self.lifecycle_state == LifecycleState.ARCHIVED:
            return ScoringDecision(
                suppressed=True,
                status=None,
                reason="project lifecycle is archived",
            )
        if any(pause.overlaps(week_start, week_end) for pause in self.planned_pauses):
            return ScoringDecision(
                suppressed=True,
                status=AttentionStatus.PLANNED_PAUSE,
                reason="planned pause overlaps snapshot window",
            )
        return ScoringDecision(suppressed=False)


class BoundaryDocument(PHIDocument):
    project_id: ProjectId = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    root_authentik_team_id: str = Field(min_length=1, max_length=200)
    included_subteam_ids: list[str] = Field(default_factory=list, max_length=500)
    primary_repos: list[RepositoryRef] = Field(default_factory=list, max_length=500)
    shared_repos: list[SharedRepositoryRef] = Field(default_factory=list, max_length=500)
    excluded_repos: list[str] = Field(default_factory=list, max_length=500)
    effective_from: date
    effective_to: date | None = None
    data_owner_user_id: str | None = Field(default=None, min_length=1, max_length=200)
    created_by: str = Field(min_length=1, max_length=200)
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        name = "boundaries"
        indexes = [
            IndexModel(
                [("project_id", ASCENDING), ("effective_from", ASCENDING)],
                name="boundaries_project_effective_from",
            ),
        ]

    @model_validator(mode="after")
    def validate_range(self) -> "BoundaryDocument":
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be on or after effective_from")
        return self

    def is_effective_at(self, when: date) -> bool:
        return self.effective_from <= when and (
            self.effective_to is None or when <= self.effective_to
        )


class IdentityMapDocument(PHIDocument):
    """Privacy guard collection; individual identity mappings are prohibited.

    The collection remains present so deployments can explicitly record that
    identity mapping is disabled. It intentionally has no username, user-id,
    or identity-reference fields.
    """

    record_type: Literal["aggregate_only_guard"] = "aggregate_only_guard"
    mapping_enabled: Literal[False] = False
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        name = "identity_map"


class AggregateMetrics(PrivacySafeModel):
    """Repository/project aggregates. No contributor-level dimensions exist."""

    active_days: int | None = Field(default=None, ge=0)
    days_since_activity: int | None = Field(default=None, ge=0)
    open_prs: int | None = Field(default=None, ge=0)
    oldest_open_pr_days: float | None = Field(default=None, ge=0)
    review_latency_days: float | None = Field(default=None, ge=0)
    merged_count: int | None = Field(default=None, ge=0)
    active_contributors: int | None = Field(default=None, ge=0)
    team_size: int | None = Field(default=None, ge=0)
    aggregation_floor: int | None = Field(default=None, ge=1)
    data_completeness_pct: float | None = Field(default=None, ge=0, le=100)
    last_sync_at: datetime | None = None

    @model_validator(mode="after")
    def enforce_aggregation_floor(self) -> "AggregateMetrics":
        if self.active_contributors is None:
            return self
        if self.team_size is None:
            raise PrivacyViolationError(
                "active_contributors requires an explicit aggregate team_size"
            )
        from .config import get_settings

        floor = max(self.aggregation_floor or 0, get_settings().aggregation_floor)
        if self.team_size < floor:
            raise PrivacyViolationError(
                "active_contributors cannot be stored below the configured aggregation floor"
            )
        if self.active_contributors > self.team_size:
            raise ValueError("active_contributors cannot exceed team_size")
        return self

    def public_dump(self) -> dict[str, Any]:
        payload = super().public_dump()
        payload.pop("team_size", None)
        payload.pop("aggregation_floor", None)
        return payload


class RepoActivityDocument(PHIDocument):
    """Append-only, aggregate-only raw evidence for one repository sync window."""

    project_id: ProjectId | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    gitea_repo_id: str = Field(min_length=1, max_length=160)
    repo_slug: str = Field(min_length=1, max_length=240)
    window_start: date
    window_end: date
    synced_at: datetime = Field(default_factory=utc_now)
    active_days: int | None = Field(default=None, ge=0)
    days_since_activity: int | None = Field(default=None, ge=0)
    open_prs: int | None = Field(default=None, ge=0)
    oldest_open_pr_days: float | None = Field(default=None, ge=0)
    review_latency_days: float | None = Field(default=None, ge=0)
    merged_count: int | None = Field(default=None, ge=0)
    active_contributors: int | None = Field(default=None, ge=0)
    team_size: int | None = Field(default=None, ge=0)
    aggregation_floor: int | None = Field(default=None, ge=1)
    data_completeness_pct: float | None = Field(default=None, ge=0, le=100)
    last_sync_at: datetime | None = None

    class Settings:
        name = "repo_activity"
        indexes = [
            IndexModel(
                [("project_id", ASCENDING), ("window_start", ASCENDING)],
                name="repo_activity_project_window",
            ),
            IndexModel(
                [("repo_slug", ASCENDING), ("synced_at", ASCENDING)],
                name="repo_activity_repo_synced",
            ),
        ]

    @model_validator(mode="after")
    def validate_window_and_floor(self) -> "RepoActivityDocument":
        if self.window_end < self.window_start:
            raise ValueError("window_end must be on or after window_start")
        AggregateMetrics(
            active_contributors=self.active_contributors,
            team_size=self.team_size,
            aggregation_floor=self.aggregation_floor,
        )
        return self

    def aggregate_metrics(self) -> AggregateMetrics:
        return AggregateMetrics(
            active_days=self.active_days,
            days_since_activity=self.days_since_activity,
            open_prs=self.open_prs,
            oldest_open_pr_days=self.oldest_open_pr_days,
            review_latency_days=self.review_latency_days,
            merged_count=self.merged_count,
            active_contributors=self.active_contributors,
            team_size=self.team_size,
            aggregation_floor=self.aggregation_floor,
            data_completeness_pct=self.data_completeness_pct,
            last_sync_at=self.last_sync_at or self.synced_at,
        )


class EvidenceReference(PrivacySafeModel):
    """Pointer to an inspectable aggregate source row."""

    source_collection: Literal[
        "projects",
        "boundaries",
        "repo_activity",
        "weekly_snapshots",
        "feedback",
        "audit_log",
    ]
    source_id: str = Field(min_length=1, max_length=200)
    source_field: str = Field(min_length=1, max_length=120)
    observed_at: datetime


class WarningEvidenceItem(PrivacySafeModel):
    warning_id: str | None = None
    evidence_type: str = Field(
        default="metric",
        validation_alias=AliasChoices("evidence_type", "type"),
        serialization_alias="type",
        min_length=1,
        max_length=40,
    )
    icon: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=240)
    metric: str | None = Field(default=None, max_length=120)
    unit: str = Field(default="", max_length=30)
    current: int | float | str | None = None
    baseline: int | float | str | None = None
    source_refs: list[EvidenceReference] = Field(
        default_factory=list,
        validation_alias=AliasChoices("source_refs", "sourceEvidence"),
        serialization_alias="sourceEvidence",
        min_length=1,
        max_length=100,
    )


class WeeklySnapshotDocument(PHIDocument):
    """Immutable weekly unit of historical truth."""

    project_id: ProjectId = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    week_start: date
    week_end: date
    rule_set_version: str = Field(min_length=1, max_length=80)
    generated_at: datetime = Field(default_factory=utc_now)
    attention_status: AttentionStatus
    data_completeness_pct: float = Field(ge=0, le=100)
    last_sync_at: datetime | None = None
    metrics: AggregateMetrics
    baselines: AggregateMetrics | None = None
    warning_ids: list[PydanticObjectId] = Field(default_factory=list, max_length=100)
    series: dict[str, list[float | int | None]] = Field(default_factory=dict)
    series_baselines: dict[str, list[float | int | None]] = Field(default_factory=dict)

    class Settings:
        name = "weekly_snapshots"
        indexes = [
            IndexModel(
                [("project_id", ASCENDING), ("week_start", ASCENDING)],
                name="snapshots_project_week_start",
            ),
            IndexModel(
                [("project_id", ASCENDING), ("week_start", ASCENDING), ("rule_set_version", ASCENDING)],
                unique=True,
                name="snapshots_project_week_rule_version",
            ),
        ]

    @model_validator(mode="after")
    def validate_window(self) -> "WeeklySnapshotDocument":
        if self.week_end < self.week_start:
            raise ValueError("week_end must be on or after week_start")
        if self.attention_status == AttentionStatus.PLANNED_PAUSE and self.warning_ids:
            raise ValueError("planned-pause snapshots cannot contain risk warnings")
        return self

    async def save(self, *args: Any, **kwargs: Any) -> Any:
        if self.id is not None:
            raise ImmutableSnapshotError("weekly snapshots are immutable")
        return await super().save(*args, **kwargs)

    async def replace(self, *args: Any, **kwargs: Any) -> Any:
        raise ImmutableSnapshotError("weekly snapshots are immutable")

    async def update(self, *args: Any, **kwargs: Any) -> Any:
        raise ImmutableSnapshotError("weekly snapshots are immutable")

    async def delete(self, *args: Any, **kwargs: Any) -> Any:
        raise ImmutableSnapshotError("weekly snapshots are immutable")


class WarningDocument(PHIDocument):
    snapshot_id: PydanticObjectId
    project_id: ProjectId = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    rule_id: str = Field(min_length=1, max_length=120)
    rule_version: str = Field(min_length=1, max_length=80)
    signal_name: str = Field(min_length=1, max_length=160)
    current_value: float | int | None = None
    baseline_value: float | int | None = None
    time_window: str = Field(min_length=1, max_length=120)
    trigger_threshold: float | int | str | None = None
    severity: WarningSeverity
    explanation: str = Field(min_length=1, max_length=1_000)
    caveats: list[str] = Field(default_factory=list, max_length=50)
    data_freshness: str = Field(min_length=1, max_length=120)
    data_completeness_pct: float = Field(ge=0, le=100)
    evidence: list[WarningEvidenceItem] = Field(min_length=1, max_length=100)

    class Settings:
        name = "warnings"
        indexes = [
            IndexModel([("snapshot_id", ASCENDING)], name="warnings_snapshot_id"),
            IndexModel([("project_id", ASCENDING), ("rule_id", ASCENDING)], name="warnings_project_rule"),
        ]

    @model_validator(mode="after")
    def require_traceable_evidence(self) -> "WarningDocument":
        if not self.evidence or any(not item.source_refs for item in self.evidence):
            raise EvidenceTraceError("every warning must include inspectable source evidence")
        return self

    @computed_field(return_type=list[EvidenceReference])
    @property
    def evidence_refs(self) -> list[EvidenceReference]:
        return [reference for item in self.evidence for reference in item.source_refs]


class FeedbackDocument(PHIDocument):
    snapshot_id: PydanticObjectId
    warning_id: PydanticObjectId | None = None
    project_id: ProjectId = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    author_user_id: str = Field(min_length=1, max_length=200)
    category: FeedbackCategory
    note: str | None = Field(default=None, max_length=2_000)
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        name = "feedback"
        indexes = [IndexModel([("snapshot_id", ASCENDING)], name="feedback_snapshot_id")]


class AuditLogDocument(PHIDocument):
    actor_user_id: str = Field(min_length=1, max_length=200)
    action: str = Field(min_length=1, max_length=160)
    target_type: str = Field(min_length=1, max_length=80)
    target_id: str = Field(min_length=1, max_length=200)
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    at: datetime = Field(default_factory=utc_now)

    class Settings:
        name = "audit_log"
        indexes = [
            IndexModel(
                [("target_type", ASCENDING), ("target_id", ASCENDING), ("at", ASCENDING)],
                name="audit_target_at",
            ),
        ]

    @model_validator(mode="after")
    def validate_safe_payloads(self) -> "AuditLogDocument":
        for label, payload in (("before", self.before), ("after", self.after)):
            forbidden_path = _find_forbidden_privacy_key(payload, label)
            if forbidden_path:
                raise PrivacyViolationError(
                    f"individual contributor data is prohibited at {forbidden_path}"
                )
        return self


class PublicAggregateMetrics(PrivacySafeModel):
    """Response shape that omits the exact team-size enforcement fields."""

    active_days: int | None = Field(default=None, ge=0)
    days_since_activity: int | None = Field(default=None, ge=0)
    open_prs: int | None = Field(default=None, ge=0)
    oldest_open_pr_days: float | None = Field(default=None, ge=0)
    review_latency_days: float | None = Field(default=None, ge=0)
    merged_count: int | None = Field(default=None, ge=0)
    active_contributors: int | None = Field(default=None, ge=0)
    data_completeness_pct: float | None = Field(default=None, ge=0, le=100)
    last_sync_at: datetime | None = None

    @classmethod
    def from_metrics(cls, metrics: AggregateMetrics) -> "PublicAggregateMetrics":
        return cls.model_validate(metrics.public_dump())


class SeriesBaselines(PrivacySafeModel):
    open_prs: list[float | int | None] = Field(
        min_length=2,
        max_length=2,
        validation_alias=AliasChoices("open_prs", "openPRs"),
        serialization_alias="openPRs",
    )
    review_latency: list[float | int | None] = Field(
        min_length=2,
        max_length=2,
        validation_alias=AliasChoices("review_latency", "reviewLatency"),
        serialization_alias="reviewLatency",
    )
    contributors: list[float | int | None] | None = Field(default=None, min_length=2, max_length=2)


class Series(PrivacySafeModel):
    activity: list[float | int | None] = Field(default_factory=list, max_length=8)
    open_prs: list[float | int | None] = Field(
        default_factory=list,
        validation_alias=AliasChoices("open_prs", "openPRs"),
        serialization_alias="openPRs",
        max_length=8,
    )
    review_latency: list[float | int | None] = Field(
        default_factory=list,
        validation_alias=AliasChoices("review_latency", "reviewLatency"),
        serialization_alias="reviewLatency",
        max_length=8,
    )
    contributors: list[float | int | None] | None = Field(default=None, max_length=8)


class BoundaryView(PrivacySafeModel):
    root_team: str = Field(
        validation_alias=AliasChoices("root_team", "rootTeam"),
        serialization_alias="rootTeam",
    )
    subteams: list[str] = Field(default_factory=list)
    repos: list[str] = Field(default_factory=list)
    data_owner: str | None = Field(
        default=None,
        validation_alias=AliasChoices("data_owner", "dataOwner"),
        serialization_alias="dataOwner",
    )
    effective_since: date | str | None = Field(
        default=None,
        validation_alias=AliasChoices("effective_since", "effectiveSince"),
        serialization_alias="effectiveSince",
    )
    effective_until: date | str | None = Field(default=None, validation_alias=AliasChoices("effective_until", "effectiveUntil"), serialization_alias="effectiveUntil")
    version: str | None = None
    lifecycle: str


class HistoryItem(PrivacySafeModel):
    date: date | datetime | str
    actor: str
    action: str
    note: str | None = None


class ProjectResponse(PrivacySafeModel):
    """Frontend-compatible project projection with no contributor identities."""

    id: ProjectId
    name: str
    short: str
    team: str
    repo: str
    status: str
    status_class: str = Field(
        validation_alias=AliasChoices("status_class", "statusClass"),
        serialization_alias="statusClass",
    )
    signal: str
    signal_detail: str = Field(
        validation_alias=AliasChoices("signal_detail", "signalDetail"),
        serialization_alias="signalDetail",
    )
    last_activity: str = Field(
        validation_alias=AliasChoices("last_activity", "lastActivity"),
        serialization_alias="lastActivity",
    )
    trend: str
    weeks: list[float | int | None] = Field(min_length=8, max_length=8)
    flag_from: int = Field(
        validation_alias=AliasChoices("flag_from", "flagFrom"),
        serialization_alias="flagFrom",
    )
    series_baselines: SeriesBaselines = Field(
        validation_alias=AliasChoices("series_baselines", "seriesBaselines"),
        serialization_alias="seriesBaselines",
    )
    series: Series
    description: str
    boundary: BoundaryView
    evidence: list[WarningEvidenceItem] = Field(default_factory=list)
    history: list[HistoryItem] = Field(default_factory=list)
    metrics: PublicAggregateMetrics | None = None
    baselines: PublicAggregateMetrics | None = None
    data_completeness_pct: float | None = Field(default=None, ge=0, le=100)
    last_sync_at: datetime | None = None

    @model_validator(mode="after")
    def enforce_public_contributor_gate(self) -> "ProjectResponse":
        contributor_series_present = (
            self.series.contributors is not None
            or self.series_baselines.contributors is not None
        )
        contributor_evidence_present = any(
            item.metric in {"contributors", "active_contributors"}
            for item in self.evidence
        )
        if contributor_series_present or contributor_evidence_present:
            if self.metrics is None or self.metrics.active_contributors is None:
                raise PrivacyViolationError(
                    "contributor aggregates must be omitted below the configured floor"
                )
        return self
    snapshot_id: str | None = None


class WeeklySnapshotResponse(PrivacySafeModel):
    """Shared weekly snapshot response envelope."""

    snapshot_week_start: date
    snapshot_week_end: date
    generated_at: datetime
    rule_set_version: str
    data_completeness_pct: float = Field(ge=0, le=100)
    last_sync_at: datetime | None = None
    projects: list[ProjectResponse] = Field(default_factory=list)
