"""Parity suite: PostgresStore must behave exactly as SqliteStore does.

Every test here runs against *both* backends from one body, so a divergence
shows up as a failure rather than as a difference nobody looked for. The
Postgres half is skipped unless ``PHI_TEST_POSTGRES_DSN`` names a reachable
database, which keeps the suite runnable with no services attached:

    docker run -d --rm --name phi-pg-test -e POSTGRES_PASSWORD=testpw \\
        -e POSTGRES_DB=phitest -p 55432:5432 postgres:15-alpine
    PHI_TEST_POSTGRES_DSN=postgresql://postgres:testpw@127.0.0.1:55432/phitest \\
        python -m pytest tests/test_postgres_store.py

The DSN's schema is dropped and recreated per test, so runs do not leak into
each other.
"""

from __future__ import annotations

import os
from datetime import date

import pytest
import pytest_asyncio

from backend.db import SqliteStore, _apply_schema
from backend.db_postgres import looks_like_pooled_dsn
from backend.errors import ImmutableSnapshotError
from backend.models import ProjectDocument

POSTGRES_DSN = os.environ.get("PHI_TEST_POSTGRES_DSN")
requires_postgres = pytest.mark.skipif(
    not POSTGRES_DSN, reason="set PHI_TEST_POSTGRES_DSN to run the Postgres half"
)


@pytest_asyncio.fixture
async def sqlite_store():
    import aiosqlite

    db = await aiosqlite.connect(":memory:")
    await _apply_schema(db)
    try:
        yield SqliteStore(db)
    finally:
        await db.close()


@pytest_asyncio.fixture
async def postgres_store():
    if not POSTGRES_DSN:
        pytest.skip("no PHI_TEST_POSTGRES_DSN")
    import asyncpg

    from backend.db_postgres import POSTGRES_SCHEMA_SQL, PostgresStore

    pool = await asyncpg.create_pool(POSTGRES_DSN, min_size=1, max_size=3)
    async with pool.acquire() as conn:
        # A clean schema per test; the immutability trigger makes DELETE
        # unusable for teardown and TRUNCATE would leave the DDL behind.
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        await conn.execute(POSTGRES_SCHEMA_SQL)
    try:
        yield PostgresStore(pool)
    finally:
        await pool.close()


@pytest.fixture
def both(request):
    """Resolve the backend named by the parametrised fixture."""
    return request.getfixturevalue(request.param)


BACKENDS = [
    pytest.param("sqlite_store", id="sqlite"),
    pytest.param("postgres_store", id="postgres", marks=requires_postgres),
]


@pytest.mark.parametrize("both", BACKENDS, indirect=True)
@pytest.mark.asyncio
async def test_add_and_read_back_a_project(both, make_project) -> None:
    await both.add("projects", make_project())
    found = await both.get_project("member-portal")
    assert found is not None
    assert found.display_name == "Member Portal"
    assert isinstance(found, ProjectDocument)


@pytest.mark.parametrize("both", BACKENDS, indirect=True)
@pytest.mark.asyncio
async def test_has_any_and_list(both, make_project) -> None:
    assert await both.has_any("projects") is False
    assert await both.list("projects") == []
    await both.add("projects", make_project())
    assert await both.has_any("projects") is True
    assert len(await both.list("projects")) == 1


@pytest.mark.parametrize("both", BACKENDS, indirect=True)
@pytest.mark.asyncio
async def test_add_is_an_upsert_on_id(both, make_project) -> None:
    project = make_project()
    await both.add("projects", project)
    project.display_name = "Renamed"
    await both.add("projects", project)

    rows = await both.list("projects")
    assert len(rows) == 1
    assert rows[0].display_name == "Renamed"


@pytest.mark.parametrize("both", BACKENDS, indirect=True)
@pytest.mark.asyncio
async def test_replace_updates_in_place(both, make_project) -> None:
    project = make_project()
    await both.add("projects", project)
    project.display_name = "Replaced"
    await both.replace(project)

    found = await both.get_project("member-portal")
    assert found is not None and found.display_name == "Replaced"


