"""Fresh-process baseline/optimized REST fixture benchmark (no external network).

Run with repository and tests on PYTHONPATH. Every worker starts a fresh Python
process, imports the real API, then sends a cold workload and two warm repeats.
Only HTTPTransport network I/O is replaced; real client/TLS construction runs.
Synthetic history and archive fixtures are never production market evidence.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter

BASELINE = '1b72b59b06d94402207b4723251f712c01d8d3bb'


def worker(mode, symbols):
    start = perf_counter()
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime
    import hashlib
    import importlib
    import logging
    import os
    from threading import Barrier
    from unittest.mock import patch
    import httpx
    import pandas as pd
    from fastapi.testclient import TestClient
    from modules import supabase_archive as archive
    from alphaos_api.research2 import ArchiveResearchService
    api = importlib.import_module('alphaos_api.app')
    interface = importlib.import_module('alphaos_api.research2')
    app_import_ms = round((perf_counter()-start)*1000, 2)
    from tests.test_archive_read_path import ReadOnlyClient, AS_OF
    from tests.test_website_mcp_parity import prepare_storage
    assert 'supabase' not in sys.modules, 'Benchmark accidentally preloaded SDK'
    if mode == 'before':
        scope = {}
        source = subprocess.check_output(['git', 'show', f'{BASELINE}:modules/supabase_archive.py'], text=True)
        exec(compile(source, 'baseline/supabase_archive.py', 'exec'), scope)
        interface.archive_client = scope['research_archive_client']
    storages = {symbol: ReadOnlyClient() for symbol in symbols}
    for symbol, storage in storages.items():
        prepare_storage(storage, symbol)
    days = pd.bdate_range(end='2030-01-01', periods=1260)
    bars = pd.DataFrame(dict(date=days, symbol='QQQ', open=range(100,1360),
        close=range(100,1360), high=range(101,1361), low=range(99,1359)))
    os.environ.update(SUPABASE_URL='https://fixture.invalid', SUPABASE_SERVICE_ROLE_KEY='fixture-only',
        ALPHAOS_API_TOKEN='offline-only', ALPHAOS_ARCHIVE_MAX_AGE_SECONDS='300')
    api.app.state.archive_research = ArchiveResearchService(
        history_loader=lambda symbol: bars.assign(symbol=symbol),
        clock=lambda: datetime.fromisoformat(AS_OF))
    calls = []
    def handle(transport, request):
        calls.append(request)
        if request.url.path == '/rest/v1/option_snapshots':
            symbol = request.url.params['symbol'].removeprefix('eq.')
            return httpx.Response(200, json=[storages[symbol].row])
        for storage in storages.values():
            if request.url.path == '/storage/v1/object/market-archive/'+storage.row['archive_path']:
                return httpx.Response(200, content=storage.raw)
        raise AssertionError('Unexpected network operation')
    traces = []
    class Capture(logging.Handler):
        def emit(self, record):
            traces.append(json.loads(record.getMessage()))
    logger = logging.getLogger('alphaos_api.research.timing')
    logger.addHandler(Capture())
    logger.setLevel(logging.WARNING)
    logger.propagate = False
    result = dict(mode=mode, symbols=symbols, app_import_ms=app_import_ms, requests=[])
    with patch.object(httpx.HTTPTransport, 'handle_request', handle), TestClient(api.app) as client:
        for iteration in range(3):
            barrier = Barrier(len(symbols))
            def invoke(symbol):
                barrier.wait(timeout=10)
                started = perf_counter()
                response = client.post('/v1/research/market', json=dict(symbol=symbol),
                    headers={'Authorization':'Bearer offline-only'})
                elapsed = round((perf_counter()-started)*1000, 2)
                assert response.status_code == 200
                request_id = response.headers['X-AlphaOS-Request-ID']
                stages = {r['stage']:r['duration_ms'] for r in traces
                    if r['request_id'] == request_id and r.get('phase') == 'end' and 'duration_ms' in r}
                digest = hashlib.sha256(json.dumps(response.json(), sort_keys=True).encode()).hexdigest()
                return dict(symbol=symbol, phase='cold' if iteration == 0 else 'warm',
                    iteration=iteration, elapsed_ms=elapsed, stages_ms=stages, response_sha256=digest)
            with ThreadPoolExecutor(len(symbols)) as pool:
                result['requests'].extend(pool.map(invoke, symbols))
    assert len(calls) == 6*len(symbols), 'Every request must query and download'
    if mode == 'after':
        assert 'supabase' not in sys.modules, 'Optimized research loaded unused SDK'
    print(json.dumps(result), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', choices=['before', 'after'])
    parser.add_argument('--symbols', default='SPY,QQQ')
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    if args.worker:
        worker(args.worker, args.symbols.split(','))
        return
    expected = {}
    for mode in ('before', 'after'):
        for symbols in ('SPY', 'QQQ', 'SPY,QQQ'):
            for sample in range(args.repeats):
                output = subprocess.check_output([sys.executable, str(Path(__file__).resolve()),
                    '--worker', mode, '--symbols', symbols], text=True)
                result = json.loads(output)
                result['sample'] = sample
                for row in result['requests']:
                    symbol = row['symbol']
                    expected.setdefault(symbol, row['response_sha256'])
                    assert row['response_sha256'] == expected[symbol], 'Full REST response changed'
                print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
