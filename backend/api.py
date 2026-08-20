from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from .auth import AuthUser, get_ci_ingest_user, get_current_user, require_project_access, require_roles, visible_project_ids
from .ci_agent import (
    CIEvidence,
    assessment_document,
    assessment_payload,
    normalize_spec,
)
from .ci_llm import (
    LLMAssessor,
    LLMSpecDecomposer,
    assess_project_llm,
    decompose_spec,
)
from .config import Settings, get_settings
from .llm import OpenAIStructuredLLM, LLMUnavailable
from .db import get_active_repository
from .models import (
    AttentionStatus,
    AuditLogDocument,
    BoundaryDocument,
    BoundaryView,
    FeedbackCategory,
    FeedbackDocument,
    HealthAssessmentView,
    ProjectResponse,
    PublicAggregateMetrics,
    RepositoryRef,
    Role,
    WarningDocument,
    WeeklySnapshotDocument,
    PrivacySafeModel,
    new_id,
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


class CIAssessmentRequest(PrivacySafeModel):
    project_id: str = Field(min_length=1, max_length=80)
    spec: str | dict[str, Any]
    spec_format: str | None = Field(default=None, max_length=20)
    evidence: CIEvidence


class DecomposeRequest(PrivacySafeModel):
    """Request body for ``POST /projects/{id}/spec/decompose``.

    The ``context`` field accepts free-form text from the tech lead describing
    the project goals, delivery requirements, team constraints, and risks.  The
    LLM produces a structured week-by-week plan from this; the result is
    returned for review before the tech lead commits it to the repository.
    """

    context: str = Field(
        min_length=1,
        max_length=40_000,
        description="Free-form project context from the tech lead (goals, milestones, constraints).",
    )
    lifecycle_weeks: int = Field(
        default=12,
        ge=1,
        le=52,
        description="Expected project duration in weeks.",
    )


def _get_assessor(settings: Settings) -> LLMAssessor | None:
    """Build an ``LLMAssessor`` if LLM enrichment is configured, else ``None``."""
    if not settings.llm_active:
        return None
    try:
        llm = OpenAIStructuredLLM(
            api_key=settings.openai_api_key,  # type: ignore[arg-type]
            timeout_s=settings.llm_timeout_seconds,
        )
        return LLMAssessor(llm, model=settings.llm_assessment_model)
    except LLMUnavailable:
        return None


def _get_decomposer(settings: Settings) -> LLMSpecDecomposer | None:
    """Build an ``LLMSpecDecomposer`` if LLM enrichment is configured, else ``None``."""
    if not settings.llm_active:
        return None
    try:
        llm = OpenAIStructuredLLM(
            api_key=settings.openai_api_key,  # type: ignore[arg-type]
            timeout_s=min(settings.llm_timeout_seconds * 3, 120.0),
        )
        return LLMSpecDecomposer(llm, model=settings.llm_decomposition_model)
    except LLMUnavailable:
        return None


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
    project = await _db().get_project(project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    return project


async def _warnings_for(snapshot_id: str) -> list[WarningDocument]:
    return await _db().warnings_for_snapshot(snapshot_id)


async def _assessment_for(project_id: str) -> Any:
    return await _db().latest_assessment(project_id)


async def _assessments_for(project_id: str) -> list[Any]:
    rows = [row for row in await _db().list("assessments") if row.project_id == project_id]
    rows.sort(key=lambda row: (row.created_at, row.assessment_id), reverse=True)
    return rows


def _assessment_view(document: Any) -> dict[str, Any] | None:
    if document is None:
        return None
    citations: list[dict[str, str]] = []
    seen: set[str] = set()
    for citation in [*getattr(document, "evidence_citations", []), *getattr(document, "spec_citations", [])]:
        get_value = citation.get if isinstance(citation, dict) else lambda key, default=None: getattr(citation, key, default)
        source_type = get_value("source_type", "ci")
        source_id = get_value("source_id", "unknown")
        source_field = get_value("source_field", "evidence")
        reference = f"{source_type}:{source_id}:{source_field}"
        if reference in seen:
            continue
        seen.add(reference)
        citations.append({"label": f"{source_type} evidence", "reference": reference})
    return HealthAssessmentView(
        status=document.status.value,
        score=document.score,
        confidence=document.confidence,
        expected_week=document.expected_week,
        explanation=document.summary,
        blockers=list(document.blockers),
        recommended_weekly_tasks=list(document.weekly_tasks),
        citations=citations,
        assessment_id=document.assessment_id,
        spec_version=document.spec_version,
        commit_sha=document.commit_sha,
        generated_at=document.created_at,
    ).model_dump(mode="json", by_alias=True, exclude_none=True)


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
    assessment = _assessment_view(await _assessment_for(project.project_id))
    if snapshot is None:
        status_value, status_class = "Insufficient data", "data"
        return ProjectResponse(
            id=project.project_id, name=project.display_name, short=project.display_name[:2].upper(), team="Unassigned", repo="—",
            status=status_value, statusClass=status_class, signal="No snapshot available", signalDetail="Data is not yet sufficient for a trusted assessment.", lastActivity="—", trend="flat", weeks=[None] * 8,
            flagFrom=99, seriesBaselines={"openPRs": [None, None], "reviewLatency": [None, None], "contributors": None}, series={"activity": [None] * 8, "openPRs": [None] * 8, "reviewLatency": [None] * 8, "contributors": None}, description="", boundary=BoundaryView(rootTeam="Unassigned", lifecycle=project.lifecycle_state.value), history=await _history(project.project_id), snapshot_id=None, healthAssessment=assessment,
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
    days_since_activity = snapshot.metrics.days_since_activity
    last_activity = "—" if days_since_activity is None else "Today" if days_since_activity == 0 else "Yesterday" if days_since_activity == 1 else f"{days_since_activity} days ago"
    first_warning = warnings[0].signal_name if warnings else ("Inactivity is expected" if snapshot.attention_status == AttentionStatus.PLANNED_PAUSE else "No current concern detected" if snapshot.attention_status == AttentionStatus.CLEAR else "Repository mapping incomplete" if snapshot.attention_status == AttentionStatus.INSUFFICIENT_DATA else "Review current project signals")
    detail = warnings[0].explanation if warnings else ("Pause recorded; signals are suppressed." if snapshot.attention_status == AttentionStatus.PLANNED_PAUSE else "Ownership review required" if snapshot.attention_status == AttentionStatus.INSUFFICIENT_DATA else "Available project aggregates are within the current rule set.")
    weeks = list(series.get("activity", [None] * 8))[-8:]
    weeks = [None] * (8 - len(weeks)) + weeks
    return ProjectResponse(
        id=project.project_id, name=project.display_name, short=project.display_name[:2].upper(), team=boundary.root_authentik_team_id if boundary else "Unassigned", repo=boundary.primary_repos[0].repo_slug if boundary and boundary.primary_repos else "—",
        status=status_value, statusClass=status_class, signal=first_warning, signalDetail=detail, lastActivity=last_activity, trend="down" if status_class in {"risk", "watch"} else "flat", weeks=weeks,
        flagFrom=5 if status_class == "risk" else 6 if status_class == "watch" else 99, seriesBaselines=_series_baselines(snapshot), series={"activity": series.get("activity", [None] * 8), "openPRs": series.get("openPRs", series.get("open_prs", [None] * 8)), "reviewLatency": series.get("review_latency", series.get("reviewLatency", series.get("review_latency_days", [None] * 8))), "contributors": contributor_series}, description="", boundary=_boundary_view(boundary, project), evidence=evidence, history=await _history(project.project_id), metrics=metrics, baselines=baselines, data_completeness_pct=snapshot.data_completeness_pct, last_sync_at=snapshot.last_sync_at, snapshot_id=_snapshot_id(snapshot), healthAssessment=assessment,
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
        "database": "sqlite",
        "sqlite_path": settings.sqlite_path,
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


@router.get("/projects/{project_id}/health-assessment")
async def project_health_assessment(project_id: str, user: AuthUser = Depends(require_project_access)) -> dict[str, Any]:
    await _accessible_project(user, project_id)
    return {"project_id": project_id, "assessment": _assessment_view(await _assessment_for(project_id))}


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
async def create_feedback(request: FeedbackRequest, user: AuthUser = Depends(get_current_user)) -> dict[str, Any]:
    await _accessible_project(user, request.project_id)
    try:
        uuid.UUID(request.snapshot_id)
    except (ValueError, AttributeError) as exc:
        raise HTTPException(status_code=422, detail="snapshot_id is invalid") from exc
    snapshot = await _db().snapshot_by_id(request.snapshot_id)
    if snapshot is None or snapshot.project_id != request.project_id or request.snapshot_id != str(snapshot.id):
        raise HTTPException(status_code=404, detail="snapshot not found for project")
    warning_str_id = None
    if request.warning_id:
        try:
            uuid.UUID(request.warning_id)
        except (ValueError, AttributeError) as exc:
            raise HTTPException(status_code=422, detail="warning_id is invalid") from exc
        warning = await _db().warning_by_id(request.warning_id)
        if warning is None or str(warning.snapshot_id) != str(snapshot.id):
            raise HTTPException(status_code=404, detail="warning not found for snapshot")
        warning_str_id = request.warning_id
    feedback = FeedbackDocument.model_construct(id=new_id(), snapshot_id=str(snapshot.id), warning_id=warning_str_id, project_id=request.project_id, author_user_id=user.subject, category=request.category, note=request.note, created_at=datetime.now(timezone.utc))
    await _db().add("feedback", feedback)
    audit = AuditLogDocument.model_construct(actor_user_id=user.subject, action="feedback.created", target_type="feedback", target_id=_id(feedback.id), after={"project_id": request.project_id, "snapshot_id": request.snapshot_id, "warning_id": request.warning_id, "category": request.category.value}, at=datetime.now(timezone.utc))
    await _db().add("audit_log", audit)
    return {"id": _id(feedback.id), "snapshot_id": request.snapshot_id, "project_id": request.project_id, "category": request.category.value, "created_at": feedback.created_at}


@router.get("/audit")
async def audit_log(project_id: str | None = Query(default=None), limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, Any]]:
    rows = list(await _db().list("audit_log"))
    if project_id:
        rows = [row for row in rows if (row.after or {}).get("project_id") == project_id]
    rows.sort(key=lambda row: row.at, reverse=True)
    return [{"id": _id(row.id), "actor_user_id": row.actor_user_id, "action": row.action, "target_type": row.target_type, "target_id": row.target_id, "before": row.before, "after": row.after, "at": row.at} for row in rows[:limit]]


@router.get("/rules")
async def rules(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    descriptions = {
        "activity_decline": ("Activity decline", "active days fall below the trailing median", "watch"),
        "open_pr_aging": ("Open PR aging", "oldest open PR exceeds the trailing 75th percentile", "at_risk"),
        "review_latency": ("Review latency", "review latency exceeds the trailing 75th percentile", "watch"),
        "merged_throughput": ("Merged throughput", "merged PR volume falls below the trailing 25th percentile", "watch"),
        "inactivity": ("Inactivity", "days since activity exceeds the trailing 75th percentile", "watch"),
        "contributor_resilience": ("Contributor resilience", "aggregate active contributor count falls below the trailing 25th percentile", "watch"),
    }
    return {"rule_set_version": settings.rule_set_version, "rules": [{"rule_id": rule_id, "version": settings.rule_set_version, "signal_name": descriptions.get(rule_id, (rule_id, "", "watch"))[0], "description": descriptions.get(rule_id, ("", "", ""))[1], "minimum_data": "at least 4 trailing observations", "threshold": descriptions.get(rule_id, ("", "", ""))[1], "severity": descriptions.get(rule_id, ("", "", "watch"))[2], "status": "Active"} for rule_id in RULES]}


async def _submit_ci_assessment(request: CIAssessmentRequest, user: AuthUser) -> dict[str, Any]:
    await _accessible_project(user, request.project_id)
    if request.evidence.project_id != request.project_id:
        raise HTTPException(status_code=422, detail="project_id does not match evidence.project_id")
    try:
        spec = normalize_spec(request.spec, project_id=request.project_id, source_format=request.spec_format)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    database = _db()
    # Idempotency: return the existing assessment for the same commit without re-running
    all_assessments = await database.list("assessments")
    existing = next(
        (row for row in all_assessments
         if row.project_id == request.project_id
         and row.commit_sha == request.evidence.commit_sha),
        None,
    )
    if existing is not None:
        return {"idempotent": True, "assessment": assessment_payload(existing)}

    # Fetch the last 4 assessments to supply as history for the LLM
    prior = sorted(
        [row for row in all_assessments if row.project_id == request.project_id],
        key=lambda r: (r.expected_week, r.created_at),
        reverse=True,
    )[:4]

    try:
        settings = get_settings()
        assessment = await assess_project_llm(
            spec,
            request.evidence,
            assessor=_get_assessor(settings),
            history=prior,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    document = assessment_document(assessment)
    await database.add("assessments", document)
    return {"idempotent": False, "assessment": assessment_payload(document)}


@router.post("/ci/assessments", status_code=status.HTTP_201_CREATED)
async def submit_ci_assessment(request: CIAssessmentRequest, user: AuthUser = Depends(get_ci_ingest_user)) -> dict[str, Any]:
    return await _submit_ci_assessment(request, user)


@router.post("/ci/evidence", status_code=status.HTTP_201_CREATED)
async def submit_ci_evidence(request: CIAssessmentRequest, user: AuthUser = Depends(get_ci_ingest_user)) -> dict[str, Any]:
    return await _submit_ci_assessment(request, user)


@router.get("/projects/{project_id}/assessments")
async def project_assessments(project_id: str, user: AuthUser = Depends(require_project_access)) -> dict[str, Any]:
    await _accessible_project(user, project_id)
    rows = await _assessments_for(project_id)
    return {"project_id": project_id, "assessments": [assessment_payload(row) for row in rows]}


@router.get("/projects/{project_id}/assessments/latest")
async def latest_project_assessment(project_id: str, user: AuthUser = Depends(require_project_access)) -> dict[str, Any]:
    await _accessible_project(user, project_id)
    rows = await _assessments_for(project_id)
    latest = rows[0] if rows else None
    return {"project_id": project_id, "assessment": assessment_payload(latest) if latest else None}


@router.get("/projects/{project_id}/weekly-tasks")
async def project_weekly_tasks(project_id: str, week: int | None = Query(default=None, ge=1, le=52), user: AuthUser = Depends(require_project_access)) -> dict[str, Any]:
    await _accessible_project(user, project_id)
    rows = await _assessments_for(project_id)
    latest = rows[0] if rows else None
    tasks = latest.weekly_tasks if latest and (week is None or latest.expected_week == week) else []
    return {"project_id": project_id, "week": week if week is not None else (latest.expected_week if latest else None), "tasks": tasks, "assessment_id": latest.assessment_id if latest else None}


@router.post("/projects/{project_id}/spec/decompose", status_code=status.HTTP_200_OK)
async def decompose_project_spec(
    project_id: str,
    request: DecomposeRequest,
    user: AuthUser = Depends(require_roles(Role.ADMIN, Role.PORTFOLIO_LEADER)),
) -> dict[str, Any]:
    """Decompose free-form project context into a structured week-by-week spec.

    This is a **kickoff-time** operation, intended to run once when a project
    starts.  The tech lead provides free-form context (goals, milestones,
    constraints); the LLM produces a structured plan the CI agent can score
    against every week.

    The response includes the generated spec for review.  The tech lead should
    commit the spec to the repository before submitting CI assessments, so the
    ``spec_version`` is stable across all submissions for the project lifetime.

    When ``PHI_LLM_ENABLED`` is ``false`` or ``PHI_ANTHROPIC_API_KEY`` is
    absent, the context is treated as a Markdown spec and parsed directly.
    """
    await _accessible_project(user, project_id)
    settings = get_settings()
    decomposer = _get_decomposer(settings)
    try:
        spec = await decompose_spec(
            request.context,
            project_id=project_id,
            lifecycle_weeks=request.lifecycle_weeks,
            decomposer=decomposer,
        )
    except (ValueError, LLMUnavailable) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "project_id": project_id,
        "spec_version": spec.version,
        "lifecycle_weeks": spec.lifecycle_weeks,
        "llm_generated": decomposer is not None,
        "chunk_count": len(spec.chunks),
        "weeks": sorted(
            {(c.week_start, c.week_end) for c in spec.chunks},
            key=lambda w: w[0],
        ),
        "spec": {
            "project_id": spec.project_id,
            "version": spec.version,
            "lifecycle_weeks": spec.lifecycle_weeks,
            "chunks": [c.model_dump(mode="json") for c in spec.chunks],
        },
    }


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
