"""Guards on the allocations that were exhausting the deployed container.

Two of the three fixes are testable in-process (the third, the frontend's
lazy-compute concurrency cap, lives in app.js). Both of these are about *peak*
memory, so each test asserts the thing was never buffered -- not merely that
the value returned afterwards was small.
"""

from __future__ import annotations

from typing import Any

import pytest

from backend.code_evidence import DEFAULT_LIMITS
from backend.db import SqliteStore
from backend.ingestion import _HttpxAdapter


class _FakeStreamResponse:
    """Yields 64KB chunks and counts how many were actually pulled."""

    def __init__(self, total_bytes: int, counter: dict[str, int]) -> None:
        self._total = total_bytes
        self._counter = counter

    def raise_for_status(self) -> None:
        return None

    def iter_bytes(self):
        chunk = b"x" * 65_536
        served = 0
        while served < self._total:
            self._counter["bytes"] += len(chunk)
            served += len(chunk)
            yield chunk

    def __enter__(self):
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False


class _StreamingClient:
    def __init__(self, total_bytes: int, counter: dict[str, int]) -> None:
        self._total = total_bytes
        self._counter = counter

    def stream(self, method: str, url: str, params: Any = None) -> _FakeStreamResponse:
        return _FakeStreamResponse(self._total, self._counter)


class _NonStreamingResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


class _NonStreamingClient:
    """A test-double client with no .stream, like the fakes elsewhere in the suite."""

    def __init__(self, text: str) -> None:
        self._text = text

    def get(self, url: str, params: Any = None) -> _NonStreamingResponse:
        return _NonStreamingResponse(self._text)


def _adapter(client: Any) -> _HttpxAdapter:
    return _HttpxAdapter(base_url="https://gitea.example.test", token="t", client=client)


def test_get_text_stops_reading_once_the_cap_is_reached() -> None:
    counter = {"bytes": 0}
    # 20MB on the wire, capped at 400KB.
    adapter = _adapter(_StreamingClient(20 * 1024 * 1024, counter))

    text = adapter.get_text("/some.diff", max_bytes=400_000)

    assert len(text.encode("utf-8")) <= 400_000
    # The point of the fix: the rest was never pulled into the process. Allow
    # one chunk of overshoot, since the cap is checked after each append.
    assert counter["bytes"] <= 400_000 + 65_536


def test_get_text_without_a_cap_is_unchanged() -> None:
    adapter = _adapter(_NonStreamingClient("a" * 5_000))
    assert adapter.get_text("/small.diff") == "a" * 5_000


def test_get_text_caps_a_client_that_cannot_stream() -> None:
    """Test doubles have no .stream; the cap must still hold for them."""
    adapter = _adapter(_NonStreamingClient("a" * 900_000))
    text = adapter.get_text("/big.diff", max_bytes=400_000)
    assert len(text.encode("utf-8")) == 400_000


def test_raw_diff_ceiling_leaves_room_above_the_per_commit_cap() -> None:
    """The raw ceiling bounds the process; max_bytes_per_commit bounds the prompt.

    If the raw ceiling ever drops near the per-commit cap, noise filtering
    would start seeing truncated commits as a matter of course rather than
    only in the pathological case.
    """
    assert DEFAULT_LIMITS.max_raw_diff_bytes > DEFAULT_LIMITS.max_bytes_per_commit * 10


@pytest.mark.asyncio
async def test_has_any_reports_emptiness_without_decoding_rows(
    in_memory_store: SqliteStore, make_project
) -> None:
    assert await in_memory_store.has_any("projects") is False
    await in_memory_store.add("projects", make_project())
    assert await in_memory_store.has_any("projects") is True


@pytest.mark.asyncio
async def test_bootstrap_uses_has_any_rather_than_listing(
    in_memory_store: SqliteStore, make_project, monkeypatch
) -> None:
    """The cold-start check runs on every request, so it must not load the table."""
    from backend import discovery

    await in_memory_store.add("projects", make_project())
    calls: list[str] = []
    original = in_memory_store.list

    async def _tracking_list(collection: str):
        calls.append(collection)
        return await original(collection)

    monkeypatch.setattr(in_memory_store, "list", _tracking_list)
    discovery.reset_bootstrap_state()

    settings_obj = type("S", (), {"gitea_url": "https://g.test", "gitea_api_token": "t"})()
    await discovery.ensure_projects_registered(settings=settings_obj, database=in_memory_store)

    assert "projects" not in calls
