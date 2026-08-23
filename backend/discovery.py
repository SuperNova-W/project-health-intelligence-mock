"""Register one project + boundary per Gitea org, on demand.

Two callers share the logic here. ``POST /admin/sync/discover-projects`` runs
:func:`discover_and_register_projects` deliberately, as an operator step. The
user-facing reads in ``backend.api`` run :func:`ensure_projects_registered`,
which does the same work but only when the projects collection is completely
empty -- the cold-database bootstrap.

That second path exists because the project registry is the one thing the
lazy per-row snapshot compute cannot rebuild for itself. ``GET
/snapshots/latest`` iterates the projects collection, so with no rows in it
there is nothing to list, nothing to mark missing, and nothing for the
frontend's IntersectionObserver to fill in -- the dashboard renders empty no
matter how much lazy machinery sits behind it. On a host whose disk does not
survive a deploy (Render's SQLite lives on the container filesystem) that is
the state after every single deploy, and re-running a token-gated admin call
by hand each time is exactly the backfill step this is meant to remove.

Discovery is cheap and network-only: it lists orgs and their repos, and
writes one small row per org. It does not pull commits, PRs or history --
those stay lazy, per project, as rows scroll into view.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import date
from typing import Any

from starlette.concurrency import run_in_threadpool

from .config import Settings
from .ingestion import discover_gitea_orgs
from .models import BoundaryDocument, LifecycleState, ProjectDocument, RepositoryRef, utc_now

logger = logging.getLogger(__name__)

# A boundary only maps repos to a project from its effective_from date
# onward, so a boundary dated "today" would be invisible to every week before
# today and all of that activity would fold as unmapped. Backdating well
# before any club org could have existed keeps the boundary effective for the
# org's whole real history.
BOUNDARY_EFFECTIVE_FROM = date(2020, 1, 1)

# How long to wait before a bootstrap attempt that found nothing -- a failed
# Gitea call, or a reachable instance with no eligible org -- is retried. The
# attempt costs a network round trip on the request that triggers it, so
# without a cooldown a misconfigured PHI_GITEA_URL would tax every page load
# with a connect timeout and still show the same empty dashboard.
BOOTSTRAP_RETRY_SECONDS = 300.0


class GiteaUnavailable(RuntimeError):
    """Raised when the Gitea org listing could not be fetched."""


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "org"


async def discover_and_register_projects(*, settings: Settings, database: Any) -> dict[str, Any]:
    """Upsert a project + boundary for every Gitea org the token can see.

    Safe to re-run: an org with no repos is skipped, an existing project is
    left alone, and a boundary is only re-versioned when its repo set actually
    changed since the last run.

    Raises :class:`GiteaUnavailable` when the org listing fails, so an
    operator-triggered call can surface the reason and a lazy bootstrap can
    swallow it.
    """
    if not settings.gitea_url or not settings.gitea_api_token:
        raise GiteaUnavailable("PHI_GITEA_URL and PHI_GITEA_API_TOKEN must both be set")

    try:
        # discover_gitea_orgs drives httpx synchronously. Handing it to a
        # worker thread keeps a bootstrap triggered from a request handler
        # from stalling the event loop for every other in-flight request.
        discovered = await run_in_threadpool(
            discover_gitea_orgs,
            base_url=settings.gitea_url,
            token=settings.gitea_api_token,
        )
    except Exception as exc:  # noqa: BLE001 - re-raised as a typed error below
        raise GiteaUnavailable(f"could not list Gitea orgs: {exc}") from exc

    today = date.today()
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
        slug = slugify(org_name)
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
                    effective_from=BOUNDARY_EFFECTIVE_FROM,
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


class _BootstrapGate:
    """Single-flight guard so one cold-start request does the discovery.

    A cold dashboard load fires several reads at once. Without the lock they
    would each list the same orgs and race to insert the same rows; with it,
    the first request discovers and the rest wait and then observe a populated
    collection.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._last_attempt: float | None = None

    def reset(self) -> None:
        self._last_attempt = None

    def _cooling_down(self) -> bool:
        return (
            self._last_attempt is not None
            and (time.monotonic() - self._last_attempt) < BOOTSTRAP_RETRY_SECONDS
        )

    @staticmethod
    async def _has_projects(database: Any) -> bool:
        # SqliteStore answers this with a LIMIT 1 query; the fallback is for
        # stores that only implement the generic collection interface.
        has_any = getattr(database, "has_any", None)
        if has_any is not None:
            return await has_any("projects")
        return bool(await database.list("projects"))

    async def run(self, *, settings: Settings, database: Any) -> dict[str, Any] | None:
        if not settings.gitea_url or not settings.gitea_api_token:
            return None
        if await self._has_projects(database) or self._cooling_down():
            return None
        async with self._lock:
            # Re-check inside the lock: whoever held it may have just filled
            # the collection while this request was queued behind them.
            if await self._has_projects(database) or self._cooling_down():
                return None
            self._last_attempt = time.monotonic()
            try:
                result = await discover_and_register_projects(settings=settings, database=database)
            except GiteaUnavailable as exc:
                # A read endpoint still owes its caller an envelope, so a
                # bootstrap failure degrades to the empty dashboard it would
                # have rendered anyway rather than a 5xx.
                logger.warning("lazy project discovery failed: %s", exc)
                return None
            if result["projects_created"]:
                # Only a run that actually registered something clears the
                # cooldown; an instance that legitimately has no eligible org
                # should not be re-listed on the next request.
                self.reset()
            logger.info(
                "lazy project discovery registered %d project(s) from %d org(s)",
                len(result["projects_created"]),
                result["orgs_seen"],
            )
            return result


_gate = _BootstrapGate()


async def ensure_projects_registered(*, settings: Settings, database: Any) -> dict[str, Any] | None:
    """Bootstrap the project registry if, and only if, it is empty.

    A no-op once any project exists, so this costs one extra collection read
    on the overwhelming majority of requests. Returns the discovery summary
    when a bootstrap ran, ``None`` otherwise.
    """
    return await _gate.run(settings=settings, database=database)


def reset_bootstrap_state() -> None:
    """Forget the last bootstrap attempt. For tests, and for /admin/sync/reset."""
    _gate.reset()
