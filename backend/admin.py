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

from datetime import date
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, status

from .config import get_settings
from .db import get_active_repository
from .discovery import GiteaUnavailable, discover_and_register_projects, reset_bootstrap_state
from .jobs import run_nightly_sync, run_weekly_backfill, run_weekly_snapshot_job

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
    engine: str | None = Query(default=None, description="'llm' or 'rules'; defaults to 'llm' when configured, else 'rules'."),
    x_admin_sync_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_token(x_admin_sync_token)
    return await run_weekly_snapshot_job(
        settings=get_settings(),
        database=get_active_repository(),
        week_start=week_start,
        engine=engine,
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
    # The collection is empty again, so the next user-facing read should be
    # allowed to bootstrap it rather than sit out a stale cooldown.
    reset_bootstrap_state()
    return {"status": "reset"}


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

    The same work also happens on its own, un-gated, the first time a
    user-facing read finds the projects collection empty -- see
    ``backend.discovery.ensure_projects_registered``. This route stays for
    picking up newly created orgs on a database that already has projects in
    it, which the empty-only bootstrap deliberately will not do.
    """
    _check_token(x_admin_sync_token)
    try:
        result = await discover_and_register_projects(
            settings=get_settings(),
            database=get_active_repository(),
        )
    except GiteaUnavailable as exc:
        configured = get_settings().gitea_url and get_settings().gitea_api_token
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY if configured else status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    # A successful manual discovery makes any earlier bootstrap failure stale.
    reset_bootstrap_state()
    return result


@router.get("/diagnostics/gitea-diff")
async def diagnose_gitea_diff(
    org: str,
    repo: str,
    sha: str,
    x_admin_sync_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """One-off check that the deployed Gitea instance/token can serve raw commit diffs.

    Exists to verify ``GET /repos/{org}/{repo}/git/commits/{sha}.diff`` (the
    endpoint the lazy LLM-signal feature depends on for real code evidence)
    without ever exposing ``PHI_GITEA_API_TOKEN`` to the caller -- the token
    stays server-side, only a status code and a content preview come back.
    """
    _check_token(x_admin_sync_token)
    settings = get_settings()
    if not settings.gitea_url or not settings.gitea_api_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PHI_GITEA_URL and PHI_GITEA_API_TOKEN must both be set",
        )
    import httpx

    url = f"{settings.gitea_url.rstrip('/')}/api/v1/repos/{org}/{repo}/git/commits/{sha}.diff"
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            response = await client.get(
                url, headers={"Authorization": f"token {settings.gitea_api_token}"}
            )
        except Exception as exc:
            return {"ok": False, "url": url, "error": str(exc)}
    body = response.text
    result = {
        "ok": response.status_code == 200 and "diff --git" in body,
        "url": url,
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type"),
        "byte_length": len(body.encode("utf-8", errors="replace")),
        "preview": body[:300],
    }
    meta_url = f"{settings.gitea_url.rstrip('/')}/api/v1/repos/{org}/{repo}/git/commits/{sha}?stat=true&files=true"
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            meta_response = await client.get(
                meta_url, headers={"Authorization": f"token {settings.gitea_api_token}"}
            )
            meta = meta_response.json()
            result["commit_meta_keys"] = sorted(meta.keys())
            result["stats"] = meta.get("stats")
            files = meta.get("files")
            result["files_sample"] = files[:2] if isinstance(files, list) else files
        except Exception as exc:
            result["commit_meta_error"] = str(exc)
    return result
