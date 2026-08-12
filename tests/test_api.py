"""API and persistence-boundary tests for the privacy-safe backend."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest
from beanie import PydanticObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.auth import AuthUser, get_current_user
from backend.config import Settings, get_settings
from backend.db import store
from backend.errors import ImmutableSnapshotError
from backend.jobs import generate_weekly_snapshots
from backend.main import create_app
from backend.models import (
    AggregateMetrics,
    AttentionStatus,
    BoundaryDocument,
    EvidenceReference,
    LifecycleState,
    ProjectDocument,
    RepoActivityDocument,
    RepositoryRef,
    Role,
    WarningDocument,
    WarningEvidenceItem,
    WarningSeverity,
    WeeklySnapshotDocument,
)


UTC = timezone.utc
WEEK_START = date(2026, 8, 3)
LAST_SYNC = datetime(2026, 8, 3, 13, 8, tzinfo=UTC)


@dataclass
class ApiHarness:
    app: FastAPI
    client: TestClient
    settings: Settings
    current_user: dict[str, AuthUser]

    def set_user(
        self,
        *,
        subject: str = "test-user",
        roles: set[Role] | None = None,
        project_ids: set[str] | None = None,
    ) -> None:
        self.current_user["value"] = AuthUser(
            subject=subject,
            roles=frozenset(roles or {Role.PORTFOLIO_LEADER}),
            project_ids=frozenset(project_ids or set()),
        )

    def add(self, collection: str, item: Any) -> None:
        asyncio.run(store.add(collection, item))


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> ApiHarness:
    """Use explicit dev auth in test mode, then override the user per test."""

    monkeypatch.setenv("PHI_ENVIRONMENT", "test")
    monkeypatch.setenv("PHI_DEV_AUTH", "true")
    monkeypatch.setenv("PHI_DEV_AUTH_USER_ID", "test-user")
    monkeypatch.setenv("PHI_DEV_AUTH_ROLES", "portfolio_leader")
    monkeypatch.setenv("PHI_AGGREGATION_FLOOR", "5")
    monkeypatch.setenv("PHI_RULE_SET_VERSION", "rules-v1")
    get_settings.cache_clear()

    settings = get_settings()
    app = create_app()
    current_user = {
        "value": AuthUser(
            subject="test-user",
            roles=frozenset({Role.PORTFOLIO_LEADER}),
            project_ids=frozenset(),
        )
    }
    app.dependency_overrides[get_current_user] = lambda: current_user["value"]
    app.dependency_overrides[get_settings] = lambda: settings

    store.clear()
    client = TestClient(app)
    harness = ApiHarness(app=app, client=client, settings=settings, current_user=current_user)
    try:
        yield harness
    finally:
        client.close()
        app.dependency_overrides.clear()
        store.clear()
        get_settings.cache_clear()


def _project(project_id: str, *, lifecycle: LifecycleState = LifecycleState.ACTIVE) -> ProjectDocument:
    return ProjectDocument.model_construct(
        project_id=project_id,
        display_name=project_id.replace("-", " ").title(),
        lifecycle_state=lifecycle,
        non_goals_ack=True,
    )


def _boundary(
    project_id: str,
    *,
    team: str = "team-old",
    repo: str = "repo-old",
    effective_from: date = date(2026, 1, 1),
) -> BoundaryDocument:
    return BoundaryDocument.model_construct(
        project_id=project_id,
        root_authentik_team_id=team,
        primary_repos=[RepositoryRef(gitea_repo_id=repo, repo_slug=repo)],
        effective_from=effective_from,
        created_by="test-admin",
    )


def _metrics(*, contributors: int | None = 6, completeness: float = 100) -> AggregateMetrics:
    values: dict[str, Any] = {
        "active_days": 4,
        "days_since_activity": 1,
        "open_prs": 2,
        "oldest_open_pr_days": 3,
        "review_latency_days": 2.0,
        "merged_count": 3,
        "data_completeness_pct": completeness,
        "last_sync_at": LAST_SYNC,
    }
    if contributors is not None:
        values.update(
            active_contributors=contributors,
            team_size=8,
            aggregation_floor=5,
        )
    return AggregateMetrics(**values)


def _snapshot(
    project_id: str,
    *,
    week_start: date = WEEK_START,
    version: str = "rules-v1",
    status: AttentionStatus = AttentionStatus.WATCH,
    metrics: AggregateMetrics | None = None,
    warning_ids: list[PydanticObjectId] | None = None,
    with_contributor_series: bool = True,
) -> WeeklySnapshotDocument:
    metrics = metrics or _metrics()
    series: dict[str, list[int | None]] = {
        "activity": [6, 6, 5, 5, 4, 4, 4, 4],
        "open_prs": [1, 1, 1, 2, 2, 2, 2, 2],
        "review_latency": [1, 1, 1, 1, 2, 2, 2, 2],
    }
    baselines: dict[str, list[int | None]] = {
        "open_prs": [1, 2],
        "review_latency": [1, 2],
    }
    if with_contributor_series:
        series["contributors"] = [6, 6, 6, 6, 6, 6, 6, 6]
        baselines["contributors"] = [6, 6]
    return WeeklySnapshotDocument.model_construct(
        id=PydanticObjectId(),
        project_id=project_id,
        week_start=week_start,
        week_end=week_start + timedelta(days=6),
        rule_set_version=version,
        generated_at=datetime.combine(week_start, datetime.min.time(), tzinfo=UTC),
        attention_status=status,
        data_completeness_pct=metrics.data_completeness_pct or 0,
        last_sync_at=metrics.last_sync_at,
        metrics=metrics,
        baselines=metrics if with_contributor_series else None,
        warning_ids=warning_ids or [],
        series=series,
        series_baselines=baselines,
    )


def _warning(snapshot_id: PydanticObjectId, project_id: str) -> WarningDocument:
    warning_id = PydanticObjectId()
    evidence = WarningEvidenceItem(
        evidence_type="metric",
        icon="activity",
        title="Activity below baseline",
        metric="active_days",
        current=1,
        baseline=4,
        source_refs=[
            EvidenceReference(
                source_collection="repo_activity",
                source_id="repo-activity-test",
                source_field="active_days",
                observed_at=LAST_SYNC,
            )
        ],
    )
    return WarningDocument.model_construct(
        id=warning_id,
        snapshot_id=snapshot_id,
        project_id=project_id,
        rule_id="activity_decline",
        rule_version="rules-v1",
        signal_name="Activity below baseline",
        current_value=1,
        baseline_value=4,
        time_window="trailing 8 weeks",
        trigger_threshold=4,
        severity=WarningSeverity.WARNING,
        explanation="Activity below the trailing baseline.",
        data_freshness=LAST_SYNC.isoformat(),
        data_completeness_pct=100,
        evidence=[evidence],
    )


def _add_project(api: ApiHarness, project_id: str, *, lifecycle: LifecycleState = LifecycleState.ACTIVE) -> ProjectDocument:
    project = _project(project_id, lifecycle=lifecycle)
    api.add("projects", project)
    api.add("boundaries", _boundary(project_id))
    return project


def _add_snapshot(api: ApiHarness, project_id: str, **kwargs: Any) -> WeeklySnapshotDocument:
    snapshot = _snapshot(project_id, **kwargs)
    api.add("snapshots", snapshot)
    return snapshot


def _add_history(api: ApiHarness, project_id: str, *, severe: bool = False) -> None:
    for index in range(9):
        current_week = date(2026, 6, 1) + timedelta(days=index * 7)
        api.add(
            "repo_activity",
            # The job consumes only aggregate fields from this raw evidence row.
            # No contributor identities or per-person dimensions are present.
            RepoActivityDocument.model_construct(
                project_id=project_id,
                gitea_repo_id=f"repo-{project_id}",
                repo_slug=project_id,
                window_start=current_week,
                window_end=current_week + timedelta(days=6),
                active_days=1 if severe and index == 8 else 6,
                days_since_activity=30 if severe and index == 8 else 1,
                open_prs=8 if severe and index == 8 else 1,
                oldest_open_pr_days=30 if severe and index == 8 else 2,
                review_latency_days=10 if severe and index == 8 else 2,
                merged_count=0 if severe and index == 8 else 4,
                data_completeness_pct=100,
                last_sync_at=LAST_SYNC,
            ),
        )


def test_latest_snapshot_has_the_frontend_compatible_shape_and_evidence(api: ApiHarness) -> None:
    _add_project(api, "alpha")
    snapshot = _snapshot("alpha")
    warning = _warning(snapshot.id, "alpha")
    snapshot.warning_ids = [warning.id]
    api.add("warnings", warning)
    api.add("snapshots", snapshot)

    response = api.client.get("/snapshots/latest")

    assert response.status_code == 200
    payload = response.json()
    assert {
        "snapshot_week_start",
        "snapshot_week_end",
        "generated_at",
        "rule_set_version",
        "data_completeness_pct",
        "last_sync_at",
        "projects",
    } <= payload.keys()
    project = payload["projects"][0]
    assert {
        "id",
        "name",
        "status",
        "statusClass",
        "metrics",
        "baselines",
        "boundary",
        "evidence",
        "history",
        "series",
        "seriesBaselines",
    } <= project.keys()
    assert project["id"] == "alpha"
    assert project["evidence"][0]["sourceEvidence"]
    assert payload["rule_set_version"] == "rules-v1"


def test_project_lead_can_only_read_assigned_projects(api: ApiHarness) -> None:
    _add_project(api, "alpha")
    _add_project(api, "beta")
    _add_snapshot(api, "alpha")
    _add_snapshot(api, "beta")
    api.set_user(subject="alpha-lead", roles={Role.PROJECT_LEAD}, project_ids={"alpha"})

    latest = api.client.get("/snapshots/latest")
    alpha = api.client.get("/projects/alpha/snapshots")
    beta = api.client.get("/projects/beta/snapshots")
    boundaries = api.client.get("/boundaries")

    assert latest.status_code == 200
    assert [project["id"] for project in latest.json()["projects"]] == ["alpha"]
    assert alpha.status_code == 200
    assert beta.status_code == 403
    assert boundaries.status_code == 403


def test_non_admin_response_contains_no_individual_contributor_keys(api: ApiHarness) -> None:
    _add_project(api, "alpha")
    _add_snapshot(api, "alpha")

    payload = api.client.get("/snapshots/latest").json()
    def all_keys(value: Any) -> set[str]:
        found: set[str] = set()
        if isinstance(value, dict):
            for key, child in value.items():
                found.add(str(key).lower().replace("_", ""))
                found.update(all_keys(child))
        elif isinstance(value, list):
            for child in value:
                found.update(all_keys(child))
        return found

    keys = all_keys(payload)
    forbidden = {
        "contributorid",
        "contributorids",
        "contributoridentities",
        "identityref",
        "identityrefs",
        "giteausername",
        "giteausernames",
        "percontributormetrics",
        "commitsbyuser",
        "additionsbyuser",
        "deletionsbyuser",
    }
    assert keys.isdisjoint(forbidden)
    # The aggregate count is allowed here because the team is above the floor.
    assert payload["projects"][0]["metrics"]["active_contributors"] == 6


def test_aggregation_floor_omits_contributor_fields_entirely(api: ApiHarness) -> None:
    _add_project(api, "small-team")
    _add_snapshot(
        api,
        "small-team",
        metrics=_metrics(contributors=None),
        with_contributor_series=False,
    )

    project = api.client.get("/snapshots/latest").json()["projects"][0]

    assert "active_contributors" not in project["metrics"]
    assert "active_contributors" not in (project.get("baselines") or {})
    assert "contributors" not in project["series"]
    assert "contributors" not in project["seriesBaselines"]
    assert "team_size" not in json.dumps(project)


def test_warning_requires_inspectable_source_evidence(api: ApiHarness) -> None:
    with pytest.raises(ValidationError):
        WarningDocument.model_validate(
            {
                "id": PydanticObjectId(),
                "snapshot_id": PydanticObjectId(),
                "project_id": "alpha",
                "rule_id": "activity_decline",
                "rule_version": "rules-v1",
                "signal_name": "Activity below baseline",
                "time_window": "trailing 8 weeks",
                "severity": WarningSeverity.WARNING,
                "explanation": "Missing evidence must be rejected.",
                "data_freshness": LAST_SYNC.isoformat(),
                "data_completeness_pct": 100,
                "evidence": [
                    {
                        "type": "metric",
                        "icon": "activity",
                        "title": "Activity below baseline",
                        "sourceEvidence": [],
                    }
                ],
            }
        )

    _add_project(api, "alpha")
    snapshot = _snapshot("alpha")
    warning = _warning(snapshot.id, "alpha")
    snapshot.warning_ids = [warning.id]
    api.add("warnings", warning)
    api.add("snapshots", snapshot)
    response = api.client.get("/snapshots/latest")
    assert response.status_code == 200
    assert all(item["sourceEvidence"] for item in response.json()["projects"][0]["evidence"])


def test_planned_pause_suppresses_signals_and_warnings(api: ApiHarness) -> None:
    _add_project(api, "paused-project", lifecycle=LifecycleState.PAUSED)
    _add_history(api, "paused-project", severe=True)

    created = asyncio.run(
        generate_weekly_snapshots(
            settings=api.settings,
            database=store,
            week_start=WEEK_START,
            rule_set_version="rules-v1",
        )
    )
    snapshot = store.snapshots[-1]

    assert created == 1
    assert snapshot.attention_status == AttentionStatus.PLANNED_PAUSE
    assert snapshot.warning_ids == []
    assert store.warnings == []
    project = api.client.get("/snapshots/latest").json()["projects"][0]
    assert project["status"] == "Planned pause"
    assert project["evidence"] == []


def test_rerunning_rules_appends_versioned_immutable_snapshots(api: ApiHarness) -> None:
    _add_project(api, "alpha")
    _add_history(api, "alpha")

    asyncio.run(
        generate_weekly_snapshots(
            settings=api.settings,
            database=store,
            week_start=WEEK_START,
            rule_set_version="rules-v1",
        )
    )
    first = store.snapshots[0]
    first_payload = first.model_dump(mode="json")

    with pytest.raises(ImmutableSnapshotError):
        asyncio.run(first.replace())
    with pytest.raises(ImmutableSnapshotError):
        asyncio.run(first.update())

    asyncio.run(
        generate_weekly_snapshots(
            settings=api.settings,
            database=store,
            week_start=WEEK_START,
            rule_set_version="rules-v2",
        )
    )

    assert len(store.snapshots) == 2
    assert {snapshot.rule_set_version for snapshot in store.snapshots} == {"rules-v1", "rules-v2"}
    assert store.snapshots[0].id != store.snapshots[1].id
    assert store.snapshots[0].model_dump(mode="json") == first_payload


def test_rerunning_the_same_rule_version_is_idempotent(api: ApiHarness) -> None:
    _add_project(api, "alpha")
    _add_history(api, "alpha")

    first = asyncio.run(
        generate_weekly_snapshots(
            settings=api.settings,
            database=store,
            week_start=WEEK_START,
            rule_set_version="rules-v1",
        )
    )
    second = asyncio.run(
        generate_weekly_snapshots(
            settings=api.settings,
            database=store,
            week_start=WEEK_START,
            rule_set_version="rules-v1",
        )
    )

    assert first == 1
    assert second == 0
    assert len(store.snapshots) == 1


def test_feedback_write_also_creates_audit_event(api: ApiHarness) -> None:
    _add_project(api, "alpha")
    snapshot = _add_snapshot(api, "alpha")
    api.set_user(subject="alpha-lead", roles={Role.PROJECT_LEAD}, project_ids={"alpha"})

    response = api.client.post(
        "/feedback",
        json={
            "snapshot_id": str(snapshot.id),
            "project_id": "alpha",
            "category": "risk_confirmed",
            "note": "The review queue is being actively worked.",
        },
    )

    assert response.status_code == 201
    assert len(store.feedback) == 1
    assert len(store.audit_log) == 1
    assert store.audit_log[0].action == "feedback.created"
    assert store.audit_log[0].after["snapshot_id"] == str(snapshot.id)
    audit = api.client.get("/audit", params={"project_id": "alpha"})
    assert audit.status_code == 200
    assert audit.json()[0]["action"] == "feedback.created"
    assert audit.json()[0]["actor_user_id"] == "Reviewer"


def test_boundary_versions_preserve_historical_snapshot_resolution(api: ApiHarness) -> None:
    _add_project(api, "alpha")
    old_snapshot = _add_snapshot(api, "alpha", week_start=date(2026, 6, 1))
    api.set_user(subject="admin", roles={Role.ADMIN})

    response = api.client.post(
        "/boundaries",
        json={
            "project_id": "alpha",
            "root_authentik_team_id": "team-new",
            "included_subteam_ids": ["subteam-new"],
            "primary_repos": [{"gitea_repo_id": "repo-new", "repo_slug": "repo-new"}],
            "effective_from": "2026-07-01",
        },
    )
    assert response.status_code == 201

    new_snapshot = _add_snapshot(api, "alpha", week_start=date(2026, 8, 3), version="rules-v2")
    assert old_snapshot.id != new_snapshot.id
    boundaries = [row for row in store.boundaries if row.project_id == "alpha"]
    assert len(boundaries) == 2
    old_at_handoff = asyncio.run(store.boundary_at("alpha", date(2026, 6, 30)))
    new_after_handoff = asyncio.run(store.boundary_at("alpha", date(2026, 7, 2)))
    assert old_at_handoff is not None
    assert new_after_handoff is not None
    assert old_at_handoff.root_authentik_team_id == "team-old"
    assert new_after_handoff.root_authentik_team_id == "team-new"

    response = api.client.get("/projects/alpha/snapshots")
    assert response.status_code == 200
    by_week = {item["snapshot_week_start"]: item["project"] for item in response.json()["snapshots"]}
    assert by_week["2026-06-01"]["boundary"]["rootTeam"] == "team-old"
    assert by_week["2026-08-03"]["boundary"]["rootTeam"] == "team-new"
