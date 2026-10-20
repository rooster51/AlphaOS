"""Operation-count and exact-result regressions, without production timing claims."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal
import pytest

from modules.market_state import _wilder
from modules import research_calendar as calendar
from modules import supabase_archive as archive
from modules import public_provider as public


@pytest.mark.parametrize('length', [0, 14, 15, 1260])
def test_wilder_matches_original_scalar_recurrence_exactly(length):
    values = pd.Series(np.random.default_rng(52).normal(size=length), index=range(7, 7+length))
    expected = pd.Series(np.nan, index=values.index, dtype=float)
    if length > 14:
        expected.iloc[14] = values.iloc[1:15].mean()
        for i in range(15, length):
            expected.iloc[i] = (expected.iloc[i-1]*13+values.iloc[i])/14
    pd.testing.assert_series_equal(_wilder(values), expected, check_exact=True)


def test_calendar_concurrent_cold_miss_is_single_and_copies_are_isolated(monkeypatch):
    calendar._schedule.cache_clear()
    original = mcal.get_calendar
    factory = Mock(side_effect=original)
    monkeypatch.setattr(calendar.mcal, 'get_calendar', factory)
    barrier = Barrier(2)
    def read(_):
        barrier.wait(timeout=5)
        return calendar.nyse_schedule('2026-11-27', '2026-11-27')
    with ThreadPoolExecutor(2) as pool:
        a, b = list(pool.map(read, range(2)))
    assert factory.call_count == 1
    assert a.iloc[0].market_close.hour == 18  # NYSE Thanksgiving early close
    a.iloc[0, 0] = pd.NaT
    assert not b.isna().any().any()
    assert calendar.nyse_schedule('2026-12-25', '2026-12-25').empty
    calendar._schedule.cache_clear()


def test_archive_client_reuses_identity_not_queries_and_rechecks_credentials(monkeypatch):
    monkeypatch.setattr(archive, '_research_client', None)
    monkeypatch.setattr(archive, '_research_credentials', None)
    monkeypatch.setenv('SUPABASE_URL', 'https://fixture.invalid')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'fixture-key')
    factory = Mock(side_effect=lambda: SimpleNamespace(postgrest=object(), storage=object()))
    monkeypatch.setattr(archive, 'archive_client', factory)
    with ThreadPoolExecutor(2) as pool:
        clients = list(pool.map(lambda _: archive.research_archive_client(), range(8)))
    assert factory.call_count == 1 and all(c is clients[0] for c in clients)
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'rotated-fixture-key')
    assert archive.research_archive_client() is not clients[0]
    assert factory.call_count == 2
    factory.side_effect = archive.ArchiveUnavailable('unavailable')
    monkeypatch.delenv('SUPABASE_SERVICE_ROLE_KEY')
    with pytest.raises(archive.ArchiveUnavailable):
        archive.research_archive_client()


def test_public_context_serializes_cold_cache_population_only(monkeypatch):
    from functools import lru_cache
    from time import sleep
    factory = Mock(side_effect=lambda *args: (sleep(.02), object())[1])
    monkeypatch.setattr(public, 'authenticated_context', lru_cache(maxsize=2)(factory))
    monkeypatch.setattr(public, 'configuration', lambda: ('fixture', None))
    with ThreadPoolExecutor(2) as pool:
        clients = list(pool.map(lambda _: public._public_context(), range(8)))
    assert factory.call_count == 1 and all(c is clients[0] for c in clients)


def test_reused_real_supabase_client_keeps_concurrent_queries_and_verification(monkeypatch):
    import httpx
    from supabase import create_client
    from supabase._sync.client import ClientOptions
    from tests.test_archive_read_path import ReadOnlyClient, AS_OF
    from tests.test_website_mcp_parity import prepare_storage
    storages = {symbol: ReadOnlyClient() for symbol in ('SPY', 'QQQ')}
    for symbol, storage in storages.items():
        prepare_storage(storage, symbol)
    queries = []
    def respond(request):
        if request.url.path == '/rest/v1/option_snapshots':
            symbol = request.url.params['symbol'].removeprefix('eq.')
            queries.append(symbol)
            return httpx.Response(200, json=[storages[symbol].row])
        symbol = 'SPY' if 'symbol=SPY' in str(request.url) else 'QQQ'
        return httpx.Response(200, content=storages[symbol].raw)
    with httpx.Client(transport=httpx.MockTransport(respond)) as transport:
        client = create_client('https://fixture.invalid', 'fixture-key',
            options=ClientOptions(httpx_client=transport))
        def read(symbol):
            return archive.read_latest_option_snapshot(client, symbol, AS_OF, max_age_seconds=300)
        with ThreadPoolExecutor(2) as pool:
            records = list(pool.map(read, ('SPY', 'QQQ', 'SPY', 'QQQ')))
        assert [r['payload']['symbol'] for r in records] == ['SPY', 'QQQ', 'SPY', 'QQQ']
        assert sorted(queries) == ['QQQ', 'QQQ', 'SPY', 'SPY']
        storages['QQQ'].raw += b'tampered'
        with pytest.raises(archive.ArchiveUnavailable):
            read('QQQ')
