from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from .auth import AuthUser, get_current_user, require_project_access, require_roles, visible_project_ids
from .config import Settings, get_settings
from .db import get_active_repository
from .models import (
    AttentionStatus,
    AuditLogDocument,
    BoundaryDocument,
    BoundaryView,
    FeedbackCategory,
    FeedbackDocument,
    ProjectResponse,
    PublicAggregateMetrics,
    RepositoryRef,
    Role,
    WarningDocument,
    WeeklySnapshotDocument,
)
from .rules import RULES

router = APIRouter()


def _db() -> Any:
    return get_active_repository()


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    warning_id: str | None = None
    project_id: str
    category: FeedbackCategory
    note: str | None = Field(default=None, max_length=2_000)


class BoundaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    root_authentik_team_id: str
    included_subteam_ids: list[str] = Field(default_factory=list)
    primary_repos: list[RepositoryRef] = Field(default_factory=list)
    effective_from: date
    data_owner_user_id: str | None = None


def _id(value: Any) -> str:
    return str(value)


def _pretty_status(value: AttentionStatus) -> tuple[str, str]:
    return {
        AttentionStatus.AT_RISK: ("At risk", "risk"),
        AttentionStatus.WATCH: ("Watch", "watch"),
        AttentionStatus.CLEAR: ("Clear", "clear"),
        AttentionStatus.INSUFFICIENT_DATA: ("Insufficient data", "data"),
        AttentionStatus.PLANNED_PAUSE: ("Planned pause", "pause"),
    }[value]


def _snapshot_id(snapshot: WeeklySnapshotDocument) -> str:
    return _id(snapshot.id)


