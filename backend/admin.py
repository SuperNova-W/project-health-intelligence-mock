"""Token-gated HTTP triggers for the pull-only ingestion jobs.

``backend.jobs`` deliberately starts no scheduler of its own -- ``scripts/run_jobs.py``
is the supported entrypoint for cron/systemd/a Kubernetes CronJob. On a host where a
second process can't share the SQLite file with the web service (e.g. Render, where a
persistent disk attaches to exactly one service), these endpoints let an external
scheduler trigger the same jobs in-process on the service that owns the database
connection instead.

Every route requires the ``X-Admin-Sync-Token`` header to match ``PHI_ADMIN_SYNC_TOKEN``.
When that setting is unset, the routes refuse every request -- there is no default-open
mode, since a sync job both writes data and makes outbound calls to the configured Gitea
org.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, status

from .config import get_settings
from .db import get_active_repository
from .ingestion import discover_gitea_orgs
from .jobs import run_nightly_sync, run_weekly_backfill, run_weekly_snapshot_job
from .models import BoundaryDocument, LifecycleState, ProjectDocument, RepositoryRef, utc_now

router = APIRouter(prefix="/admin/sync", tags=["admin"])


def _check_token(provided: str | None) -> None:
    settings = get_settings()
    if not settings.admin_sync_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PHI_ADMIN_SYNC_TOKEN is not configured; sync endpoints are disabled",
        )
    if not provided or provided != settings.admin_sync_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or missing sync token")


@router.post("/nightly")
async def trigger_nightly_sync(
    lookback_days: int = Query(default=14, ge=1, le=90),
    x_admin_sync_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_token(x_admin_sync_token)
    return await run_nightly_sync(
        settings=get_settings(),
        database=get_active_repository(),
        lookback_days=lookback_days,
    )


@router.post("/weekly")
async def trigger_weekly_snapshot(
    week_start: date | None = Query(default=None),
    x_admin_sync_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_token(x_admin_sync_token)
    return await run_weekly_snapshot_job(
        settings=get_settings(),
        database=get_active_repository(),
        week_start=week_start,
    )


@router.post("/backfill")
async def trigger_backfill(
    weeks: int = Query(default=10, ge=1, le=52),
    through: date | None = Query(
        default=None,
        description="Replay the N weeks ending on this date, instead of ending today. "
        "Lets a large backfill be split into smaller sequential HTTP calls "
        "(e.g. weeks=4 with `through` stepping back 4 weeks each call) so no "
        "single request runs long enough to risk a client/proxy timeout.",
    ),
    x_admin_sync_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_token(x_admin_sync_token)
    return await run_weekly_backfill(
        settings=get_settings(),
        database=get_active_repository(),
        through=through,
        weeks=weeks,
    )


@router.post("/reset")
async def trigger_reset(
    confirm: str = Query(description="Must be exactly 'erase-all-data' to proceed."),
    x_admin_sync_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Wipe every row in every collection, including immutable weekly snapshots.

    Intended as a one-time step to clear the bundled demo fixtures before
    pointing the service at a real Gitea org, so leftover mock projects don't
    sit alongside real ones. Irreversible; the ``confirm`` query param exists
    so it can't be triggered by an accidental request.
    """
    _check_token(x_admin_sync_token)
    if confirm != "erase-all-data":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="pass ?confirm=erase-all-data to proceed",
        )
    await get_active_repository().clear()
    return {"status": "reset"}


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "org"


@router.post("/discover-projects")
async def trigger_discover_projects(
    x_admin_sync_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Register one project + boundary per Gitea org the token can see.

    For a Gitea instance that hosts one org per project team (rather than one
    org with many project repos), there is no single ``PHI_GITEA_ORG`` to
    configure. This lists every org via the Gitea API instead, and for each
    one upserts a ``ProjectDocument`` plus a ``BoundaryDocument`` whose
    ``primary_repos`` covers every repo currently in that org. The org's
    username is stored in ``root_authentik_team_id`` (there is no Authentik
    integration here) so ``run_nightly_sync`` / ``run_weekly_backfill`` know
    which orgs to pull from when ``PHI_GITEA_ORG`` is left unset.

    Safe to re-run: an org with no repos is skipped, and a boundary is only
    re-versioned when its repo set actually changed since the last run.
    """
    _check_token(x_admin_sync_token)
    settings = get_settings()
    if not settings.gitea_url or not settings.gitea_api_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PHI_GITEA_URL and PHI_GITEA_API_TOKEN must both be set",
        )
    try:
        discovered = discover_gitea_orgs(base_url=settings.gitea_url, token=settings.gitea_api_token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"could not list Gitea orgs: {exc}",
        ) from exc

    database = get_active_repository()
    today = date.today()
    # A boundary only maps repos to a project from its effective_from date
    # onward, so a boundary dated "today" would be invisible to every
    # backfilled week before today and every one of those weeks' activity
    # would fold as unmapped. Backdating well before any club org could have
    # existed keeps the boundary effective for the org's whole real history.
    effective_from = date(2020, 1, 1)
    created_projects: list[str] = []
    updated_boundaries: list[str] = []
    skipped: list[str] = []
    seen_slugs: set[str] = set()

    for entry in discovered:
        org_name = entry["org"]
        repos = [repo for repo in entry["repos"] if repo.get("id") is not None and repo.get("name")]
        if not repos:
            skipped.append(org_name)
            continue
        slug = _slugify(org_name)
        if slug in seen_slugs:
            skipped.append(org_name)
            continue
        seen_slugs.add(slug)

        primary_repos = [
            RepositoryRef(gitea_repo_id=str(repo["id"]), repo_slug=str(repo["name"]))
            for repo in repos
        ]

        if await database.get_project(slug) is None:
            await database.add(
                "projects",
                ProjectDocument(
                    project_id=slug,
                    display_name=org_name,
                    lifecycle_state=LifecycleState.ACTIVE,
                    non_goals_ack=True,
                ),
            )
            created_projects.append(slug)

        current = await database.boundary_at(slug, at=today)
        current_repo_ids = {ref.gitea_repo_id for ref in current.primary_repos} if current else None
        new_repo_ids = {ref.gitea_repo_id for ref in primary_repos}
        if current_repo_ids != new_repo_ids:
            await database.add(
                "boundaries",
                BoundaryDocument(
                    project_id=slug,
                    root_authentik_team_id=org_name,
                    primary_repos=primary_repos,
                    effective_from=effective_from,
                    created_by="admin-discover",
                    created_at=utc_now(),
                ),
            )
            updated_boundaries.append(slug)

    return {
        "orgs_seen": len(discovered),
        "projects_created": created_projects,
        "boundaries_updated": updated_boundaries,
        "skipped_orgs": skipped,
    }
