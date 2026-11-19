"""Database-side append-only and optimistic concurrency checks on local Postgres."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")
DSN = os.environ.get("MARKET_PLAYBOOK_TEST_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="Local market playbook PostgreSQL DSN is missing")
MIGRATION = Path(__file__).parents[1] / "supabase/migrations/20261119140412_market_playbook_journal.sql"


def rpc(revision=None, updates=None):
    with psycopg.connect(DSN) as connection:
        connection.execute("SET ROLE service_role")
        return connection.execute(
            "select public.market_playbook_journal('SPY', 'Fixture', '2026-11-19', %s, %s)",
            (revision, psycopg.types.json.Jsonb(updates or [])),
        ).fetchone()[0]


def test_market_playbook_migration_access_and_concurrent_append():
    with psycopg.connect(DSN, autocommit=True) as connection:
        for role in ("anon", "authenticated", "service_role"):
            if not connection.execute("select 1 from pg_roles where rolname = %s", (role,)).fetchone():
                connection.execute(psycopg.sql.SQL("CREATE ROLE {} NOLOGIN").format(psycopg.sql.Identifier(role)))
        connection.execute("ALTER ROLE service_role BYPASSRLS")
        connection.execute(MIGRATION.read_text(encoding="utf-8"), prepare=False)

        for role in ("anon", "authenticated"):
            assert not connection.execute(
                "select has_function_privilege(%s, 'public.market_playbook_journal(text,text,date,text,jsonb)', 'EXECUTE')",
                (role,),
            ).fetchone()[0]
        for table in ("thesis", "event"):
            for privilege in ("UPDATE", "DELETE", "TRUNCATE"):
                assert not connection.execute(
                    "select has_table_privilege('service_role', %s, %s)",
                    (f"market_playbook_private.{table}", privilege),
                ).fetchone()[0]

    seed = rpc()
    original = {"id": "fixture", "trigger": 505}
    create = {"id": "fixture", "after": 0, "thesis": original, "events": []}
    assert rpc(seed["revision"], [create])["applied"] is True
    before = rpc()
    append = {"id": "fixture", "after": 0, "events": [{"state": "CONFIRMED"}]}
    with ThreadPoolExecutor(max_workers=4) as pool:
        attempts = list(pool.map(lambda _: rpc(before["revision"], [append]), range(8)))
    assert sum(result["applied"] for result in attempts) == 1
    assert rpc()["records"] == [{"thesis": original, "events": [{"state": "CONFIRMED"}]}]
