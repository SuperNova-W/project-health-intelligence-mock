from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.auth import get_ci_ingest_user
from backend.config import Settings
from backend.ci_agent import (
    AssessmentStatus,
    AssessmentDocument,
    CIEvidence,
    assess_project,
    assessment_document,
    normalize_spec,
    retrieve_chunks,
)
from backend.db import BeanieStore, InMemoryStore, store
from backend.models import Role
from backend.seed import _demo_assessment, _specs, seed_demo_data
from test_api import _boundary, _project, _snapshot, api


def spec():
    return normalize_spec({
        "project_id": "demo-project",
        "lifecycle_weeks": 12,
        "weeks": [
            {"week": 2, "milestone": "Vertical slice", "tasks": ["Ship API"], "acceptance_criteria": ["API returns health"], "required_artifacts": ["assessment.json"]},
            {"week": 3, "milestone": "Early signal", "tasks": ["Add citations"], "acceptance_criteria": ["Warnings cite evidence"]},
            {"week": 12, "milestone": "Handoff", "tasks": ["Publish handoff"]},
        ],
    })


def evidence(**overrides):
    values = {
        "project_id": "demo-project", "commit_sha": "abc123", "expected_week": 3,
        "changed_files": ["backend/app.py"], "tests_total": 10, "tests_passed": 10,
        "tests_failed": 0, "coverage_pct": 85, "deploy_status": "passed",
        "check_results": [{"name": "ci", "status": "passed"}],
        "milestone_refs": ["week-3"], "acceptance_criteria_refs": ["Warnings cite evidence"],
        "docs_updated": True, "observed_at": datetime(2026, 8, 12, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return CIEvidence(**values)


def test_retrieval_is_deterministic_and_week_scoped():
    project_spec = spec()
    first = [item.chunk_id for item in retrieve_chunks(project_spec, "citations evidence", week=3)]
    second = [item.chunk_id for item in retrieve_chunks(project_spec, "citations evidence", week=3)]
    assert first == second
    assert all(item.week_start <= 3 <= item.week_end for item in retrieve_chunks(project_spec, "API", week=3))


def test_markdown_normalization_creates_stable_chunks():
    source = "## Week 2: Slice\n- Ship API\n- Acceptance: API returns health\n"
    first = normalize_spec(source, project_id="md-project", source_format="markdown")
    second = normalize_spec(source, project_id="md-project", source_format="markdown")
    assert [chunk.chunk_id for chunk in first.chunks] == [chunk.chunk_id for chunk in second.chunks]
    assert {chunk.week_start for chunk in first.chunks} == {2}


def test_clear_assessment_has_spec_and_evidence_citations():
    result = assess_project(spec(), evidence())
    assert result.status == AssessmentStatus.CLEAR
    assert result.score >= 80
    assert result.spec_citations and result.evidence_citations


def test_failed_ci_is_at_risk_and_cited():
    result = assess_project(spec(), evidence(tests_failed=2, tests_passed=8, coverage_pct=40, deploy_status="failed"))
    assert result.status == AssessmentStatus.AT_RISK
    assert result.blockers
    assert any(item.source_field in {"tests_failed", "coverage_pct", "deploy_status"} for item in result.evidence_citations)


def test_stale_progress_is_at_risk_and_cited():
    result = assess_project(spec(), evidence(progress_age_days=14))

    assert result.status == AssessmentStatus.AT_RISK
    assert any(item.source_field == "progress_age_days" for item in result.evidence_citations)
    assert any("progress" in blocker.lower() for blocker in result.blockers)


def test_last_progress_timestamp_is_used_for_freshness():
    result = assess_project(
        spec(),
        evidence(
            last_progress_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            milestone_due_week=3,
        ),
    )

    assert result.status == AssessmentStatus.WATCH
    assert any(item.source_field == "progress_age_days" for item in result.evidence_citations)


def test_overdue_milestone_timing_is_watch_and_cited():
    result = assess_project(spec(), evidence(milestone_refs=[], milestone_due_week=2))

    assert result.status == AssessmentStatus.WATCH
    assert any(item.source_field == "milestone_due_week" for item in result.evidence_citations)


def test_week_two_missing_evidence_is_early_watch_signal():
    result = assess_project(spec(), CIEvidence(project_id="demo-project", commit_sha="week2", expected_week=2, changed_files=["README.md"]))
    assert result.status == AssessmentStatus.WATCH
    assert result.evidence_citations or result.spec_citations


def test_week_three_sparse_evidence_is_early_watch_signal():
    result = assess_project(spec(), CIEvidence(project_id="demo-project", commit_sha="week3", expected_week=3, changed_files=["README.md"]))

    assert result.status == AssessmentStatus.WATCH
    assert result.evidence_citations or result.spec_citations


def test_week_one_does_not_emit_a_health_signal():
    result = assess_project(spec(), CIEvidence(project_id="demo-project", commit_sha="week1", expected_week=1, changed_files=["README.md"]))
    assert result.status == AssessmentStatus.INSUFFICIENT_DATA
    assert "week 2" in result.summary


def test_privacy_rejection_is_fail_closed():
    with pytest.raises((ValidationError, ValueError)):
        CIEvidence.model_validate({"project_id": "demo-project", "commit_sha": "x", "per_person_metrics": {"a": 1}})


def test_planned_pause_is_not_risk():
    result = assess_project(spec(), evidence(planned_pause=True))
    assert result.status == AssessmentStatus.PLANNED_PAUSE


def test_malformed_spec_is_rejected():
    with pytest.raises(ValueError):
        normalize_spec("weeks: [not-an-object]", project_id="demo-project")


def test_twelve_week_lifecycle_fixtures_cover_expected_statuses():
    root = Path(__file__).parents[1]
    project_spec = normalize_spec(root / "fixtures/project-health-spec.yaml", project_id="project-health-intelligence")
    scenarios = json.loads((root / "fixtures/ci-lifecycle-scenarios.json").read_text())
    assert project_spec.lifecycle_weeks == 12
    assert {2, 3, 4, 8, 12} <= {scenario["expected_week"] for scenario in scenarios}
    observed = []
    for scenario in scenarios:
        payload = {key: value for key, value in scenario.items() if key not in {"name", "expected_status"}}
        payload["project_id"] = "project-health-intelligence"
        observed.append(assess_project(project_spec, CIEvidence(**payload)).status.value)
    assert observed == [scenario["expected_status"] for scenario in scenarios]


def test_demo_seed_assessments_cover_all_dashboard_states():
    assessments = [_demo_assessment(project, index) for index, project in enumerate(_specs(), 1)]
    assert [assessment.status.value for assessment in assessments] == [
        "at_risk", "watch", "watch", "clear", "clear", "insufficient_data", "planned_pause",
    ]
    assert all(assessment.project_id for assessment in assessments)
    assert all(assessment.spec_citations or assessment.status == AssessmentStatus.PLANNED_PAUSE for assessment in assessments)


def test_assessment_collection_aliases_work_in_local_and_mongo_facades():
    repository = InMemoryStore()
    assessment = assessment_document(assess_project(spec(), evidence()))

    asyncio.run(repository.insert(assessment))

    assert asyncio.run(repository.list("assessments")) == [assessment]
    assert asyncio.run(repository.list("ci_assessments")) == [assessment]
    assert asyncio.run(repository.find_one(AssessmentDocument, project_id="demo-project")) == assessment
    assert BeanieStore()._model("assessments") is AssessmentDocument
    assert BeanieStore()._model("ci_assessments") is AssessmentDocument


def test_seed_backfills_missing_assessments_for_existing_demo_projects(api):
    api.add("projects", _project("member-portal"))

    asyncio.run(seed_demo_data())
    asyncio.run(seed_demo_data())

    assert len(store.assessments) == 1
    assert store.assessments[0].project_id == "member-portal"


def test_long_commit_sha_keeps_citations_within_the_contract():
    result = assess_project(spec(), evidence(commit_sha="c" * 160))

    assert result.evidence_citations
    assert all(len(citation.citation_id) <= 160 for citation in result.evidence_citations)


def test_local_cli_uses_current_worktree_and_risk_exit_code(tmp_path):
    from scripts.run_ci_assessment import local_evidence

    local = local_evidence("demo-project", 2)
    assert "backend/ci_agent.py" in local.changed_files

    risk_evidence = tmp_path / "risk.json"
    risk_evidence.write_text(json.dumps({
        "project_id": "project-health-intelligence",
        "commit_sha": "cli-risk",
        "expected_week": 4,
        "changed_files": ["app.py"],
        "tests_total": 4,
        "tests_passed": 0,
        "tests_failed": 4,
        "coverage_pct": 40,
        "deploy_status": "failed",
    }))
    output = tmp_path / "assessment.json"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_ci_assessment.py",
            "--project-id",
            "project-health-intelligence",
            "--spec",
            "fixtures/project-health-spec.yaml",
            "--evidence",
            str(risk_evidence),
            "--output",
            str(output),
            "--fail-on-risk",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert json.loads(output.read_text())["status"] == "at_risk"


def test_api_submit_is_idempotent_and_project_scoped(api):
    api.add("projects", _project("member-portal"))
    api.add("boundaries", _boundary("member-portal"))
    payload = {
        "project_id": "member-portal",
        "spec": {"project_id": "member-portal", "weeks": [{"week": 3, "tasks": ["Ship slice"], "acceptance_criteria": ["Evidence is cited"]}]},
        "evidence": {"project_id": "member-portal", "commit_sha": "api-commit", "expected_week": 3, "changed_files": ["app.py"], "tests_total": 4, "tests_passed": 4, "tests_failed": 0, "coverage_pct": 90, "deploy_status": "passed", "milestone_refs": ["week-3"], "acceptance_criteria_refs": ["Evidence is cited"]},
    }
    first = api.client.post("/ci/assessments", json=payload)
    second = api.client.post("/ci/assessments", json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["idempotent"] is True
    latest = api.client.get("/projects/member-portal/assessments/latest")
    assert latest.status_code == 200
    assert latest.json()["assessment"]["commit_sha"] == "api-commit"
    api.set_user(roles={Role.PROJECT_LEAD}, project_ids={"campus-events"})
    denied = api.client.get("/projects/member-portal/assessments/latest")
    assert denied.status_code == 403


def test_api_rejects_mismatched_or_malformed_specs(api):
    api.add("projects", _project("member-portal"))
    api.add("boundaries", _boundary("member-portal"))
    evidence_payload = {"project_id": "member-portal", "commit_sha": "api-invalid", "expected_week": 3}

    mismatch = api.client.post(
        "/ci/assessments",
        json={
            "project_id": "member-portal",
            "spec": {"project_id": "other-project", "weeks": [{"week": 3, "tasks": ["Ship slice"]}]},
            "evidence": evidence_payload,
        },
    )
    malformed = api.client.post(
        "/ci/assessments",
        json={"project_id": "member-portal", "spec": "weeks: [", "evidence": evidence_payload},
    )

    assert mismatch.status_code == 422
    assert malformed.status_code == 422


def test_latest_snapshot_embeds_safe_health_assessment_contract(api):
    api.add("projects", _project("member-portal"))
    api.add("boundaries", _boundary("member-portal"))
    snapshot = _snapshot("member-portal")
    api.add("snapshots", snapshot)
    project_spec = normalize_spec({"project_id": "member-portal", "weeks": [{"week": 3, "tasks": ["Ship slice"], "acceptance_criteria": ["Evidence is cited"]}]})
    assessment = assessment_document(assess_project(project_spec, CIEvidence(
        project_id="member-portal", commit_sha="embedded-commit", expected_week=3,
        changed_files=["app.py"], tests_total=4, tests_passed=4, tests_failed=0,
        coverage_pct=90, milestone_refs=["week-3"], acceptance_criteria_refs=["Evidence is cited"],
    )))
    api.add("assessments", assessment)

    latest = api.client.get("/snapshots/latest")
    embedded = latest.json()["projects"][0]["healthAssessment"]
    assert latest.status_code == 200
    assert embedded["status"] == "clear"
    assert embedded["expectedWeek"] == 3
    assert embedded["recommendedWeeklyTasks"]
    assert embedded["citations"]
    assert api.client.get("/projects/member-portal/health-assessment").json()["assessment"]["commit_sha"] == "embedded-commit"


def test_health_assessment_is_absent_when_server_has_no_assessment(api):
    api.add("projects", _project("alpha"))
    api.add("snapshots", _snapshot("alpha"))

    project = api.client.get("/snapshots/latest").json()["projects"][0]
    assert "healthAssessment" not in project
    assert api.client.get("/projects/alpha/health-assessment").json()["assessment"] is None


def test_production_ci_token_is_accepted():
    settings = Settings(environment="production", agent_ingest_token="ci-secret")

    user = asyncio.run(get_ci_ingest_user(token="ci-secret", settings=settings))

    assert user.subject == "ci-agent"
    assert Role.PORTFOLIO_LEADER in user.roles


def test_invalid_production_ci_token_is_rejected():
    settings = Settings(environment="production", agent_ingest_token="ci-secret")

    with pytest.raises(HTTPException) as error:
        asyncio.run(get_ci_ingest_user(token="wrong-secret", settings=settings))

    assert getattr(error.value, "status_code", None) == 401


def test_missing_production_ci_token_is_rejected():
    settings = Settings(environment="production", agent_ingest_token="ci-secret")

    with pytest.raises(HTTPException) as error:
        asyncio.run(get_ci_ingest_user(token=None, settings=settings))

    assert getattr(error.value, "status_code", None) == 401
