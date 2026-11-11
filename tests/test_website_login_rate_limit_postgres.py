"""Real PostgreSQL concurrency tests for the shared Supabase RPC migration."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")
DSN = os.environ.get("WEBSITE_LOGIN_LIMITER_TEST_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="PostgreSQL limiter test DSN is not configured")
MIGRATION = Path(__file__).parents[1] / "supabase" / "migrations" / "20261103000000_website_login_shared_rate_limit.sql"


def _connection():
    return psycopg.connect(DSN)


def _install_migration():
    with _connection() as connection:
        connection.execute(
            """
            DO $roles$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                    CREATE ROLE anon NOLOGIN;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                    CREATE ROLE authenticated NOLOGIN;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
                    CREATE ROLE service_role NOLOGIN;
                END IF;
            END
            $roles$;
            """,
            prepare=False,
        )
        connection.execute(MIGRATION.read_text(encoding="utf-8"), prepare=False)


def _consume(client_id):
    with _connection() as connection:
        connection.execute("SELECT set_config('application_name', %s, false)", (client_id,))
        connection.execute("SET ROLE service_role")
        return connection.execute(
            "SELECT allowed, retry_after_seconds FROM public.consume_website_login_attempt()"
        ).fetchone()


def test_concurrent_distinct_clients_share_exactly_five_atomic_attempts():
    _install_migration()
    with _connection() as connection:
        connection.execute("DELETE FROM public.website_login_attempts")

    clients = [f"edge-client-{number}" for number in range(64)]
    with ThreadPoolExecutor(max_workers=24) as pool:
        outcomes = list(pool.map(_consume, clients))

    assert sum(allowed for allowed, _ in outcomes) == 5
    assert all(0 <= retry <= 60 for _, retry in outcomes)
    assert all(retry == 0 for allowed, retry in outcomes if allowed)
    assert all(retry > 0 for allowed, retry in outcomes if not allowed)
    with _connection() as connection:
        assert connection.execute("SELECT count(*) FROM public.website_login_attempts").fetchone()[0] == 5


def test_expired_attempts_are_removed_before_the_next_window():
    with _connection() as connection:
        connection.execute("DELETE FROM public.website_login_attempts")
    assert all(allowed for allowed, _ in [_consume(f"burst-{n}") for n in range(5)])
    assert _consume("blocked")[0] is False
    with _connection() as connection:
        connection.execute(
            "UPDATE public.website_login_attempts SET attempted_at = clock_timestamp() - interval '61 seconds'"
        )
    allowed, retry = _consume("after-expiry")
    assert allowed is True
    assert retry == 0
    with _connection() as connection:
        assert connection.execute("SELECT count(*) FROM public.website_login_attempts").fetchone()[0] == 1


def test_only_the_service_role_can_execute_rpc_and_tables_are_not_exposed():
    with _connection() as connection:
        assert connection.execute(
            "SELECT has_function_privilege('anon', 'public.consume_website_login_attempt()', 'EXECUTE')"
        ).fetchone()[0] is False
        assert connection.execute(
            "SELECT has_function_privilege('authenticated', 'public.consume_website_login_attempt()', 'EXECUTE')"
        ).fetchone()[0] is False
        assert connection.execute(
            "SELECT has_function_privilege('service_role', 'public.consume_website_login_attempt()', 'EXECUTE')"
        ).fetchone()[0] is True
        assert connection.execute(
            "SELECT has_table_privilege('service_role', 'public.website_login_attempts', 'SELECT')"
        ).fetchone()[0] is False
        assert connection.execute(
            "SELECT relrowsecurity FROM pg_class WHERE oid = 'public.website_login_attempts'::regclass"
        ).fetchone()[0] is True
