"""Aggregate-only local fixtures for running the disconnected UI against FastAPI."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from beanie import PydanticObjectId

from .config import get_settings
from .db import get_db_state, init_db
from .models import (
    AggregateMetrics,
    AttentionStatus,
    AuditLogDocument,
    BoundaryDocument,
    EvidenceReference,
    FeedbackCategory,
    FeedbackDocument,
    IdentityMapDocument,
    LifecycleState,
    ProjectDocument,
    RepoActivityDocument,
    RepositoryRef,
    WarningDocument,
    WarningEvidenceItem,
    WarningSeverity,
    WeeklySnapshotDocument,
    utc_now,
)

WEEK_START = date(2026, 8, 3)
WEEK_END = date(2026, 8, 9)
GENERATED_AT = datetime(2026, 8, 3, 13, 34, tzinfo=timezone.utc)
LAST_SYNC = datetime(2026, 8, 3, 13, 8, tzinfo=timezone.utc)


def _oid(number: int) -> PydanticObjectId:
    return PydanticObjectId(f"{number:024x}")


def _doc(model: Any, **values: Any) -> Any:
    """Construct Beanie documents without requiring a live Motor collection."""
    return model.model_construct(**values)


def build_safe_demo_project(project_id: str = "demo-project") -> ProjectDocument:
    return _doc(ProjectDocument, project_id=project_id, display_name="Demo Project", lifecycle_state=LifecycleState.ACTIVE, non_goals_ack=True)


def build_safe_demo_boundary(project_id: str = "demo-project") -> BoundaryDocument:
    return _doc(BoundaryDocument, project_id=project_id, root_authentik_team_id="team-demo", primary_repos=[RepositoryRef(gitea_repo_id="repo-demo", repo_slug=project_id)], effective_from=date.today() - timedelta(days=90), created_by="seed")


def build_safe_demo_activity(project_id: str = "demo-project") -> RepoActivityDocument:
    return _doc(RepoActivityDocument, project_id=project_id, gitea_repo_id=f"repo-{project_id}", repo_slug=project_id, window_start=WEEK_START, window_end=WEEK_END, synced_at=LAST_SYNC, active_days=4, days_since_activity=1, open_prs=2, oldest_open_pr_days=3, review_latency_days=1.5, merged_count=3, active_contributors=2, team_size=max(get_settings().aggregation_floor, 6), aggregation_floor=get_settings().aggregation_floor, data_completeness_pct=100, last_sync_at=LAST_SYNC)


async def _insert(document: Any) -> Any:
    state = get_db_state()
    if state.repository is not None:
        return await state.repository.insert(document)
    return await document.insert()


def _specs() -> list[dict[str, Any]]:
    common: dict[str, Any] = {}
    return [
        dict(id="member-portal", name="Member Portal", short="MP", team="Product Experience", repo="member-portal", status=AttentionStatus.AT_RISK, signal="PR review queue is aging", detail="4 PRs · oldest 18 days", last="Yesterday", lifecycle=LifecycleState.ACTIVE, root="product-experience", subteams=["member-portal-core", "growth"], repos=["member-portal", "member-portal-api"], owner="priya-n", metrics=dict(active_days=1, days_since_activity=1, open_prs=4, oldest_open_pr_days=18, review_latency_days=5.4, merged_count=1, active_contributors=2, team_size=8), series=dict(activity=[6, 5, 5, 4, 4, 2, 1, 1], open_prs=[1, 1, 2, 2, 2, 3, 3, 4], review_latency=[2.1, 2.4, 2.8, 3.1, 3.4, 4.3, 4.9, 5.4], contributors=[5, 5, 4, 4, 3, 3, 2, 2]), baselines=dict(open_prs=[1, 4], review_latency=[2.1, 5.4], contributors=[5, 2]), warnings=[("open_pr_aging", "Pull requests aging", "open_prs", 4, 1, WarningSeverity.CRITICAL), ("activity_decline", "Activity below baseline", "active_days", 1, 4, WarningSeverity.WARNING), ("contributor_resilience", "Concentrated contributors", "active_contributors", 2, 5, WarningSeverity.WARNING)], **common),
        dict(id="campus-events", name="Campus Events", short="CE", team="Community Programs", repo="campus-events", status=AttentionStatus.WATCH, signal="Review latency is rising", detail="6.2 days · +2.1 vs baseline", last="Today", lifecycle=LifecycleState.ACTIVE, root="community-programs", subteams=["events-ops"], repos=["campus-events"], owner="marcus-t", metrics=dict(active_days=4, days_since_activity=0, open_prs=2, oldest_open_pr_days=6, review_latency_days=6.2, merged_count=3, active_contributors=4, team_size=7), series=dict(activity=[4, 4, 4, 5, 4, 3, 3, 4], open_prs=[2, 2, 2, 1, 2, 2, 2, 2], review_latency=[4.1, 4.0, 4.3, 4.5, 4.8, 5.2, 5.8, 6.2], contributors=[4, 4, 4, 5, 4, 4, 4, 4]), baselines=dict(open_prs=[2, 3], review_latency=[4.1, 6.2], contributors=[4, 4]), warnings=[("review_latency", "Review latency rising", "review_latency_days", 6.2, 4.1, WarningSeverity.WARNING)], **common),
        dict(id="design-system", name="Design System", short="DS", team="Platform Experience", repo="design-system", status=AttentionStatus.WATCH, signal="Contributor count dipped", detail="3 → 1 active contributors", last="2 days ago", lifecycle=LifecycleState.ACTIVE, root="platform-experience", subteams=["design-systems-guild"], repos=["design-system", "design-tokens"], owner="alex-r", metrics=dict(active_days=2, days_since_activity=2, open_prs=1, oldest_open_pr_days=2, review_latency_days=1.8, merged_count=1, active_contributors=1, team_size=6), series=dict(activity=[5, 5, 5, 4, 4, 3, 2, 2], open_prs=[1, 1, 1, 1, 1, 1, 1, 1], review_latency=[1.8, 1.8, 1.9, 1.7, 1.8, 1.8, 1.7, 1.8], contributors=[3, 3, 3, 2, 2, 2, 1, 1]), baselines=dict(open_prs=[1, 1], review_latency=[1.8, 1.8], contributors=[3, 1]), warnings=[("contributor_resilience", "Contributor count dipped", "active_contributors", 1, 3, WarningSeverity.WARNING)], **common),
        dict(id="alumni-network", name="Alumni Network", short="AN", team="Community Programs", repo="alumni-network", status=AttentionStatus.CLEAR, signal="No current concern detected", detail="12 active days · steady flow", last="Today", lifecycle=LifecycleState.ACTIVE, root="community-programs", subteams=["alumni-relations"], repos=["alumni-network"], owner="marcus-t", metrics=dict(active_days=12, days_since_activity=0, open_prs=1, oldest_open_pr_days=1, review_latency_days=1.2, merged_count=4, active_contributors=5, team_size=8), series=dict(activity=[4, 4, 5, 5, 6, 7, 7, 7], open_prs=[1, 1, 1, 1, 1, 1, 1, 1], review_latency=[1.5, 1.5, 1.4, 1.4, 1.5, 1.3, 1.3, 1.2], contributors=[4, 4, 4, 4, 4, 5, 5, 5]), baselines=dict(open_prs=[1, 2], review_latency=[1.5, 1.2], contributors=[4, 5]), warnings=[], **common),
        dict(id="onboarding", name="Onboarding Refresh", short="OR", team="People Operations", repo="onboarding-refresh", status=AttentionStatus.CLEAR, signal="No current concern detected", detail="9 active days · 3 PRs merged", last="Today", lifecycle=LifecycleState.ACTIVE, root="people-operations", subteams=["member-experience"], repos=["onboarding-refresh"], owner="priya-n", metrics=dict(active_days=9, days_since_activity=0, open_prs=1, oldest_open_pr_days=1, review_latency_days=.9, merged_count=3, active_contributors=3, team_size=5), series=dict(activity=[3, 3, 4, 4, 4, 5, 5, 6], open_prs=[1, 1, 1, 1, 1, 1, 1, 1], review_latency=[1.1, 1.1, 1.0, 1.0, 1.0, .9, .9, .9], contributors=[2, 2, 2, 2, 2, 3, 3, 3]), baselines=dict(open_prs=[1, 1], review_latency=[1.1, .9], contributors=[2, 3]), warnings=[], **common),
        dict(id="mobile-lab", name="Mobile Lab", short="ML", team="Innovation Studio", repo="mobile-lab", status=AttentionStatus.INSUFFICIENT_DATA, signal="Repository mapping incomplete", detail="Ownership review required", last="11 days ago", lifecycle=LifecycleState.NEW, root="innovation-studio", subteams=["mobile-spikes"], repos=["mobile-lab", "mobile-lab-experiments (unmapped)"], owner=None, metrics=dict(active_days=1, days_since_activity=11, data_completeness_pct=62), series=dict(activity=[2, 1, None, None, 2, None, None, 1], open_prs=[None] * 8, review_latency=[None] * 8, contributors=[None] * 8), baselines=dict(open_prs=[None, None], review_latency=[None, None], contributors=[None, None]), warnings=[], completeness=62, **common),
        dict(id="winter-campaign", name="Winter Campaign", short="WC", team="Marketing", repo="winter-campaign", status=AttentionStatus.PLANNED_PAUSE, signal="Inactivity is expected", detail="Pause recorded through Aug 20", last="16 days ago", lifecycle=LifecycleState.PAUSED, root="marketing", subteams=[], repos=["winter-campaign"], owner="sam-d", metrics=dict(active_days=0, days_since_activity=16, open_prs=0, merged_count=0), series=dict(activity=[4, 3, 1, 0, 0, 0, 0, 0], open_prs=[1, 1, 0, 0, 0, 0, 0, 0], review_latency=[None] * 8, contributors=[None] * 8), baselines=dict(open_prs=[1, 0], review_latency=[None, None], contributors=[None, None]), warnings=[], **common),
    ]


async def seed_demo_data() -> dict[str, str]:
    settings = get_settings()
    if not settings.allows_dev_auth:
        return {"status": "disabled"}
    try:
        state = get_db_state()
    except RuntimeError:
        await init_db(settings)
        state = get_db_state()
    repository = state.repository
    existing = await repository.list("projects") if repository is not None else await ProjectDocument.find_all().to_list()
    if existing:
        return {"status": "already_seeded"}
    if repository is not None:
        await repository.insert(_doc(IdentityMapDocument))
    first_snapshot = ""
    for index, spec in enumerate(_specs(), start=1):
        project = _doc(ProjectDocument, project_id=spec["id"], display_name=spec["name"], lifecycle_state=spec["lifecycle"], data_owner_user_id=spec["owner"], non_goals_ack=True)
        boundary = _doc(BoundaryDocument, project_id=spec["id"], root_authentik_team_id=spec["root"], included_subteam_ids=spec["subteams"], primary_repos=[RepositoryRef(gitea_repo_id=repo, repo_slug=repo) for repo in spec["repos"] if "unmapped" not in repo], effective_from=WEEK_START if spec["id"] == "mobile-lab" else date(2026, 1, 1), data_owner_user_id=spec["owner"], created_by="seed")
        completeness = spec.get("completeness", 97)
        activity = _doc(RepoActivityDocument, id=_oid(1000 + index), project_id=spec["id"], gitea_repo_id=f"repo-{spec['id']}", repo_slug=spec["repo"], window_start=WEEK_START, window_end=WEEK_END, synced_at=LAST_SYNC, **{key: value for key, value in spec["metrics"].items() if key in RepoActivityDocument.model_fields and key != "data_completeness_pct"}, data_completeness_pct=completeness, last_sync_at=LAST_SYNC)
        snapshot_id = _oid(index)
        warning_ids: list[PydanticObjectId] = []
        for warning_index, (rule_id, title, metric, current, baseline, severity) in enumerate(spec["warnings"], start=1):
            warning_id = _oid(index * 100 + warning_index)
            warning_ids.append(warning_id)
            evidence = WarningEvidenceItem(evidence_type="metric", icon="pull" if "PR" in title or "review" in title.lower() else "users" if "contributor" in title.lower() else "activity", title=title, metric=metric, unit="d" if "latency" in title.lower() else "", current=current, baseline=baseline, source_refs=[EvidenceReference(source_collection="repo_activity", source_id=str(activity.id), source_field=metric, observed_at=LAST_SYNC)])
            warning = _doc(WarningDocument, id=warning_id, snapshot_id=snapshot_id, project_id=spec["id"], rule_id=rule_id, rule_version=settings.rule_set_version, signal_name=title, current_value=current, baseline_value=baseline, time_window="trailing 8 weeks", trigger_threshold="project baseline deviation", severity=severity, explanation=f"{title} is outside the project's trailing baseline.", caveats=["Conversation prompt only; not an individual performance measure."], data_freshness=LAST_SYNC.isoformat(), data_completeness_pct=completeness, evidence=[evidence])
            if repository is not None:
                await repository.insert(warning)
            else:
                await warning.insert()
        metric_values = {key: value for key, value in spec["metrics"].items() if key != "data_completeness_pct"}
        metrics = AggregateMetrics(**metric_values, data_completeness_pct=completeness, last_sync_at=LAST_SYNC)
        baselines = AggregateMetrics(open_prs=spec["baselines"]["open_prs"][0], review_latency_days=spec["baselines"]["review_latency"][0], active_contributors=spec["baselines"]["contributors"][0], team_size=spec["metrics"].get("team_size"), aggregation_floor=settings.aggregation_floor, data_completeness_pct=completeness, last_sync_at=LAST_SYNC)
        snapshot = _doc(WeeklySnapshotDocument, id=snapshot_id, project_id=spec["id"], week_start=WEEK_START, week_end=WEEK_END, rule_set_version=settings.rule_set_version, generated_at=GENERATED_AT, attention_status=spec["status"], data_completeness_pct=completeness, last_sync_at=LAST_SYNC, metrics=metrics, baselines=baselines, warning_ids=warning_ids, series=spec["series"], series_baselines=spec["baselines"])
        if repository is not None:
            await repository.insert(project); await repository.insert(boundary); await repository.insert(activity); await repository.insert(snapshot)
        else:
            await project.insert(); await boundary.insert(); await activity.insert(); await snapshot.insert()
        if not first_snapshot: first_snapshot = str(snapshot.id)
    feedback = _doc(FeedbackDocument, id=_oid(900), snapshot_id=_oid(1), warning_id=_oid(101), project_id="member-portal", author_user_id="jordan-kim", category=FeedbackCategory.RISK_CONFIRMED, note="Reviewer bandwidth is being backfilled.", created_at=datetime(2026, 7, 27, 15, tzinfo=timezone.utc))
    audit = _doc(AuditLogDocument, actor_user_id="jordan-kim", action="feedback.created", target_type="feedback", target_id=str(feedback.id), after={"project_id": "member-portal", "category": "risk_confirmed"}, at=datetime(2026, 7, 27, 15, tzinfo=timezone.utc))
    if repository is not None:
        await repository.insert(feedback); await repository.insert(audit)
    else:
        await feedback.insert(); await audit.insert()
    return {"status": "seeded", "snapshot_id": first_snapshot}
