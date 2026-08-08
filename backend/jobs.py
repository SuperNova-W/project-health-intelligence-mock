"""Pull-only scheduled jobs and immutable weekly snapshot orchestration.

The job layer consumes the aggregate records produced by
``backend.ingestion`` and the pure functions in ``backend.rules``.  It does
not import notification clients or expose source payloads.  Every write is an
append, and a snapshot is only created after its warning evidence has been
validated.
"""

from __future__ import annotations

import inspect
import os
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, timedelta, timezone
from typing import Any

from beanie import PydanticObjectId

from .config import Settings, get_settings
from .db import get_active_repository
from .ingestion import (
    AuthentikTeamHierarchyAdapter,
    GiteaRepoActivityAdapter,
    SyncResult,
)
from .models import (
    AggregateMetrics,
    AttentionStatus,
    EvidenceReference,
    WarningDocument,
    WarningEvidenceItem,
    WarningSeverity,
    WeeklySnapshotDocument,
)
from .rules import evaluate_mvp_rules


WEEKLY_SNAPSHOTS_COLLECTION = "weekly_snapshots"


def _document(model: type[Any], **values: Any) -> Any:
    """Construct a Beanie document without requiring a live collection.

    The local/demo repository deliberately runs without Mongo initialization.
    ``model_construct`` keeps that path usable while production persistence
    still receives the same validated field values through the repository.
    """

    return model.model_construct(**values)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    if isinstance(value, str):
        candidate = value.strip()
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _iso(value: Any) -> str | None:
    parsed = _parse_datetime(value)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if parsed else None


