from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable
from typing import Any, TypeVar

from beanie import PydanticObjectId

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
)

T = TypeVar("T")


def _record_id(item: Any) -> str | None:
    value = getattr(item, "id", None)
    return str(value) if value is not None else None


class InMemoryStore:
    """Async repository used for local development and deterministic tests."""

    def __init__(self) -> None:
        self.projects: dict[str, ProjectDocument] = {}
        self.boundaries: list[BoundaryDocument] = []
        self.identity_map: list[IdentityMapDocument] = []
        self.repo_activity: list[RepoActivityDocument] = []
        self.snapshots: list[WeeklySnapshotDocument] = []
        self.warnings: list[WarningDocument] = []
        self.feedback: list[FeedbackDocument] = []
        self.audit_log: list[AuditLogDocument] = []

    def clear(self) -> None:
        self.__init__()

    async def add(self, collection: str, item: T) -> T:
        target = getattr(self, collection)
        if isinstance(target, dict):
            key = getattr(item, "project_id", None)
            if key is None:
                raise ValueError(f"{collection} requires a project_id")
            target[str(key)] = item
        else:
            target.append(item)
        return item

    async def insert(self, item: T) -> T:
        """Beanie-shaped insert helper used by foundation fixtures."""

        if getattr(item, "id", None) is None and hasattr(item, "id"):
            item.id = PydanticObjectId()
        collection = getattr(getattr(item, "Settings", None), "name", "")
        collection = {"weekly_snapshots": "snapshots"}.get(collection, collection)
        return await self.add(collection, item)

    async def insert_many(self, items: Iterable[T]) -> list[T]:
        inserted: list[T] = []
        for item in items:
            inserted.append(await self.insert(item))
        return inserted

    async def find_one(self, model: type[T], **filters: Any) -> T | None:
        collection = {"weekly_snapshots": "snapshots"}.get(model.Settings.name, model.Settings.name)
        rows = await self.list(collection)
        return next(
            (
                row
                for row in rows
                if all(getattr(row, field, None) == expected for field, expected in filters.items())
            ),
            None,
        )

    async def find_many(self, model: type[T], **filters: Any) -> list[T]:
        collection = {"weekly_snapshots": "snapshots"}.get(model.Settings.name, model.Settings.name)
        rows = await self.list(collection)
        return [
            row
            for row in rows
            if all(getattr(row, field, None) == expected for field, expected in filters.items())
        ]

    async def replace(self, item: T) -> T:
        if isinstance(item, WeeklySnapshotDocument):
            raise ImmutableSnapshotError("weekly snapshots are immutable")
        collection = {"weekly_snapshots": "snapshots"}.get(item.Settings.name, item.Settings.name)
        target = getattr(self, collection)
        item_id = _record_id(item)
        for index, existing in enumerate(target):
            if _record_id(existing) == item_id:
                target[index] = item
                return item
        raise KeyError(item_id)

    async def list(self, collection: str) -> list[Any]:
        target = getattr(self, collection)
        return list(target.values()) if isinstance(target, dict) else list(target)

    async def get_project(self, project_id: str) -> ProjectDocument | None:
        return self.projects.get(project_id)

    async def boundary_at(self, project_id: str, at: Any = None) -> BoundaryDocument | None:
        rows = [row for row in self.boundaries if row.project_id == project_id]
        if at is not None:
            rows = [row for row in rows if row.is_effective_at(at)]
        return max(rows, key=lambda row: row.effective_from, default=None)

    async def latest_snapshot(self, project_id: str) -> WeeklySnapshotDocument | None:
        rows = [row for row in self.snapshots if row.project_id == project_id]
        return max(rows, key=lambda row: (row.week_start, row.generated_at), default=None)

    async def snapshot_by_id(self, snapshot_id: str) -> WeeklySnapshotDocument | None:
        return next((row for row in self.snapshots if _record_id(row) == snapshot_id), None)

    async def warning_by_id(self, warning_id: str) -> WarningDocument | None:
        return next((row for row in self.warnings if _record_id(row) == warning_id), None)

    async def warnings_for_snapshot(self, snapshot_id: str) -> list[WarningDocument]:
        return [row for row in self.warnings if str(row.snapshot_id) == snapshot_id]


