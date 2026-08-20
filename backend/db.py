"""SQLite-backed async repository replacing the former Beanie/Motor stack.

``:memory:`` is a fully supported path so the same code serves tests, local
development, and production — no dual-mode branching.

WAL journal mode and a generous busy-timeout let multiple readers coexist with
the nightly writer without contention errors.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, TypeVar

import aiosqlite

from .ci_agent import AssessmentDocument
from .config import Settings, get_settings
from .errors import ImmutableSnapshotError
from .models import (
    AuditLogDocument,
    BoundaryDocument,
    FeedbackDocument,
    IdentityMapDocument,
    ProjectDocument,
    RepoActivityDocument,
    WarningDocument,
    WeeklySnapshotDocument,
    new_id,
)

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Schema DDL — only CREATE TABLE / INDEX / TRIGGER, no PRAGMAs
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL,
    data        TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_pid ON projects(project_id);

CREATE TABLE IF NOT EXISTS boundaries (
    id             TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to   TEXT,
    data           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_boundaries_pid ON boundaries(project_id);

CREATE TABLE IF NOT EXISTS identity_map (
    id   TEXT PRIMARY KEY,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS repo_activity (
    id           TEXT PRIMARY KEY,
    project_id   TEXT,
    repo_slug    TEXT NOT NULL,
    window_start TEXT NOT NULL,
    data         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_repo_activity_pid    ON repo_activity(project_id);
CREATE INDEX IF NOT EXISTS idx_repo_activity_window ON repo_activity(project_id, window_start);

CREATE TABLE IF NOT EXISTS weekly_snapshots (
    id               TEXT PRIMARY KEY,
    project_id       TEXT NOT NULL,
    week_start       TEXT NOT NULL,
    rule_set_version TEXT NOT NULL,
    generated_at     TEXT NOT NULL,
    data             TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_pid ON weekly_snapshots(project_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_snapshots_key
    ON weekly_snapshots(project_id, week_start, rule_set_version);

CREATE TRIGGER IF NOT EXISTS trig_snapshots_no_update
    BEFORE UPDATE ON weekly_snapshots
BEGIN
    SELECT RAISE(ABORT, 'weekly snapshots are immutable');
END;

CREATE TRIGGER IF NOT EXISTS trig_snapshots_no_delete
    BEFORE DELETE ON weekly_snapshots
BEGIN
    SELECT RAISE(ABORT, 'weekly snapshots are immutable');
END;

CREATE TABLE IF NOT EXISTS warnings (
    id          TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL,
    project_id  TEXT NOT NULL,
    data        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_warnings_sid ON warnings(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_warnings_pid ON warnings(project_id);

CREATE TABLE IF NOT EXISTS feedback (
    id          TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL,
    project_id  TEXT NOT NULL,
    data        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feedback_sid ON feedback(snapshot_id);

CREATE TABLE IF NOT EXISTS audit_log (
    id   TEXT PRIMARY KEY,
    at   TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_at ON audit_log(at);

CREATE TABLE IF NOT EXISTS ci_assessments (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL,
    assessment_id TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    data          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assessments_pid     ON ci_assessments(project_id);
CREATE INDEX IF NOT EXISTS idx_assessments_created ON ci_assessments(project_id, created_at);
"""

# ---------------------------------------------------------------------------
# Collection → table / model registry
# ---------------------------------------------------------------------------

_COLLECTION_ALIASES: dict[str, str] = {
    "weekly_snapshots": "snapshots",
    "assessments": "assessments",
    "ci_assessments": "assessments",
}

_TABLE_MAP: dict[str, str] = {
    "projects": "projects",
    "boundaries": "boundaries",
    "identity_map": "identity_map",
    "repo_activity": "repo_activity",
    "snapshots": "weekly_snapshots",
    "warnings": "warnings",
    "feedback": "feedback",
    "audit_log": "audit_log",
    "assessments": "ci_assessments",
}

