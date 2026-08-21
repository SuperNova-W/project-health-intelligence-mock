"""API coverage for the calendar's missing_project_ids and the lazy compute endpoint."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from backend.db import SqliteStore
from backend.models import AttentionStatus
from backend.signal_llm import SIGNAL_VERSION

PAST_WEEK_MONDAY = date(2026, 3, 2)


@pytest_asyncio.fixture
async def client_over_store(in_memory_store: SqliteStore):
    from backend.api import router

    app = FastAPI(title="test-llm-snapshot")
    app.include_router(router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, in_memory_store


@pytest.mark.asyncio
async def test_missing_project_ids_lists_projects_without_a_snapshot(client_over_store, make_project, make_boundary) -> None:
    client, store = client_over_store
    await store.add("projects", make_project())
    await store.add("boundaries", make_boundary())

    response = await client.get("/snapshots/at", params={"date": PAST_WEEK_MONDAY.isoformat()})
    assert response.status_code == 200
    body = response.json()
    assert body["missing_project_ids"] == ["member-portal"]
    assert body["has_data"] is False


@pytest.mark.asyncio
async def test_post_snapshot_at_refuses_current_week(client_over_store, make_project, make_boundary) -> None:
    client, store = client_over_store
    await store.add("projects", make_project())
    await store.add("boundaries", make_boundary())

    today = date.today()
    response = await client.post("/projects/member-portal/snapshots/at", params={"date": today.isoformat()})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_post_snapshot_at_serves_cached_result_without_recompute(client_over_store, make_project, make_boundary, make_snapshot, monkeypatch) -> None:
    client, store = client_over_store
    await store.add("projects", make_project())
    await store.add("boundaries", make_boundary())
    await store.add(
        "snapshots",
        make_snapshot(
            week_start=PAST_WEEK_MONDAY,
            rule_set_version=SIGNAL_VERSION,
            attention_status=AttentionStatus.CLEAR,
        ),
    )

    async def fail_if_called(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("generate_llm_snapshot should not be called for a cached week")

    monkeypatch.setattr("backend.api.generate_llm_snapshot", fail_if_called)

    response = await client.post("/projects/member-portal/snapshots/at", params={"date": PAST_WEEK_MONDAY.isoformat()})
    assert response.status_code == 200
    body = response.json()
    assert body["cached"] is True
    assert body["computed"] is False


@pytest.mark.asyncio
async def test_post_snapshot_at_computes_and_returns_result(client_over_store, make_project, make_boundary, make_snapshot, monkeypatch) -> None:
    client, store = client_over_store
    await store.add("projects", make_project())
    await store.add("boundaries", make_boundary())

    computed = make_snapshot(
        week_start=PAST_WEEK_MONDAY,
        rule_set_version=SIGNAL_VERSION,
        attention_status=AttentionStatus.WATCH,
    )

    async def fake_generate(*args: Any, **kwargs: Any) -> Any:
        await store.add("snapshots", computed)
        return computed

    monkeypatch.setattr("backend.api.generate_llm_snapshot", fake_generate)
    monkeypatch.setattr("backend.api.get_signal_judge", lambda settings: object())

    import backend.config as config_module
    config_module.get_settings.cache_clear()
    monkeypatch.setenv("PHI_LLM_ENABLED", "true")
    monkeypatch.setenv("PHI_OPENAI_API_KEY", "test-key")
    config_module.get_settings.cache_clear()
    try:
        response = await client.post("/projects/member-portal/snapshots/at", params={"date": PAST_WEEK_MONDAY.isoformat()})
    finally:
        config_module.get_settings.cache_clear()

    assert response.status_code == 200
    body = response.json()
    assert body["computed"] is True
    assert body["cached"] is False
