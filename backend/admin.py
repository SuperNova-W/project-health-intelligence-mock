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
    x_admin_sync_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_token(x_admin_sync_token)
    return await run_weekly_backfill(
        settings=get_settings(),
        database=get_active_repository(),
        weeks=weeks,
    )