_MODEL_MAP: dict[str, type[Any]] = {
    "projects": ProjectDocument,
    "boundaries": BoundaryDocument,
    "identity_map": IdentityMapDocument,
    "repo_activity": RepoActivityDocument,
    "snapshots": WeeklySnapshotDocument,
    "warnings": WarningDocument,
    "feedback": FeedbackDocument,
    "audit_log": AuditLogDocument,
    "assessments": AssessmentDocument,
}


def _logical(collection: str) -> str:
    return _COLLECTION_ALIASES.get(collection, collection)


# ---------------------------------------------------------------------------
# Encoding / decoding helpers
# ---------------------------------------------------------------------------

def _encode(doc: Any) -> str:
    """Serialize a document to a JSON string for storage.

    Computed fields are excluded so that ``model_validate`` doesn't see them
    as extra fields and raise a ``ValidationError`` (``extra='forbid'``).
    """
    if hasattr(doc, "model_dump"):
        computed = set(getattr(type(doc), "model_computed_fields", {}).keys())
        payload = doc.model_dump(
            mode="json",
            by_alias=False,
            exclude_none=False,
            exclude=computed or None,
        )
    else:
        payload = dict(doc)
    return json.dumps(payload, default=str)


def _decode(model: type[T], data: str) -> T:
    """Deserialize a JSON string back into a document model."""
    return model.model_validate(json.loads(data))


def _record_id(item: Any) -> str | None:
    value = getattr(item, "id", None)
    return str(value) if value is not None else None


def _ensure_id(item: Any) -> None:
    """Assign a new random id to the document when one is absent."""
    if getattr(item, "id", None) is None and hasattr(item, "id"):
        item.id = new_id()


