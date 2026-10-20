"""Offline before/after benchmark; synthetic fixtures, never market evidence.

Run from repo root with repository and tests on PYTHONPATH. Uses the same
interpreter/dependencies for both versions. No credentials or network required.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import importlib
import logging
import os
import subprocess
from datetime import datetime
from time import perf_counter

import pandas as pd
import pandas_market_calendars as mcal
from modules import market_state, market_session_gate, structure_economics
from fastapi.testclient import TestClient
from alphaos_api.research2 import ArchiveResearchService
from modules.supabase_archive import read_latest_option_snapshot
from tests.test_archive_read_path import ReadOnlyClient, AS_OF
from tests.test_website_mcp_parity import prepare_storage


def main():
    original = {}
    for name in ('market_state', 'market_session_gate', 'structure_economics'):
        scope = {}
        source = subprocess.check_output(['git', 'show', f'be430e860d4b220a63b5f03225875925039de792:modules/{name}.py'], text=True)
        exec(compile(source, f'baseline/{name}.py', 'exec'), scope)
        original[name] = scope
    saved = (market_state._wilder, market_session_gate.nyse_schedule, structure_economics.nyse_schedule)
    storages = {symbol: ReadOnlyClient() for symbol in ('SPY', 'QQQ')}
    for symbol, storage in storages.items():
        prepare_storage(storage, symbol)
    days = pd.bdate_range(end='2030-01-01', periods=1260)
    bars = pd.DataFrame(dict(date=days, symbol='QQQ', open=range(100,1360),
        close=range(100,1360), high=range(101,1361), low=range(99,1359)))
    expected = {}
    api = importlib.import_module('alphaos_api.app')
    os.environ['ALPHAOS_API_TOKEN'] = 'offline-benchmark-only'
    api.app.state.archive_research = ArchiveResearchService(
        read_snapshot=lambda symbol, as_of, **kwargs: read_latest_option_snapshot(
            storages[symbol], symbol, as_of, max_age_seconds=300, **kwargs),
        history_loader=lambda symbol: bars.assign(symbol=symbol),
        clock=lambda: datetime.fromisoformat(AS_OF))
    logging.disable(logging.CRITICAL)
    client = TestClient(api.app)
    def run(symbol):
        start = perf_counter()
        response = client.post('/v1/research/market', json=dict(symbol=symbol, research_mode=research_mode),
            headers={'Authorization': 'Bearer offline-benchmark-only'})
        elapsed = round((perf_counter()-start)*1000, 2)
        assert response.status_code == 200
        result = response.json()
        key = (symbol, research_mode)
        if key in expected:
            assert result == expected[key], 'Research output changed'
        else:
            expected[key] = result
        return elapsed
    try:
        for mode in ('before', 'after'):
            if mode == 'before':
                market_state._wilder = original['market_state']['_wilder']
                def uncached(start, end):
                    return mcal.get_calendar('NYSE').schedule(start_date=start, end_date=end)
                market_session_gate.nyse_schedule = structure_economics.nyse_schedule = uncached
            else:
                market_state._wilder, market_session_gate.nyse_schedule, structure_economics.nyse_schedule = saved
            for research_mode in ('current', 'historical'):
                for iteration in range(3):
                    independent = {symbol: run(symbol) for symbol in ('SPY', 'QQQ')}
                    with ThreadPoolExecutor(2) as pool:
                        concurrent = dict(zip(('SPY', 'QQQ'), pool.map(run, ('SPY', 'QQQ'))))
                    print(json.dumps(dict(mode=mode, research_mode=research_mode, iteration=iteration,
                        independent_ms=independent, concurrent_ms=concurrent)), flush=True)
    finally:
        market_state._wilder, market_session_gate.nyse_schedule, structure_economics.nyse_schedule = saved


if __name__ == '__main__':
    main()