class BeanieStore:
    """Repository-shaped facade over initialized Beanie collections."""

    _models = {
        "projects": ProjectDocument,
        "boundaries": BoundaryDocument,
        "identity_map": IdentityMapDocument,
        "repo_activity": RepoActivityDocument,
        "snapshots": WeeklySnapshotDocument,
        "warnings": WarningDocument,
        "feedback": FeedbackDocument,
        "audit_log": AuditLogDocument,
    }

    def _model(self, collection: str) -> type[Any]:
        try:
            return self._models[collection]
        except KeyError as exc:
            raise ValueError(f"unsupported collection {collection!r}") from exc

    def __getitem__(self, collection: str) -> Any:
        """Expose raw staging collections to the pull-only adapters."""

        state = get_db_state()
        if state.database is None:
            raise KeyError(collection)
        return state.database[collection]

    async def add(self, collection: str, item: T) -> T:
        return await item.insert()  # type: ignore[attr-defined,no-any-return]

    async def insert(self, item: T) -> T:
        return await item.insert()  # type: ignore[attr-defined,no-any-return]

    async def replace(self, item: T) -> T:
        if isinstance(item, WeeklySnapshotDocument):
            raise ImmutableSnapshotError("weekly snapshots are immutable")
        return await item.replace()  # type: ignore[attr-defined,no-any-return]

    async def list(self, collection: str) -> list[Any]:
        return await self._model(collection).find_all().to_list()

    async def get_project(self, project_id: str) -> ProjectDocument | None:
        rows = await self.list("projects")
        return next((row for row in rows if row.project_id == project_id), None)

    async def boundary_at(self, project_id: str, at: Any = None) -> BoundaryDocument | None:
        rows = [row for row in await self.list("boundaries") if row.project_id == project_id]
        if at is not None:
            rows = [row for row in rows if row.is_effective_at(at)]
        return max(rows, key=lambda row: row.effective_from, default=None)

    async def latest_snapshot(self, project_id: str) -> WeeklySnapshotDocument | None:
        rows = [row for row in await self.list("snapshots") if row.project_id == project_id]
        return max(rows, key=lambda row: (row.week_start, row.generated_at), default=None)

    async def snapshot_by_id(self, snapshot_id: str) -> WeeklySnapshotDocument | None:
        rows = await self.list("snapshots")
        return next((row for row in rows if _record_id(row) == snapshot_id), None)

    async def warning_by_id(self, warning_id: str) -> WarningDocument | None:
        rows = await self.list("warnings")
        return next((row for row in rows if _record_id(row) == warning_id), None)

    async def warnings_for_snapshot(self, snapshot_id: str) -> list[WarningDocument]:
        return [row for row in await self.list("warnings") if str(row.snapshot_id) == snapshot_id]


store = InMemoryStore()
mongo_client: Any = None
_mongo_client: Any = None
_database_state: "DatabaseState | None" = None


@dataclass(slots=True)
class DatabaseState:
    settings: Settings
    client: Any
    database: Any
    repository: InMemoryStore | None

    @property
    def in_memory(self) -> bool:
        return self.repository is not None


async def init_db(settings: Settings | None = None) -> InMemoryStore:
    """Initialize Beanie when Mongo is configured; otherwise use memory."""
    global _mongo_client, _database_state
    resolved = settings or get_settings()
    if not resolved.mongo_uri:
        _database_state = DatabaseState(
            settings=resolved,
            client=None,
            database=None,
            repository=store,
        )
        return store
    from beanie import init_beanie
    from motor.motor_asyncio import AsyncIOMotorClient

    _mongo_client = AsyncIOMotorClient(
        resolved.mongo_uri,
        serverSelectionTimeoutMS=resolved.mongo_server_selection_timeout_ms,
    )
    await _mongo_client.admin.command("ping")
    await init_beanie(
        database=_mongo_client[resolved.mongo_database],
        document_models=[
            ProjectDocument,
            BoundaryDocument,
            IdentityMapDocument,
            RepoActivityDocument,
            WeeklySnapshotDocument,
            WarningDocument,
            FeedbackDocument,
            AuditLogDocument,
        ],
    )
    _database_state = DatabaseState(
        settings=resolved,
        client=_mongo_client,
        database=_mongo_client[resolved.mongo_database],
        repository=None,
    )
    return store


async def close_db() -> None:
    global _mongo_client, _database_state
    if _mongo_client is not None:
        _mongo_client.close()
        _mongo_client = None
    _database_state = None


def get_db_state() -> DatabaseState:
    """Return initialized state, lazily selecting safe in-memory mode."""

    global _database_state
    if _database_state is None:
        settings = get_settings()
        if settings.mongo_uri:
            raise RuntimeError("init_db() must be awaited before using configured MongoDB")
        _database_state = DatabaseState(
            settings=settings,
            client=None,
            database=None,
            repository=store,
        )
    return _database_state


def get_repository() -> InMemoryStore:
    repository = get_db_state().repository
    if repository is None:
        raise RuntimeError("the repository helper is available only in in-memory mode")
    return repository


def get_active_repository() -> InMemoryStore | BeanieStore:
    """Return the initialized repository for either local or Mongo mode."""

    state = get_db_state()
    if state.repository is not None:
        return state.repository
    return BeanieStore()