def _date_str(value: Any) -> str | None:
    """Coerce a date/datetime/str to an ISO string, or None."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _extra_cols(logical: str, doc: Any) -> dict[str, Any]:
    """Return the extra indexed columns that supplement id + data for a row."""
    if logical == "projects":
        return {"project_id": str(doc.project_id)}

    if logical == "boundaries":
        return {
            "project_id": str(doc.project_id),
            "effective_from": _date_str(doc.effective_from),
            "effective_to": _date_str(getattr(doc, "effective_to", None)),
        }

    if logical == "repo_activity":
        pid = getattr(doc, "project_id", None)
        return {
            "project_id": str(pid) if pid is not None else None,
            "repo_slug": str(doc.repo_slug),
            "window_start": _date_str(doc.window_start),
        }

    if logical == "snapshots":
        return {
            "project_id": str(doc.project_id),
            "week_start": _date_str(doc.week_start),
            "rule_set_version": str(doc.rule_set_version),
            "generated_at": _date_str(doc.generated_at),
        }

    if logical == "warnings":
        return {
            "snapshot_id": str(doc.snapshot_id),
            "project_id": str(doc.project_id),
        }

    if logical == "feedback":
        return {
            "snapshot_id": str(doc.snapshot_id),
            "project_id": str(doc.project_id),
        }

    if logical == "audit_log":
        return {"at": _date_str(getattr(doc, "at", None)) or ""}

    if logical == "assessments":
        return {
            "project_id": str(doc.project_id),
            "assessment_id": str(doc.assessment_id),
            "created_at": _date_str(getattr(doc, "created_at", None)) or "",
        }

    return {}


# ---------------------------------------------------------------------------
# SqliteStore
# ---------------------------------------------------------------------------

class SqliteStore:
    """Async repository backed by a single SQLite database file.

    The interface mirrors ``InMemoryStore`` exactly so the two are
    interchangeable without conditional branching at the call sites.
    """

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Low-level row helpers
    # ------------------------------------------------------------------

    async def _insert_row(self, table: str, logical: str, doc: Any) -> None:
        doc_id = _record_id(doc)
        data = _encode(doc)
        extra = _extra_cols(logical, doc)
        cols = ["id", "data"] + list(extra.keys())
        placeholders = ", ".join("?" for _ in cols)
        values = [doc_id, data] + list(extra.values())
        # weekly_snapshots uses a plain INSERT so that the immutability trigger
        # fires on conflicts rather than silently replacing the row.
        verb = "INSERT" if table == "weekly_snapshots" else "INSERT OR REPLACE"
        sql = f"{verb} INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
        await self._db.execute(sql, values)
        await self._db.commit()

    async def _update_row(self, table: str, logical: str, doc: Any) -> None:
        if table == "weekly_snapshots":
            raise ImmutableSnapshotError("weekly snapshots are immutable")
        doc_id = _record_id(doc)
        data = _encode(doc)
        extra = _extra_cols(logical, doc)
        set_parts = ["data = ?"] + [f"{col} = ?" for col in extra.keys()]
        values = [data] + list(extra.values()) + [doc_id]
        sql = f"UPDATE {table} SET {', '.join(set_parts)} WHERE id = ?"
        await self._db.execute(sql, values)
        await self._db.commit()

    async def _fetch_all(self, table: str, model: type[T]) -> list[T]:
        async with self._db.execute(f"SELECT data FROM {table}") as cursor:
            rows = await cursor.fetchall()
        return [_decode(model, row[0]) for row in rows]

    # ------------------------------------------------------------------
    # Generic repository interface
    # ------------------------------------------------------------------

    async def add(self, collection: str, item: T) -> T:
        """Persist an item; assign an id first if the document lacks one."""
        _ensure_id(item)
        logical = _logical(collection)
        table = _TABLE_MAP[logical]
        await self._insert_row(table, logical, item)
        return item

    async def insert(self, item: T) -> T:
        """Beanie-shaped insert: assign id from Settings.name, then persist."""
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
        """Update an existing row in-place (raises for immutable snapshots)."""
        if isinstance(item, WeeklySnapshotDocument):
            raise ImmutableSnapshotError("weekly snapshots are immutable")
        logical = _logical(getattr(getattr(item, "Settings", None), "name", ""))
        table = _TABLE_MAP[logical]
        await self._update_row(table, logical, item)
        return item

    async def list(self, collection: str) -> list[Any]:
        logical = _logical(collection)
        table = _TABLE_MAP[logical]
        model = _MODEL_MAP[logical]
        return await self._fetch_all(table, model)

    async def find_one(self, model: type[T], **filters: Any) -> T | None:
        collection = _logical(model.Settings.name)
        table = _TABLE_MAP[collection]
        rows = await self._fetch_all(table, model)
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
        table = _TABLE_MAP[collection]
        rows = await self._fetch_all(table, model)
        return [
            row
            for row in rows
            if all(getattr(row, field, None) == val for field, val in filters.items())
        ]

    # ------------------------------------------------------------------
    # Optimised lookup methods (use indexed WHERE clauses)
    # ------------------------------------------------------------------

    async def get_project(self, project_id: str) -> ProjectDocument | None:
        async with self._db.execute(
            "SELECT data FROM projects WHERE project_id = ?", (project_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return _decode(ProjectDocument, row[0]) if row else None

    async def boundary_at(self, project_id: str, at: Any = None) -> BoundaryDocument | None:
        async with self._db.execute(
            "SELECT data FROM boundaries WHERE project_id = ?", (project_id,)
        ) as cursor:
            rows = await cursor.fetchall()
        docs = [_decode(BoundaryDocument, row[0]) for row in rows]
        if at is not None:
            docs = [doc for doc in docs if doc.is_effective_at(at)]
        return max(docs, key=lambda doc: doc.effective_from, default=None)

    async def latest_snapshot(self, project_id: str) -> WeeklySnapshotDocument | None:
        async with self._db.execute(
            """SELECT data FROM weekly_snapshots
               WHERE project_id = ?
               ORDER BY week_start DESC, generated_at DESC
               LIMIT 1""",
            (project_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return _decode(WeeklySnapshotDocument, row[0]) if row else None

    async def snapshot_by_id(self, snapshot_id: str) -> WeeklySnapshotDocument | None:
        async with self._db.execute(
            "SELECT data FROM weekly_snapshots WHERE id = ?", (snapshot_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return _decode(WeeklySnapshotDocument, row[0]) if row else None

    async def warning_by_id(self, warning_id: str) -> WarningDocument | None:
        async with self._db.execute(
            "SELECT data FROM warnings WHERE id = ?", (warning_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return _decode(WarningDocument, row[0]) if row else None

    async def warnings_for_snapshot(self, snapshot_id: str) -> list[WarningDocument]:
        async with self._db.execute(
            "SELECT data FROM warnings WHERE snapshot_id = ?", (snapshot_id,)
        ) as cursor:
            rows = await cursor.fetchall()
        return [_decode(WarningDocument, row[0]) for row in rows]

    async def latest_assessment(self, project_id: str) -> AssessmentDocument | None:
        async with self._db.execute(
            """SELECT data FROM ci_assessments
               WHERE project_id = ?
               ORDER BY created_at DESC, assessment_id DESC
               LIMIT 1""",
            (project_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return _decode(AssessmentDocument, row[0]) if row else None

    async def clear(self) -> None:
        """Delete all rows from every collection (test / dev utility only)."""
        # weekly_snapshots has immutability triggers on DELETE; drop and recreate.
        await self._db.execute("DROP TABLE IF EXISTS weekly_snapshots")
        await self._db.execute("DROP TRIGGER IF EXISTS trig_snapshots_no_update")
        await self._db.execute("DROP TRIGGER IF EXISTS trig_snapshots_no_delete")
        await self._db.execute("DROP INDEX IF EXISTS idx_snapshots_pid")
        await self._db.execute("DROP INDEX IF EXISTS idx_snapshots_key")
        for table in set(_TABLE_MAP.values()) - {"weekly_snapshots"}:
            await self._db.execute(f"DELETE FROM {table}")
        await self._db.commit()
        await self._db.executescript(_SCHEMA_SQL)


# ---------------------------------------------------------------------------
# Schema initialisation helper
# ---------------------------------------------------------------------------

async def _apply_schema(db: aiosqlite.Connection, busy_timeout_ms: int = 5_000) -> None:
    await db.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
    await db.execute("PRAGMA journal_mode = WAL")
    await db.execute("PRAGMA foreign_keys = ON")
    # executescript does an implicit COMMIT before running the statements,
    # which is fine here — we have no pending transaction yet.
    await db.executescript(_SCHEMA_SQL)


# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

@dataclass
class DatabaseState:
    settings: Settings
    connection: aiosqlite.Connection
    store: SqliteStore

    @property
    def in_memory(self) -> bool:
        return self.settings.sqlite_path == ":memory:"


_database_state: DatabaseState | None = None


async def init_db(settings: Settings | None = None) -> SqliteStore:
    """Open the SQLite connection, apply WAL mode, and create the schema."""
    global _database_state

    resolved = settings or get_settings()
    path = resolved.sqlite_path

    # Create the parent directory for file-based databases.
    if path != ":memory:":
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)

    db = await aiosqlite.connect(path)
    await _apply_schema(db, resolved.sqlite_busy_timeout_ms)

    store = SqliteStore(db)
    _database_state = DatabaseState(settings=resolved, connection=db, store=store)
    return store


async def close_db() -> None:
    """Close the SQLite connection and reset module state."""
    global _database_state
    if _database_state is not None:
        await _database_state.connection.close()
        _database_state = None


def get_db_state() -> DatabaseState:
    global _database_state
    if _database_state is None:
        raise RuntimeError("init_db() must be awaited before using the database")
    return _database_state


def get_active_repository() -> SqliteStore:
    """Return the initialized SQLite store (previously selected in/memory vs Mongo)."""
    return get_db_state().store
