"""Postgres-backed store, interface-identical to ``SqliteStore``.

Exists because the deployed SQLite file lives on a container filesystem that
does not survive a deploy. Everything storage-agnostic -- the collection /
table / model registry, ``_encode`` / ``_decode``, and the ``_extra_cols``
projection -- is imported from ``backend.db`` rather than duplicated, so the
two backends cannot drift in what they persist.

Faithful-translation notes, where Postgres and SQLite differ:

* Dates and timestamps stay **TEXT**, exactly as SQLite stored them. ISO-8601
  sorts lexicographically, so ``ORDER BY week_start DESC`` keeps its meaning
  and no value changes shape on the way through. Switching these to ``date`` /
  ``timestamptz`` would be a nicer schema and a much larger change, since
  every read would then hand back objects the models currently receive as
  strings.
* ``data`` becomes **JSONB**. asyncpg hands JSONB back as ``str``, which is
  what ``_decode`` already expects, and it leaves the door open to pushing
  filters into SQL later instead of decoding whole tables in Python.
* ``INSERT OR REPLACE`` becomes ``ON CONFLICT (id) DO UPDATE``.
* The snapshot immutability triggers become one plpgsql function. ``clear()``
  uses ``TRUNCATE``, which by design does not fire row-level DELETE triggers,
  so the immutability guard does not have to be torn down and rebuilt.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any, TypeVar
from urllib.parse import urlsplit

from .ci_agent import AssessmentDocument
from .db import (
    _MODEL_MAP,
    _TABLE_MAP,
    _decode,
    _encode,
    _ensure_id,
    _extra_cols,
    _logical,
    _record_id,
)
from .errors import ImmutableSnapshotError
from .models import (
    BoundaryDocument,
    ProjectDocument,
    WarningDocument,
    WeeklySnapshotDocument,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


POSTGRES_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL,
    data        JSONB NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_pid ON projects(project_id);

CREATE TABLE IF NOT EXISTS boundaries (
    id             TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to   TEXT,
    data           JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_boundaries_pid ON boundaries(project_id);

CREATE TABLE IF NOT EXISTS identity_map (
    id   TEXT PRIMARY KEY,
    data JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS repo_activity (
    id           TEXT PRIMARY KEY,
    project_id   TEXT,
    repo_slug    TEXT NOT NULL,
    window_start TEXT NOT NULL,
    data         JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_repo_activity_pid    ON repo_activity(project_id);
CREATE INDEX IF NOT EXISTS idx_repo_activity_window ON repo_activity(project_id, window_start);

CREATE TABLE IF NOT EXISTS weekly_snapshots (
    id               TEXT PRIMARY KEY,
    project_id       TEXT NOT NULL,
    week_start       TEXT NOT NULL,
    rule_set_version TEXT NOT NULL,
    generated_at     TEXT NOT NULL,
    data             JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_pid ON weekly_snapshots(project_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_snapshots_key
    ON weekly_snapshots(project_id, week_start, rule_set_version);

CREATE OR REPLACE FUNCTION phi_snapshots_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'weekly snapshots are immutable';
END;
$$ LANGUAGE plpgsql;

-- CREATE TRIGGER IF NOT EXISTS does not exist before PG14, and CREATE OR
-- REPLACE TRIGGER not before PG14 either; drop-then-create works everywhere
-- and is idempotent.
DROP TRIGGER IF EXISTS trig_snapshots_no_update ON weekly_snapshots;
CREATE TRIGGER trig_snapshots_no_update
    BEFORE UPDATE ON weekly_snapshots
    FOR EACH ROW EXECUTE FUNCTION phi_snapshots_immutable();

DROP TRIGGER IF EXISTS trig_snapshots_no_delete ON weekly_snapshots;
CREATE TRIGGER trig_snapshots_no_delete
    BEFORE DELETE ON weekly_snapshots
    FOR EACH ROW EXECUTE FUNCTION phi_snapshots_immutable();

CREATE TABLE IF NOT EXISTS warnings (
    id          TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL,
    project_id  TEXT NOT NULL,
    data        JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_warnings_sid ON warnings(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_warnings_pid ON warnings(project_id);

CREATE TABLE IF NOT EXISTS feedback (
    id          TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL,
    project_id  TEXT NOT NULL,
    data        JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feedback_sid ON feedback(snapshot_id);

CREATE TABLE IF NOT EXISTS audit_log (
    id   TEXT PRIMARY KEY,
    at   TEXT NOT NULL,
    data JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_at ON audit_log(at);

CREATE TABLE IF NOT EXISTS ci_assessments (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL,
    assessment_id TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    data          JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assessments_pid     ON ci_assessments(project_id);
CREATE INDEX IF NOT EXISTS idx_assessments_created ON ci_assessments(project_id, created_at);

CREATE TABLE IF NOT EXISTS cumulative_checkpoints (
    id               TEXT PRIMARY KEY,
    project_id       TEXT NOT NULL,
    as_of_week_start TEXT NOT NULL,
    signal_version   TEXT NOT NULL,
    data             JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_checkpoints_pid ON cumulative_checkpoints(project_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_checkpoints_key
    ON cumulative_checkpoints(project_id, as_of_week_start, signal_version);
"""