@pytest.mark.parametrize("both", BACKENDS, indirect=True)
@pytest.mark.asyncio
async def test_boundary_at_picks_the_effective_version(both, make_boundary) -> None:
    await both.add("boundaries", make_boundary(effective_from=date(2026, 1, 1)))
    await both.add("boundaries", make_boundary(effective_from=date(2026, 6, 1)))

    latest = await both.boundary_at("member-portal", at=date(2026, 7, 1))
    earlier = await both.boundary_at("member-portal", at=date(2026, 3, 1))

    assert latest is not None and latest.effective_from == date(2026, 6, 1)
    assert earlier is not None and earlier.effective_from == date(2026, 1, 1)


@pytest.mark.parametrize("both", BACKENDS, indirect=True)
@pytest.mark.asyncio
async def test_latest_snapshot_orders_by_week(both, make_snapshot) -> None:
    await both.add("snapshots", make_snapshot(week_start=date(2026, 3, 2)))
    await both.add("snapshots", make_snapshot(week_start=date(2026, 3, 9)))

    latest = await both.latest_snapshot("member-portal")
    assert latest is not None and latest.week_start == date(2026, 3, 9)


@pytest.mark.parametrize("both", BACKENDS, indirect=True)
@pytest.mark.asyncio
async def test_snapshots_reject_replace(both, make_snapshot) -> None:
    snapshot = make_snapshot()
    await both.add("snapshots", snapshot)
    with pytest.raises(ImmutableSnapshotError):
        await both.replace(snapshot)


@pytest.mark.parametrize("both", BACKENDS, indirect=True)
@pytest.mark.asyncio
async def test_warnings_are_found_by_snapshot(both, make_snapshot, make_warning) -> None:
    snapshot = make_snapshot()
    await both.add("snapshots", snapshot)
    await both.add("warnings", make_warning(snapshot_id=str(snapshot.id)))

    found = await both.warnings_for_snapshot(str(snapshot.id))
    assert len(found) == 1
    assert found[0].rule_id == "open_pr_aging"
    # Nested evidence has to survive the JSON round trip intact -- it is the
    # deepest structure either backend stores.
    assert found[0].evidence[0].source_refs[0].source_collection == "repo_activity"


@pytest.mark.parametrize("both", BACKENDS, indirect=True)
@pytest.mark.asyncio
async def test_find_one_and_find_many(both, make_project) -> None:
    from backend.models import ProjectDocument as PD

    await both.add("projects", make_project("alpha", display_name="Alpha"))
    await both.add("projects", make_project("beta", display_name="Beta"))

    one = await both.find_one(PD, project_id="beta")
    many = await both.find_many(PD, lifecycle_state=make_project().lifecycle_state)

    assert one is not None and one.display_name == "Beta"
    assert len(many) == 2


@pytest.mark.parametrize("both", BACKENDS, indirect=True)
@pytest.mark.asyncio
async def test_clear_empties_every_collection_including_snapshots(
    both, make_project, make_snapshot
) -> None:
    await both.add("projects", make_project())
    await both.add("snapshots", make_snapshot())

    await both.clear()

    assert await both.list("projects") == []
    # Snapshots are immutable, so clear() has to route around the guard --
    # SQLite drops and recreates the table, Postgres uses TRUNCATE.
    assert await both.list("snapshots") == []


@pytest.mark.parametrize("both", BACKENDS, indirect=True)
@pytest.mark.asyncio
async def test_snapshots_still_reject_a_write_after_clear(both, make_snapshot) -> None:
    """clear() must leave the immutability guard installed, not just the table."""
    await both.clear()
    snapshot = make_snapshot()
    await both.add("snapshots", snapshot)
    with pytest.raises(ImmutableSnapshotError):
        await both.replace(snapshot)


# ---------------------------------------------------------------------------
# DSN handling — no database needed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dsn,pooled",
    [
        ("postgresql://u:p@aws-0-us-east-1.pooler.supabase.com:6543/postgres", True),
        ("postgresql://u:p@aws-0-us-east-1.pooler.supabase.com:5432/postgres", True),
        ("postgresql://u:p@db.abcdefgh.supabase.co:5432/postgres", False),
        ("postgresql://u:p@localhost:5432/phi", False),
        ("postgresql://u:p@somewhere:6543/phi", True),
    ],
)
def test_pooled_dsn_detection(dsn: str, pooled: bool) -> None:
    """Prepared statements must be off behind a transaction pooler.

    Getting this wrong fails intermittently under concurrency rather than at
    startup, so it is worth pinning by example.
    """
    assert looks_like_pooled_dsn(dsn) is pooled