async def _accessible_project(user: AuthUser, project_id: str) -> Any:
    if not user.can_view_portfolio and project_id not in user.project_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="project access denied")
    project = await _db().get_project(project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    return project


async def _warnings_for(snapshot_id: str) -> list[WarningDocument]:
    return await _db().warnings_for_snapshot(snapshot_id)


def _boundary_view(boundary: BoundaryDocument | None, project: Any) -> dict[str, Any]:
    if boundary is None:
        return {"rootTeam": "Unassigned", "subteams": [], "repos": [], "dataOwner": None, "effectiveSince": None, "lifecycle": project.lifecycle_state.value}
    repositories = [item.repo_slug for item in boundary.primary_repos]
    repositories.extend(item.repo_slug for shared in boundary.shared_repos for item in [shared])
    return {
        "rootTeam": boundary.root_authentik_team_id,
        "subteams": boundary.included_subteam_ids,
        "repos": repositories,
        "dataOwner": boundary.data_owner_user_id,
        "effectiveSince": boundary.effective_from,
        "effectiveUntil": boundary.effective_to,
        "lifecycle": project.lifecycle_state.value,
        "version": f"{boundary.project_id}:{boundary.effective_from.isoformat()}",
    }


async def _history(project_id: str) -> list[dict[str, Any]]:
    items = [item for item in await _db().list("feedback") if item.project_id == project_id]
    items.sort(key=lambda item: item.created_at, reverse=True)
    return [
        {"date": item.created_at, "actor": "Reviewer", "action": item.category.value.replace("_", " ").title(), "note": item.note or ""}
        for item in items
    ]


def _series_baselines(snapshot: WeeklySnapshotDocument) -> dict[str, list[Any]]:
    if snapshot.series_baselines:
        result = {
            "openPRs": snapshot.series_baselines.get("open_prs", snapshot.series_baselines.get("openPRs", [None, None])),
            "reviewLatency": snapshot.series_baselines.get("review_latency", snapshot.series_baselines.get("reviewLatency", [None, None])),
            "contributors": snapshot.series_baselines.get("contributors", [None, None]),
        }
        if snapshot.metrics.active_contributors is None:
            result["contributors"] = None
        return result
    baseline = snapshot.baselines
    metrics = snapshot.metrics
    result = {
        "openPRs": [baseline.open_prs if baseline else None, metrics.open_prs],
        "reviewLatency": [baseline.review_latency_days if baseline else None, metrics.review_latency_days],
        "contributors": [baseline.active_contributors if baseline else None, metrics.active_contributors],
    }
    if snapshot.metrics.active_contributors is None:
        result["contributors"] = None
    return result


async def _project_response(project: Any, snapshot: WeeklySnapshotDocument | None) -> dict[str, Any]:
    if snapshot is None:
        status_value, status_class = "Insufficient data", "data"
        return ProjectResponse(
            id=project.project_id, name=project.display_name, short=project.display_name[:2].upper(), team="Unassigned", repo="—",
            status=status_value, statusClass=status_class, signal="No snapshot available", signalDetail="Data is not yet sufficient for a trusted assessment.", lastActivity="—", trend="flat", weeks=[None] * 8,
            flagFrom=99, seriesBaselines={"openPRs": [None, None], "reviewLatency": [None, None], "contributors": None}, series={"activity": [None] * 8, "openPRs": [None] * 8, "reviewLatency": [None] * 8, "contributors": None}, description="", boundary=BoundaryView(rootTeam="Unassigned", lifecycle=project.lifecycle_state.value), history=await _history(project.project_id), snapshot_id=None,
        ).model_dump(mode="json", by_alias=True, exclude_none=True)

    status_value, status_class = _pretty_status(snapshot.attention_status)
    warnings = await _warnings_for(_snapshot_id(snapshot))
    evidence: list[dict[str, Any]] = []
    for warning in warnings:
        for item in warning.evidence:
            payload = item.model_dump(mode="json", by_alias=True, exclude_none=True)
            payload["warning_id"] = _id(warning.id)
            payload["sourceEvidence"] = [ref.model_dump(mode="json") for ref in item.source_refs]
            evidence.append(payload)
    boundary = await _db().boundary_at(project.project_id, snapshot.week_start)
    metrics = PublicAggregateMetrics.from_metrics(snapshot.metrics).model_dump(mode="json", exclude_none=True)
    baselines = PublicAggregateMetrics.from_metrics(snapshot.baselines).model_dump(mode="json", exclude_none=True) if snapshot.baselines else None
    series = snapshot.series or {"activity": [None] * 8, "open_prs": [None] * 8, "review_latency": [None] * 8, "contributors": [None] * 8}
    contributor_series = series.get("contributors", [None] * 8) if snapshot.metrics.active_contributors is not None else None
    current_active_days = snapshot.metrics.active_days
    days_since_activity = snapshot.metrics.days_since_activity
    last_activity = "—" if days_since_activity is None else "Today" if days_since_activity == 0 else "Yesterday" if days_since_activity == 1 else f"{days_since_activity} days ago"
    first_warning = warnings[0].signal_name if warnings else ("Inactivity is expected" if snapshot.attention_status == AttentionStatus.PLANNED_PAUSE else "No current concern detected" if snapshot.attention_status == AttentionStatus.CLEAR else "Repository mapping incomplete" if snapshot.attention_status == AttentionStatus.INSUFFICIENT_DATA else "Review current project signals")
    detail = warnings[0].explanation if warnings else ("Pause recorded; signals are suppressed." if snapshot.attention_status == AttentionStatus.PLANNED_PAUSE else "Ownership review required" if snapshot.attention_status == AttentionStatus.INSUFFICIENT_DATA else "Available project aggregates are within the current rule set.")
    weeks = list(series.get("activity", [None] * 8))[-8:]
    weeks = [None] * (8 - len(weeks)) + weeks
    return ProjectResponse(
        id=project.project_id, name=project.display_name, short=project.display_name[:2].upper(), team=boundary.root_authentik_team_id if boundary else "Unassigned", repo=boundary.primary_repos[0].repo_slug if boundary and boundary.primary_repos else "—",
        status=status_value, statusClass=status_class, signal=first_warning, signalDetail=detail, lastActivity=last_activity, trend="down" if status_class in {"risk", "watch"} else "flat", weeks=weeks,
        flagFrom=5 if status_class == "risk" else 6 if status_class == "watch" else 99, seriesBaselines=_series_baselines(snapshot), series={"activity": series.get("activity", [None] * 8), "openPRs": series.get("openPRs", series.get("open_prs", [None] * 8)), "reviewLatency": series.get("review_latency", series.get("reviewLatency", series.get("review_latency_days", [None] * 8))), "contributors": contributor_series}, description="", boundary=_boundary_view(boundary, project), evidence=evidence, history=await _history(project.project_id), metrics=metrics, baselines=baselines, data_completeness_pct=snapshot.data_completeness_pct, last_sync_at=snapshot.last_sync_at, snapshot_id=_snapshot_id(snapshot),
    ).model_dump(mode="json", by_alias=True, exclude_none=True)


def _snapshot_envelope(snapshots: list[WeeklySnapshotDocument], projects: list[dict[str, Any]]) -> dict[str, Any]:
    latest = max(snapshots, key=lambda item: (item.week_start, item.generated_at), default=None)
    if latest is None:
        now = datetime.now(timezone.utc)
        return {"snapshot_week_start": None, "snapshot_week_end": None, "generated_at": now, "rule_set_version": "none", "data_completeness_pct": 0, "last_sync_at": None, "projects": projects}
    completeness = round(sum(item.data_completeness_pct for item in snapshots) / len(snapshots), 1) if snapshots else 0
    return {"snapshot_week_start": latest.week_start, "snapshot_week_end": latest.week_end, "generated_at": latest.generated_at, "rule_set_version": latest.rule_set_version, "data_completeness_pct": completeness, "last_sync_at": latest.last_sync_at, "projects": projects}


@router.get("/health")
async def health(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return {
        "status": "ok",
        "environment": settings.environment,
        "mongo_configured": bool(settings.mongo_uri),
        "directory_source": "people_portal" if settings.people_portal_url else "authentik" if settings.authentik_url else None,
        "people_portal_configured": bool(settings.people_portal_url),
        "outbound_notifications": False,
    }


@router.get("/snapshots/latest")
async def latest_snapshot(user: AuthUser = Depends(get_current_user)) -> dict[str, Any]:
    database = _db()
    all_projects = await database.list("projects")
    ids = visible_project_ids(user, [project.project_id for project in all_projects])
    items: list[dict[str, Any]] = []
    snapshots: list[WeeklySnapshotDocument] = []
    for project_id in ids:
        snapshot = await database.latest_snapshot(project_id)
        if snapshot:
            snapshots.append(snapshot)
        project = await database.get_project(project_id)
        if project:
            items.append(await _project_response(project, snapshot))
    return _snapshot_envelope(snapshots, items)


@router.get("/projects/{project_id}/snapshots")
async def project_snapshots(project_id: str, user: AuthUser = Depends(require_project_access)) -> dict[str, Any]:
    project = await _accessible_project(user, project_id)
    rows = sorted([row for row in await _db().list("snapshots") if row.project_id == project_id], key=lambda row: (row.week_start, row.generated_at), reverse=True)
    payload = []
    for snapshot in rows:
        project_payload = await _project_response(project, snapshot)
        payload.append({"snapshot_id": _snapshot_id(snapshot), "snapshot_week_start": snapshot.week_start, "snapshot_week_end": snapshot.week_end, "generated_at": snapshot.generated_at, "rule_set_version": snapshot.rule_set_version, "data_completeness_pct": snapshot.data_completeness_pct, "last_sync_at": snapshot.last_sync_at, "project": project_payload})
    return {"project_id": project_id, "snapshots": payload}


@router.get("/projects/{project_id}/boundary")
async def project_boundary(project_id: str, user: AuthUser = Depends(require_project_access)) -> dict[str, Any]:
    project = await _accessible_project(user, project_id)
    boundary = await _db().boundary_at(project_id)
    return {"project_id": project_id, "boundary": _boundary_view(boundary, project)}


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
async def create_feedback(request: FeedbackRequest, user: AuthUser = Depends(get_current_user)) -> dict[str, Any]:
    await _accessible_project(user, request.project_id)
    try:
        snapshot_oid = PydanticObjectId(request.snapshot_id)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="snapshot_id is invalid") from exc
    snapshot = await _db().snapshot_by_id(request.snapshot_id)
    if snapshot is None or snapshot.project_id != request.project_id or snapshot_oid != snapshot.id:
        raise HTTPException(status_code=404, detail="snapshot not found for project")
    warning_oid = None
    if request.warning_id:
        try:
            warning_oid = PydanticObjectId(request.warning_id)
        except Exception as exc:
            raise HTTPException(status_code=422, detail="warning_id is invalid") from exc
        warning = await _db().warning_by_id(request.warning_id)
        if warning is None or warning.snapshot_id != snapshot.id:
            raise HTTPException(status_code=404, detail="warning not found for snapshot")
    feedback = FeedbackDocument.model_construct(id=PydanticObjectId(), snapshot_id=snapshot.id, warning_id=warning_oid, project_id=request.project_id, author_user_id=user.subject, category=request.category, note=request.note, created_at=datetime.now(timezone.utc))
    await _db().add("feedback", feedback)
    audit = AuditLogDocument.model_construct(actor_user_id=user.subject, action="feedback.created", target_type="feedback", target_id=_id(feedback.id), after={"project_id": request.project_id, "snapshot_id": request.snapshot_id, "warning_id": request.warning_id, "category": request.category.value}, at=datetime.now(timezone.utc))
    await _db().add("audit_log", audit)
    return {"id": _id(feedback.id), "snapshot_id": request.snapshot_id, "project_id": request.project_id, "category": request.category.value, "created_at": feedback.created_at}


@router.get("/audit")
async def audit_log(project_id: str | None = Query(default=None), limit: int = Query(default=100, ge=1, le=500), user: AuthUser = Depends(get_current_user)) -> list[dict[str, Any]]:
    rows = list(await _db().list("audit_log"))
    if not user.can_view_portfolio:
        visible = set(user.project_ids)
        rows = [row for row in rows if (row.after or {}).get("project_id") in visible]
    if project_id:
        if not user.can_view_portfolio and project_id not in user.project_ids:
            raise HTTPException(status_code=403, detail="project access denied")
        rows = [row for row in rows if (row.after or {}).get("project_id") == project_id]
    rows.sort(key=lambda row: row.at, reverse=True)
    return [{"id": _id(row.id), "actor_user_id": "Reviewer" if not user.is_admin else row.actor_user_id, "action": row.action, "target_type": row.target_type, "target_id": row.target_id, "before": row.before, "after": row.after, "at": row.at} for row in rows[:limit]]


@router.get("/rules")
async def rules(settings: Settings = Depends(get_settings), user: AuthUser = Depends(get_current_user)) -> dict[str, Any]:
    if not user.can_view_portfolio and not user.project_ids:
        raise HTTPException(status_code=403, detail="insufficient role")
    descriptions = {
        "activity_decline": ("Activity decline", "active days fall below the trailing median", "watch"),
        "open_pr_aging": ("Open PR aging", "oldest open PR exceeds the trailing 75th percentile", "at_risk"),
        "review_latency": ("Review latency", "review latency exceeds the trailing 75th percentile", "watch"),
        "merged_throughput": ("Merged throughput", "merged PR volume falls below the trailing 25th percentile", "watch"),
        "inactivity": ("Inactivity", "days since activity exceeds the trailing 75th percentile", "watch"),
        "contributor_resilience": ("Contributor resilience", "aggregate active contributor count falls below the trailing 25th percentile", "watch"),
    }
    return {"rule_set_version": settings.rule_set_version, "rules": [{"rule_id": rule_id, "version": settings.rule_set_version, "signal_name": descriptions.get(rule_id, (rule_id, "", "watch"))[0], "description": descriptions.get(rule_id, ("", "", ""))[1], "minimum_data": "at least 4 trailing observations", "threshold": descriptions.get(rule_id, ("", "", ""))[1], "severity": descriptions.get(rule_id, ("", "", "watch"))[2], "status": "Active"} for rule_id in RULES]}


@router.get("/boundaries")
async def boundaries(user: AuthUser = Depends(require_roles(Role.ADMIN, Role.PORTFOLIO_LEADER))) -> list[dict[str, Any]]:
    rows = await _db().list("boundaries")
    return [row.model_dump(mode="json", exclude_none=True) for row in sorted(rows, key=lambda item: (item.project_id, item.effective_from), reverse=True)]


@router.post("/boundaries", status_code=status.HTTP_201_CREATED)
async def create_boundary(request: BoundaryRequest, user: AuthUser = Depends(require_roles(Role.ADMIN))) -> dict[str, Any]:
    await _accessible_project(user, request.project_id)
    database = _db()
    existing = await database.boundary_at(request.project_id)
    if existing and existing.effective_from >= request.effective_from:
        raise HTTPException(status_code=409, detail="effective_from must advance the boundary version")
    if existing and existing.effective_to is None:
        existing.effective_to = request.effective_from
        await database.replace(existing)
    boundary = BoundaryDocument.model_construct(project_id=request.project_id, root_authentik_team_id=request.root_authentik_team_id, included_subteam_ids=request.included_subteam_ids, primary_repos=request.primary_repos, effective_from=request.effective_from, data_owner_user_id=request.data_owner_user_id, created_by=user.subject)
    await database.add("boundaries", boundary)
    audit = AuditLogDocument.model_construct(actor_user_id=user.subject, action="boundary.created", target_type="boundary", target_id=f"{request.project_id}:{request.effective_from}", after=request.model_dump(mode="json"), at=datetime.now(timezone.utc))
    await database.add("audit_log", audit)
    return {"project_id": request.project_id, "boundary": _boundary_view(boundary, await database.get_project(request.project_id))}
