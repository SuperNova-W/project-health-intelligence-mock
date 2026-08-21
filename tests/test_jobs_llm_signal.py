"""Integration coverage for the lazy LLM-signal job functions in backend.jobs."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest

from backend.code_evidence import CommitFact, RepoCodeEvidence, WeekCodeEvidence
from backend.db import SqliteStore
from backend.jobs import generate_llm_snapshot, generate_llm_weekly_snapshots
from backend.models import LifecycleState, PlannedPause
from backend.signal_llm import SIGNAL_VERSION, WeeklySignalJudge

WEEK_START = date(2026, 8, 3)


def _commit(sha: str) -> CommitFact:
    return CommitFact(
        sha=sha, repo_slug="member-portal", subject="add feature", committed_at=datetime(2026, 8, 4, tzinfo=timezone.utc),
        additions=200, deletions=10, files=["src/feature.py"], noise_files=[], is_noise_only=False, is_chore_like=False,
    )


class FakeReader:
    def __init__(self, evidence: WeekCodeEvidence) -> None:
        self._evidence = evidence
        self.closed = False

    def week_evidence(self, **_: Any) -> WeekCodeEvidence:
        return self._evidence

    def close(self) -> None:
        self.closed = True


class FakeLLM:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls = 0

    async def call_tool(self, *, system: str, user: str, tool: dict[str, Any], model: str, max_tokens: int) -> dict[str, Any]:
        self.calls += 1
        return self.response


def _valid_response(status: str = "watch") -> dict[str, Any]:
    return {
        "status": status,
        "confidence": 0.7,
        "headline": "Steady progress",
        "summary": "Real work landed this week.",
        "work_volume": "moderate",
        "what_changed": [{"text": "Added a feature", "evidence": ["member-portal@aaaaaaa"]}],
        "concerns": [{"text": "No tests included", "severity": "warning", "evidence": ["member-portal@aaaaaaa"]}],
        "recommendations": [],
        "data_gaps": [],
    }


@pytest.mark.asyncio
async def test_generate_llm_snapshot_caches_on_second_call(in_memory_store: SqliteStore, make_project, make_boundary, monkeypatch) -> None:
    await in_memory_store.add("projects", make_project())
    await in_memory_store.add("boundaries", make_boundary())

    evidence = WeekCodeEvidence(
        project_id="member-portal", week_start=WEEK_START, week_end=WEEK_START + timedelta(days=6),
        repos=[RepoCodeEvidence(repo_slug="member-portal", commits=[_commit("aaaaaaa1234")], diffs={"aaaaaaa1234": "diff --git a/src/feature.py b/src/feature.py\n"})],
        tier="tier2",
    )
    reader = FakeReader(evidence)

    async def fake_builder(settings, database, project_id, *, at):
        return reader, ["member-portal"]

    monkeypatch.setattr("backend.jobs.build_code_evidence_reader", fake_builder)

    llm = FakeLLM(_valid_response())
    judge = WeeklySignalJudge(llm, model="gpt-4o")

    first = await generate_llm_snapshot("member-portal", WEEK_START, database=in_memory_store, judge=judge)
    assert first is not None
    assert first.signal_source == "llm"
    assert first.rule_set_version == SIGNAL_VERSION
    assert llm.calls == 1

    second = await generate_llm_snapshot("member-portal", WEEK_START, database=in_memory_store, judge=judge)
    assert second is not None
    assert second.id == first.id
    assert llm.calls == 1  # cache hit, no second OpenAI call

    warnings = [w for w in await in_memory_store.list("warnings") if w.project_id == "member-portal"]
    assert len(warnings) == 1
    assert warnings[0].rule_id == "llm.weekly_signal"


@pytest.mark.asyncio
async def test_generate_llm_snapshot_returns_none_on_llm_failure(in_memory_store: SqliteStore, make_project, make_boundary, monkeypatch) -> None:
    await in_memory_store.add("projects", make_project())
    await in_memory_store.add("boundaries", make_boundary())

    evidence = WeekCodeEvidence(
        project_id="member-portal", week_start=WEEK_START, week_end=WEEK_START + timedelta(days=6),
        repos=[RepoCodeEvidence(repo_slug="member-portal", commits=[_commit("bbbbbbb1234")], diffs={"bbbbbbb1234": "diff --git a/src/feature.py b/src/feature.py\n"})],
        tier="tier2",
    )
    reader = FakeReader(evidence)

    async def fake_builder(settings, database, project_id, *, at):
        return reader, ["member-portal"]

    monkeypatch.setattr("backend.jobs.build_code_evidence_reader", fake_builder)

    result = await generate_llm_snapshot("member-portal", WEEK_START, database=in_memory_store, judge=None)
    assert result is None

    snapshots = [s for s in await in_memory_store.list("snapshots") if s.project_id == "member-portal"]
    assert snapshots == []  # nothing persisted on the fail-closed path


@pytest.mark.asyncio
async def test_generate_llm_snapshot_honors_planned_pause(in_memory_store: SqliteStore, make_project, make_boundary) -> None:
    project = make_project(
        lifecycle_state=LifecycleState.PAUSED,
        planned_pauses=[PlannedPause(starts_on=date(2026, 8, 1), ends_on=date(2026, 8, 31), reason="summer break")],
    )
    await in_memory_store.add("projects", project)
    await in_memory_store.add("boundaries", make_boundary())

    result = await generate_llm_snapshot("member-portal", WEEK_START, database=in_memory_store, judge=None)
    assert result is not None
    assert result.signal_headline == "Planned pause"


@pytest.mark.asyncio
async def test_generate_llm_weekly_snapshots_fans_out_across_projects(in_memory_store: SqliteStore, make_project, make_boundary, monkeypatch) -> None:
    await in_memory_store.add("projects", make_project(project_id="proj-a"))
    await in_memory_store.add("boundaries", make_boundary(project_id="proj-a"))
    await in_memory_store.add("projects", make_project(project_id="proj-b"))
    await in_memory_store.add("boundaries", make_boundary(project_id="proj-b"))

    async def fake_builder(settings, database, project_id, *, at):
        evidence = WeekCodeEvidence(
            project_id=project_id, week_start=WEEK_START, week_end=WEEK_START + timedelta(days=6),
            repos=[RepoCodeEvidence(repo_slug=project_id, commits=[], diffs={})], tier="tier0",
        )
        return FakeReader(evidence), [project_id]

    monkeypatch.setattr("backend.jobs.build_code_evidence_reader", fake_builder)
    monkeypatch.setattr("backend.jobs.get_signal_judge", lambda settings: None)

    written = await generate_llm_weekly_snapshots(database=in_memory_store, week_start=WEEK_START)
    assert written == 2

    snapshots = [s for s in await in_memory_store.list("snapshots") if s.rule_set_version == SIGNAL_VERSION]
    assert {s.project_id for s in snapshots} == {"proj-a", "proj-b"}