def looks_like_pooled_dsn(dsn: str) -> bool:
    """Whether this DSN points at a connection pooler in transaction mode.

    Supabase's pooler (``*.pooler.supabase.com``, port 6543) multiplexes many
    clients onto few server connections, which makes server-side prepared
    statements unsafe: asyncpg prepares a statement on one backend and may be
    handed a different one for the execute. The symptom is an intermittent
    ``prepared statement "__asyncpg_stmt_x__" does not exist`` under
    concurrency, not a clean failure at startup, so it is worth detecting
    rather than leaving to be discovered in production.
    """
    try:
        parts = urlsplit(dsn)
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    return parts.port == 6543 or "pooler." in host


class PostgresStore:
    """Async repository over an asyncpg pool. Mirrors ``SqliteStore`` exactly."""

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    # ------------------------------------------------------------------
    # Low-level row helpers
    # ------------------------------------------------------------------

    async def _insert_row(self, table: str, logical: str, doc: Any) -> None:
        doc_id = _record_id(doc)
        data = _encode(doc)
        extra = _extra_cols(logical, doc)
        cols = ["id", "data"] + list(extra.keys())
        values = [doc_id, data] + list(extra.values())
        # data is column 2, and JSONB needs the cast from the text parameter.
        placeholders = ", ".join(
            f"${i}::jsonb" if i == 2 else f"${i}" for i in range(1, len(cols) + 1)
        )
        if table == "weekly_snapshots":
            # Plain INSERT, so a duplicate raises rather than silently
            # replacing an immutable row -- the SQLite backend's behaviour.
            sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
        else:
            updates = ", ".join(
                f"{col} = EXCLUDED.{col}" for col in cols if col != "id"
            )
            sql = (
                f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders}) "
                f"ON CONFLICT (id) DO UPDATE SET {updates}"
            )
        async with self._pool.acquire() as conn:
            await conn.execute(sql, *values)

    async def _update_row(self, table: str, logical: str, doc: Any) -> None:
        if table == "weekly_snapshots":
            raise ImmutableSnapshotError("weekly snapshots are immutable")
        doc_id = _record_id(doc)
        data = _encode(doc)
        extra = _extra_cols(logical, doc)
        set_parts = ["data = $1::jsonb"] + [
            f"{col} = ${i}" for i, col in enumerate(extra.keys(), start=2)
        ]
        values = [data] + list(extra.values()) + [doc_id]
        sql = f"UPDATE {table} SET {', '.join(set_parts)} WHERE id = ${len(values)}"
        async with self._pool.acquire() as conn:
            await conn.execute(sql, *values)

    async def _fetch_all(self, table: str, model: type[T]) -> list[T]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(f"SELECT data FROM {table}")
        return [_decode(model, row["data"]) for row in rows]

    async def _fetch(self, sql: str, *args: Any) -> list[Any]:
        async with self._pool.acquire() as conn:
            return await conn.fetch(sql, *args)

    async def _fetchrow(self, sql: str, *args: Any) -> Any:
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(sql, *args)

    # ------------------------------------------------------------------
    # Generic repository interface
    # ------------------------------------------------------------------

    async def add(self, collection: str, item: T) -> T:
        _ensure_id(item)
        logical = _logical(collection)
        await self._insert_row(_TABLE_MAP[logical], logical, item)
        return item

    async def insert(self, item: T) -> T:
        _ensure_id(item)
        settings_name = getattr(getattr(item, "Settings", None), "name", None)
        if settings_name is None:
            raise ValueError(f"{type(item).__name__} has no Settings.name")
        return await self.add(settings_name, item)

    async def insert_many(self, items: Iterable[T]) -> list[T]:
        inserted: list[T] = []
        for item in items:
            inserted.append(await self.insert(item))
        return inserted

    async def replace(self, item: T) -> T:
        if isinstance(item, WeeklySnapshotDocument):
            raise ImmutableSnapshotError("weekly snapshots are immutable")
        logical = _logical(getattr(getattr(item, "Settings", None), "name", ""))
        await self._update_row(_TABLE_MAP[logical], logical, item)
        return item

    async def list(self, collection: str) -> list[Any]:
        logical = _logical(collection)
        return await self._fetch_all(_TABLE_MAP[logical], _MODEL_MAP[logical])

    async def find_one(self, model: type[T], **filters: Any) -> T | None:
        collection = _logical(model.Settings.name)
        rows = await self._fetch_all(_TABLE_MAP[collection], model)
        return next(
            (
                row
                for row in rows
                if all(getattr(row, field, None) == val for field, val in filters.items())
            ),
            None,
        )

    async def find_many(self, model: type[T], **filters: Any) -> list[T]:
        collection = _logical(model.Settings.name)
        rows = await self._fetch_all(_TABLE_MAP[collection], model)
        return [
            row
            for row in rows
            if all(getattr(row, field, None) == val for field, val in filters.items())
        ]

    async def has_any(self, collection: str) -> bool:
        table = _TABLE_MAP[_logical(collection)]
        return await self._fetchrow(f"SELECT 1 FROM {table} LIMIT 1") is not None

    # ------------------------------------------------------------------
    # Optimised lookup methods (use indexed WHERE clauses)
    # ------------------------------------------------------------------

    async def get_project(self, project_id: str) -> ProjectDocument | None:
        row = await self._fetchrow("SELECT data FROM projects WHERE project_id = $1", project_id)
        return _decode(ProjectDocument, row["data"]) if row else None

    async def boundary_at(self, project_id: str, at: Any = None) -> BoundaryDocument | None:
        rows = await self._fetch("SELECT data FROM boundaries WHERE project_id = $1", project_id)
        docs = [_decode(BoundaryDocument, row["data"]) for row in rows]
        if at is not None:
            docs = [doc for doc in docs if doc.is_effective_at(at)]
        return max(docs, key=lambda doc: doc.effective_from, default=None)

    async def latest_snapshot(self, project_id: str) -> WeeklySnapshotDocument | None:
        row = await self._fetchrow(
            """SELECT data FROM weekly_snapshots
               WHERE project_id = $1
               ORDER BY week_start DESC, generated_at DESC
               LIMIT 1""",
            project_id,
        )
        return _decode(WeeklySnapshotDocument, row["data"]) if row else None

    async def snapshot_by_id(self, snapshot_id: str) -> WeeklySnapshotDocument | None:
        row = await self._fetchrow("SELECT data FROM weekly_snapshots WHERE id = $1", snapshot_id)
        return _decode(WeeklySnapshotDocument, row["data"]) if row else None

    async def warning_by_id(self, warning_id: str) -> WarningDocument | None:
        row = await self._fetchrow("SELECT data FROM warnings WHERE id = $1", warning_id)
        return _decode(WarningDocument, row["data"]) if row else None

    async def warnings_for_snapshot(self, snapshot_id: str) -> list[WarningDocument]:
        rows = await self._fetch("SELECT data FROM warnings WHERE snapshot_id = $1", snapshot_id)
        return [_decode(WarningDocument, row["data"]) for row in rows]

    async def latest_assessment(self, project_id: str) -> AssessmentDocument | None:
        row = await self._fetchrow(
            """SELECT data FROM ci_assessments
               WHERE project_id = $1
               ORDER BY created_at DESC, assessment_id DESC
               LIMIT 1""",
            project_id,
        )
        return _decode(AssessmentDocument, row["data"]) if row else None

    async def clear(self) -> None:
        """Delete all rows from every collection (test / dev utility only).

        TRUNCATE does not fire row-level DELETE triggers, so the snapshot
        immutability guard stays installed rather than being dropped and
        rebuilt the way the SQLite backend has to.
        """
        tables = ", ".join(sorted(set(_TABLE_MAP.values())))
        async with self._pool.acquire() as conn:
            await conn.execute(f"TRUNCATE {tables}")


async def create_pool(dsn: str, *, min_size: int, max_size: int, timeout: float) -> Any:
    """Open the asyncpg pool and apply the schema.

    Prepared statements are disabled whenever the DSN looks pooled -- see
    :func:`looks_like_pooled_dsn`.
    """
    import asyncpg  # imported here so asyncpg stays an optional dependency

    kwargs: dict[str, Any] = {
        "min_size": min_size,
        "max_size": max_size,
        "command_timeout": timeout,
    }
    if looks_like_pooled_dsn(dsn):
        # asyncpg caches prepared statements per connection; behind a
        # transaction-mode pooler that cache is invalid the moment the pooler
        # reassigns the backend.
        kwargs["statement_cache_size"] = 0
        logger.info("connecting to Postgres through a transaction pooler; prepared statements disabled")

    pool = await asyncpg.create_pool(dsn, **kwargs)
    async with pool.acquire() as conn:
        await conn.execute(POSTGRES_SCHEMA_SQL)
    return pool