def _field(row: Any, name: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(name, default)
    return getattr(row, name, default)


def _record_id(row: Any) -> str | None:
    for name in ("id", "_id", "source_ref", "snapshot_id"):
        value = _field(row, name)
        if value not in (None, ""):
            return str(value)
    return None


def _metric_map(row: Any) -> dict[str, Any]:
    if hasattr(row, "aggregate_metrics"):
        try:
            metrics = row.aggregate_metrics()
            return metrics.model_dump(exclude_none=True)
        except (AttributeError, TypeError, ValueError):
            pass
    raw = _field(row, "metrics", {})
    result = dict(raw) if isinstance(raw, Mapping) else {}
    metric_names = (
        "active_days",
        "days_since_activity",
        "open_prs",
        "oldest_open_pr_days",
        "review_latency_days",
        "merged_count",
        "active_contributors",
        "team_size",
        "aggregation_floor",
        "data_completeness_pct",
        "last_sync_at",
    )
    for name in metric_names:
        value = _field(row, name)
        if value is not None:
            result[name] = value
    source_ref = _record_id(row)
    if source_ref:
        result["source_ref"] = source_ref
    return result


def _project_ids(row: Any) -> list[str]:
    value = _field(row, "project_ids")
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [str(item) for item in value if item not in (None, "")]
    project_id = _field(row, "project_id")
    return [str(project_id)] if project_id not in (None, "") else []


def _history_by_project(rows: Sequence[Any]) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for row in rows:
        week = _field(row, "window_start", _field(row, "week_start", _field(row, "snapshot_week_start")))
        for project_id in _project_ids(row):
            buckets[(project_id, str(week or "unknown"))].append(row)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (project_id, week), bucket in buckets.items():
        metric_rows = [_metric_map(row) for row in bucket]
        combined: dict[str, Any] = {
            "week_start": next(
                (
                    _field(row, "window_start", _field(row, "week_start", _field(row, "snapshot_week_start")))
                    for row in bucket
                    if _field(row, "window_start", _field(row, "week_start", _field(row, "snapshot_week_start"))) is not None
                ),
                week if week != "unknown" else None,
            ),
            "source_ref": f"project_activity:{project_id}:{week}",
        }
        # A project-level observation is the aggregate across all repos in its
        # effective boundary. Distinct commit days are used when raw rows have
        # them; model-only rows fall back to the additive aggregate.
        commit_days: set[str] = set()
        active_day_sum = 0
        for row, metrics in zip(bucket, metric_rows):
            raw_days = _field(row, "commit_days")
            if isinstance(raw_days, Sequence) and not isinstance(raw_days, (str, bytes)):
                commit_days.update(str(day) for day in raw_days)
            elif isinstance(metrics.get("active_days"), (int, float)):
                active_day_sum += int(metrics["active_days"])
        combined["active_days"] = len(commit_days) if commit_days else active_day_sum

        def numeric_values(name: str) -> list[float]:
            return [
                float(metrics[name])
                for metrics in metric_rows
                if isinstance(metrics.get(name), (int, float)) and not isinstance(metrics.get(name), bool)
            ]

        for name, operation in (
            ("days_since_activity", min),
            ("oldest_open_pr_days", max),
            ("open_prs", sum),
            ("merged_count", sum),
        ):
            values = numeric_values(name)
            if values:
                result = operation(values)
                combined[name] = int(result) if name == "open_prs" or name == "merged_count" else result
        latency_values = numeric_values("review_latency_days")
        if latency_values:
            combined["review_latency_days"] = sum(latency_values) / len(latency_values)

        # Contributor counts cannot be de-duplicated safely across repositories
        # without retaining identities.  Only preserve the aggregate when one
        # repository is represented and it explicitly passed the floor gate.
        if len(bucket) == 1 and isinstance(metric_rows[0].get("active_contributors"), (int, float)):
            combined["active_contributors"] = int(metric_rows[0]["active_contributors"])
            if isinstance(metric_rows[0].get("team_size"), int):
                combined["team_size"] = metric_rows[0]["team_size"]
        completeness_values = numeric_values("data_completeness_pct")
        if completeness_values:
            combined["data_completeness_pct"] = min(completeness_values)
        sync_times = [
            _parse_datetime(metrics.get("last_sync_at"))
            for metrics in metric_rows
            if _parse_datetime(metrics.get("last_sync_at")) is not None
        ]
        if sync_times:
            combined["last_sync_at"] = max(sync_times)
        combined["lifecycle_state"] = _field(bucket[0], "lifecycle_state")
        grouped[project_id].append(combined)
    for records in grouped.values():
        records.sort(key=lambda item: str(item.get("week_start") or ""))
    return grouped


def _warning_evidence(result: Mapping[str, Any], project_id: str) -> list[WarningEvidenceItem]:
    evidence = result.get("evidence")
    if not isinstance(evidence, Mapping):
        return []
    observations = evidence.get("observations")
    if not isinstance(observations, Sequence) or isinstance(observations, (str, bytes)):
        return []

    references: list[EvidenceReference] = []
    for observation in observations:
        if not isinstance(observation, Mapping):
            continue
        raw_source = observation.get("source_ref")
        source_id: str | None = None
        if isinstance(raw_source, Mapping):
            value = raw_source.get("ref")
            if value not in (None, ""):
                source_id = str(value)
        elif raw_source not in (None, ""):
            source_id = str(raw_source)
        if source_id is None:
            continue
        observed_at = _parse_datetime(observation.get("last_sync_at")) or _utc_now()
        references.append(
            EvidenceReference(
                source_collection="repo_activity",
                source_id=source_id,
                source_field=str(observation.get("metric") or "aggregate_metrics"),
                observed_at=observed_at,
            )
        )

    if not references:
        return []
    return [
        WarningEvidenceItem(
            evidence_type=str(evidence.get("type", "metric")),
            icon=str(evidence.get("icon", "activity")),
            title=str(evidence.get("title", "Aggregate signal")),
            metric=str(evidence.get("metric")) if evidence.get("metric") is not None else None,
            unit=str(evidence.get("unit", "")),
            current=evidence.get("current"),
            baseline=evidence.get("baseline"),
            source_refs=references,
        )
    ]


def _warning_severity(triggered_count: int) -> WarningSeverity:
    return WarningSeverity.CRITICAL if triggered_count >= 3 else WarningSeverity.WARNING


def _status_for_results(
    results: Mapping[str, Mapping[str, Any]],
    *,
    current: Mapping[str, Any],
    aggregation_floor: int,
) -> AttentionStatus:
    if not current:
        return AttentionStatus.INSUFFICIENT_DATA
    completeness = current.get("data_completeness_pct")
    try:
        if completeness is None or float(completeness) < 80:
            return AttentionStatus.INSUFFICIENT_DATA
    except (TypeError, ValueError):
        return AttentionStatus.INSUFFICIENT_DATA
    triggered = [
        result
        for result in results.values()
        if result.get("meets_minimum_data") and result.get("evidence")
    ]
    return (
        AttentionStatus.AT_RISK
        if len(triggered) >= 2
        else AttentionStatus.WATCH
        if triggered
        else AttentionStatus.CLEAR
    )


async def _call_sync(adapter: Any, kwargs: Mapping[str, Any]) -> SyncResult:
    sync = getattr(adapter, "sync", adapter if callable(adapter) else None)
    if sync is None:
        raise TypeError("sync adapter must expose sync() or be callable")
    try:
        result = sync(**dict(kwargs))
    except TypeError:
        try:
            signature = inspect.signature(sync)
            accepted = {name: value for name, value in kwargs.items() if name in signature.parameters}
            result = sync(**accepted) if accepted else sync()
        except (TypeError, ValueError):
            result = sync()
    if inspect.isawaitable(result):
        result = await result
    if isinstance(result, SyncResult):
        return result
    if isinstance(result, Mapping):
        return SyncResult(
            status=str(result.get("status", "ok")),
            sync_cycle_id=str(result.get("sync_cycle_id", "")),
            synced_at=str(result.get("synced_at", "")),
            records_written=int(result.get("records_written", 0) or 0),
            evidence_rows_written=int(result.get("evidence_rows_written", 0) or 0),
            repos_seen=int(result.get("repos_seen", 0) or 0),
            data_quality_flags=tuple(str(item) for item in result.get("data_quality_flags", ()) or ()),
            message=str(result["message"]) if result.get("message") else None,
        )
    raise TypeError("sync hook returned an unsupported result")


async def run_nightly_sync(
    settings: Settings | None = None,
    database: Any = None,
    *,
    authentik_adapter: Any = None,
    gitea_adapter: Any = None,
    now: datetime | None = None,
    lookback_days: int = 14,
) -> dict[str, Any]:
    """Run nightly pulls; missing endpoints are a normal no-op status."""

    settings = settings or get_settings()
    database = database or get_active_repository()
    started = now or _utc_now()
    cycle_id = f"sync_{started.strftime('%Y%m%d%H%M%S')}_{started.microsecond}"
    if authentik_adapter is None:
        authentik_adapter = AuthentikTeamHierarchyAdapter(
            database,
            base_url=settings.authentik_url,
            token=settings.authentik_api_token,
            aggregation_floor=settings.aggregation_floor,
        )
    if gitea_adapter is None:
        authentik_org = os.getenv("GITEA_ORG") or os.getenv("GITEA_ORGANIZATION")
        gitea_adapter = GiteaRepoActivityAdapter(
            database,
            base_url=settings.gitea_url,
            token=settings.gitea_api_token,
            organization=authentik_org,
            aggregation_floor=settings.aggregation_floor,
        )
    try:
        team_result = await _call_sync(
            authentik_adapter,
            {"sync_cycle_id": cycle_id, "synced_at": _iso(started)},
        )
        repo_result = await _call_sync(
            gitea_adapter,
            {
                "sync_cycle_id": cycle_id,
                "synced_at": _iso(started),
                "since": started - timedelta(days=max(0, int(lookback_days))),
                "until": started,
                "backfill": False,
            },
        )
        statuses = {team_result.status, repo_result.status}
        return {
            "status": (
                "ok"
                if statuses == {"ok"}
                else "not_configured"
                if statuses == {"not_configured"}
                else "partial"
            ),
            "sync_cycle_id": cycle_id,
            "authentik": team_result.as_dict(),
            "gitea": repo_result.as_dict(),
            "outbound_notifications": False,
        }
    finally:
        for adapter in (authentik_adapter, gitea_adapter):
            closer = getattr(adapter, "close", None)
            if closer is not None:
                closer()


async def run_historical_backfill(
    adapter: Any,
    *,
    start_at: date | datetime | str | None = None,
    end_at: date | datetime | str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run an explicit historical Gitea replay as a new append-only cycle."""

    captured = now or _utc_now()
    result = await _call_sync(
        adapter,
        {
            "start_at": start_at,
            "end_at": end_at,
            "backfill": True,
            "synced_at": _iso(captured),
        },
    )
    return {"status": result.status, "job": "historical_backfill", **result.as_dict()}


async def generate_weekly_snapshots(
    settings: Settings | None = None,
    database: Any = None,
    week_start: date | None = None,
    rule_set_version: str | None = None,
) -> int:
    """Append one immutable, evidence-backed snapshot per project."""

    settings = settings or get_settings()
    database = database or get_active_repository()
    now = _utc_now()
    week_start = week_start or now.date() - timedelta(days=now.weekday())
    week_end = week_start + timedelta(days=6)
    version = rule_set_version or settings.rule_set_version
    projects = await database.list("projects")
    activity_rows = await database.list("repo_activity")
    histories = _history_by_project(activity_rows)
    created = 0

    for project in projects:
        project_id = str(project.project_id)
        decision = project.scoring_decision(week_start, week_end)
        history = histories.get(project_id, [])
        # A current empty record keeps the rule engine's insufficient-data
        # status explicit instead of allowing an empty history to look clear.
        if not history:
            history = [{"week_start": week_start, "data_completeness_pct": 0, "source_ref": f"missing:{project_id}:{week_start}"}]
        current = history[-1]
        rule_input = {
            "weeks": history,
            "current": current,
            "lifecycle_state": project.lifecycle_state.value,
        }
        results = evaluate_mvp_rules(
            rule_input,
            aggregation_floor=settings.aggregation_floor,
        )

        if decision.suppressed:
            status = decision.status or AttentionStatus.INSUFFICIENT_DATA
            results = {}
        else:
            status = _status_for_results(
                results,
                current=current,
                aggregation_floor=settings.aggregation_floor,
            )

        metrics_payload = {
            key: value
            for key, value in _metric_map(current).items()
            if key
            in {
                "active_days",
                "days_since_activity",
                "open_prs",
                "oldest_open_pr_days",
                "review_latency_days",
                "merged_count",
                "active_contributors",
                "team_size",
                "aggregation_floor",
                "data_completeness_pct",
                "last_sync_at",
            }
        }
        if "active_contributors" in metrics_payload:
            team_size = metrics_payload.get("team_size")
            if not isinstance(team_size, int) or team_size < settings.aggregation_floor:
                metrics_payload.pop("active_contributors", None)
                metrics_payload.pop("team_size", None)
        metrics_payload["data_completeness_pct"] = float(metrics_payload.get("data_completeness_pct", 0) or 0)
        metrics_payload["last_sync_at"] = _parse_datetime(metrics_payload.get("last_sync_at"))
        metrics = AggregateMetrics(**metrics_payload)

        warning_documents: list[WarningDocument] = []
        triggered_count = sum(1 for result in results.values() if result.get("meets_minimum_data") and result.get("evidence"))
        snapshot_id = PydanticObjectId()
        for rule_id, result in results.items():
            if not result.get("meets_minimum_data") or not result.get("evidence"):
                continue
            evidence_items = _warning_evidence(result, project_id)
            if not evidence_items:
                # A warning without an inspectable evidence row is a bug; do
                # not persist the warning or downgrade it to an unexplained UI
                # signal.
                raise ValueError(f"rule {rule_id} produced no source evidence")
            evidence = result["evidence"]
            warning_documents.append(
                _document(WarningDocument,
                    id=PydanticObjectId(),
                    snapshot_id=snapshot_id,
                    project_id=project_id,
                    rule_id=rule_id,
                    rule_version=version,
                    signal_name=str(evidence.get("title", rule_id)),
                    current_value=result.get("value"),
                    baseline_value=result.get("baseline"),
                    time_window=str(result.get("window", "")),
                    trigger_threshold=(evidence.get("trigger") or {}).get("threshold"),
                    severity=_warning_severity(triggered_count),
                    explanation=str(evidence.get("title", "Aggregate rule triggered")),
                    data_freshness=str(current.get("last_sync_at") or "unknown"),
                    data_completeness_pct=float(current.get("data_completeness_pct", 0) or 0),
                    evidence=evidence_items,
                )
            )

        snapshot = _document(WeeklySnapshotDocument,
            id=snapshot_id,
            project_id=project_id,
            week_start=week_start,
            week_end=week_end,
            rule_set_version=version,
            generated_at=now,
            attention_status=status,
            data_completeness_pct=metrics.data_completeness_pct or 0,
            last_sync_at=metrics.last_sync_at,
            metrics=metrics,
            baselines=None,
            warning_ids=[warning.id for warning in warning_documents if warning.id is not None],
        )
        for warning in warning_documents:
            await database.add("warnings", warning)
        # This is intentionally add/insert only. No existing snapshot is read
        # or mutated, so reruns remain new historical records with a version.
        await database.add("snapshots", snapshot)
        created += 1
    return created


async def run_weekly_snapshot_job(
    settings: Settings | None = None,
    database: Any = None,
    *,
    week_start: date | None = None,
    rule_set_version: str | None = None,
) -> dict[str, Any]:
    database = database or get_active_repository()
    created = await generate_weekly_snapshots(
        settings=settings,
        database=database,
        week_start=week_start,
        rule_set_version=rule_set_version,
    )
    return {
        "status": "ok",
        "job": "weekly_snapshot",
        "snapshots_written": created,
        "outbound_notifications": False,
    }


class ScheduledJobHooks:
    """Register nightly and weekly callbacks with an injected scheduler."""

    def __init__(self, nightly: Callable[[], Any], weekly: Callable[[], Any]) -> None:
        self.nightly = nightly
        self.weekly = weekly

    def register(
        self,
        scheduler: Any,
        *,
        nightly_hour: int = 2,
        nightly_minute: int = 0,
        weekly_day: str = "mon",
        weekly_hour: int = 5,
        weekly_minute: int = 0,
    ) -> Any:
        scheduler.add_job(
            self.nightly,
            trigger="cron",
            id="phi-nightly-sync",
            day_of_week="*",
            hour=nightly_hour,
            minute=nightly_minute,
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            self.weekly,
            trigger="cron",
            id="phi-weekly-snapshot",
            day_of_week=weekly_day,
            hour=weekly_hour,
            minute=weekly_minute,
            max_instances=1,
            coalesce=True,
        )
        return scheduler


def register_scheduled_jobs(
    scheduler: Any,
    *,
    nightly: Callable[[], Any],
    weekly: Callable[[], Any],
    nightly_hour: int = 2,
    nightly_minute: int = 0,
    weekly_day: str = "mon",
    weekly_hour: int = 5,
    weekly_minute: int = 0,
) -> Any:
    return ScheduledJobHooks(nightly, weekly).register(
        scheduler,
        nightly_hour=nightly_hour,
        nightly_minute=nightly_minute,
        weekly_day=weekly_day,
        weekly_hour=weekly_hour,
        weekly_minute=weekly_minute,
    )


# Stable hook names for scheduler wiring and older deployment manifests.
nightly_sync_job = run_nightly_sync
weekly_snapshot_job = run_weekly_snapshot_job
register_jobs = register_scheduled_jobs


__all__ = [
    "WEEKLY_SNAPSHOTS_COLLECTION",
    "run_nightly_sync",
    "run_historical_backfill",
    "generate_weekly_snapshots",
    "run_weekly_snapshot_job",
    "nightly_sync_job",
    "weekly_snapshot_job",
    "ScheduledJobHooks",
    "register_scheduled_jobs",
    "register_jobs",
]
