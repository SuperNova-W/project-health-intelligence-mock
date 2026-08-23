"""Cold-start project discovery: the bootstrap that makes the lazy path reachable.

Every test here patches ``backend.discovery.discover_gitea_orgs`` -- the real
one talks to a Gitea instance over HTTP, and the suite is hermetic.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from backend import discovery
from backend.config import Settings
from backend.db import SqliteStore

ORGS: list[dict[str, Any]] = [
    {"org": "Member Portal", "repos": [{"id": 11, "name": "member-portal"}]},
    {"org": "events-team", "repos": [{"id": 22, "name": "events-api"}, {"id": 23, "name": "events-web"}]},
    {"org": "empty-org", "repos": []},
]


@pytest.fixture
def gitea_settings() -> Settings:
    return Settings(
        sqlite_path=":memory:",
        environment="test",
        gitea_url="https://gitea.example.test",
        gitea_api_token="token-abc",
    )


@pytest.fixture(autouse=True)
def clear_bootstrap_state():
    """The cooldown lives in a module-level gate, so tests must not inherit it."""
    discovery.reset_bootstrap_state()
    yield
    discovery.reset_bootstrap_state()


@pytest_asyncio.fixture
async def client_over_store(in_memory_store: SqliteStore):
    from backend.api import router

    app = FastAPI(title="test-discovery")
    app.include_router(router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, in_memory_store


def _patch(monkeypatch, settings: Settings, orgs: Any, calls: list[int] | None = None) -> None:
    """Point the API at a gitea-configured Settings and a canned org listing."""
    monkeypatch.setattr("backend.api.get_settings", lambda: settings)

    def _fake_discover(*, base_url: str, token: str, **kwargs: Any) -> list[dict[str, Any]]:
        if calls is not None:
            calls.append(1)
        if isinstance(orgs, Exception):
            raise orgs
        return orgs

    monkeypatch.setattr(discovery, "discover_gitea_orgs", _fake_discover)


@pytest.mark.asyncio
async def test_cold_read_registers_a_project_per_org(client_over_store, gitea_settings, monkeypatch) -> None:
    client, store = client_over_store
    _patch(monkeypatch, gitea_settings, ORGS)

    response = await client.get("/snapshots/latest")
    assert response.status_code == 200
    body = response.json()

    # The org with no repos is skipped; the other two become projects, slugified.
    assert sorted(item["id"] for item in body["projects"]) == ["events-team", "member-portal"]
    # The display name is the org's, not a placeholder -- a reviewer has to be
    # able to tell the rows apart while they are still computing.
    assert sorted(item["name"] for item in body["projects"]) == ["Member Portal", "events-team"]
    # Registered but not yet computed, so the frontend's observer has rows to fill.
    assert sorted(body["missing_project_ids"]) == ["events-team", "member-portal"]
    assert body["gitea_configured"] is True

    boundaries = await store.list("boundaries")
    assert {b.project_id for b in boundaries} == {"events-team", "member-portal"}
    repo_ids = {ref.gitea_repo_id for b in boundaries for ref in b.primary_repos}
    assert repo_ids == {"11", "22", "23"}


@pytest.mark.asyncio
async def test_bootstrap_does_not_run_again_once_projects_exist(
    client_over_store, gitea_settings, monkeypatch, make_project
) -> None:
    client, store = client_over_store
    calls: list[int] = []
    _patch(monkeypatch, gitea_settings, ORGS, calls)
    await store.add("projects", make_project())

    await client.get("/snapshots/latest")
    await client.get("/snapshots/latest")

    assert calls == []
    assert [p.project_id for p in await store.list("projects")] == ["member-portal"]


@pytest.mark.asyncio
async def test_bootstrap_runs_once_across_repeated_cold_reads(client_over_store, gitea_settings, monkeypatch) -> None:
    client, _ = client_over_store
    calls: list[int] = []
    _patch(monkeypatch, gitea_settings, ORGS, calls)

    await client.get("/snapshots/latest")
    await client.get("/snapshots/latest")
    await client.get("/portfolio/delivery")

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_failed_bootstrap_still_serves_an_envelope_and_backs_off(
    client_over_store, gitea_settings, monkeypatch
) -> None:
    client, _ = client_over_store
    calls: list[int] = []
    _patch(monkeypatch, gitea_settings, RuntimeError("gitea unreachable"), calls)

    first = await client.get("/snapshots/latest")
    second = await client.get("/snapshots/latest")

    # A read endpoint owes its caller an envelope even when discovery fails.
    assert first.status_code == 200
    assert first.json()["projects"] == []
    assert second.status_code == 200
    # The cooldown means the second read does not pay for the same timeout.
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_bootstrap_is_skipped_when_gitea_is_not_configured(client_over_store, monkeypatch) -> None:
    client, _ = client_over_store
    calls: list[int] = []
    _patch(monkeypatch, Settings(sqlite_path=":memory:", environment="test"), ORGS, calls)

    response = await client.get("/snapshots/latest")

    assert response.status_code == 200
    body = response.json()
    assert body["projects"] == []
    assert calls == []
    # The envelope has to say why it is empty, or the frontend can only render
    # a blank table that looks identical to a broken API base.
    assert body["gitea_configured"] is False


@pytest.mark.asyncio
async def test_reachable_gitea_with_no_eligible_org_backs_off(client_over_store, gitea_settings, monkeypatch) -> None:
    client, _ = client_over_store
    calls: list[int] = []
    _patch(monkeypatch, gitea_settings, [{"org": "empty-org", "repos": []}], calls)

    await client.get("/snapshots/latest")
    await client.get("/snapshots/latest")

    # Nothing was created, so re-listing on every request would be pure waste.
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_discovery_is_idempotent_on_repeat(in_memory_store: SqliteStore, gitea_settings, monkeypatch) -> None:
    monkeypatch.setattr(discovery, "discover_gitea_orgs", lambda **kwargs: ORGS)

    first = await discovery.discover_and_register_projects(settings=gitea_settings, database=in_memory_store)
    second = await discovery.discover_and_register_projects(settings=gitea_settings, database=in_memory_store)

    assert sorted(first["projects_created"]) == ["events-team", "member-portal"]
    assert first["skipped_orgs"] == ["empty-org"]
    # An unchanged repo set must not append a new boundary version.
    assert second["projects_created"] == []
    assert second["boundaries_updated"] == []
    assert len(await in_memory_store.list("boundaries")) == 2


@pytest.mark.asyncio
async def test_boundary_is_backdated_so_past_weeks_map(in_memory_store: SqliteStore, gitea_settings, monkeypatch) -> None:
    monkeypatch.setattr(discovery, "discover_gitea_orgs", lambda **kwargs: ORGS)
    await discovery.discover_and_register_projects(settings=gitea_settings, database=in_memory_store)

    for boundary in await in_memory_store.list("boundaries"):
        assert boundary.effective_from == discovery.BOUNDARY_EFFECTIVE_FROM


@pytest.mark.asyncio
async def test_discovery_reports_missing_configuration(in_memory_store: SqliteStore) -> None:
    settings = Settings(sqlite_path=":memory:", environment="test")
    with pytest.raises(discovery.GiteaUnavailable):
        await discovery.discover_and_register_projects(settings=settings, database=in_memory_store)
