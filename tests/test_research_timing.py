"""Correlated diagnostics with deterministic archive fixtures; no live latency claims."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import logging
from threading import Barrier, Event

import httpx
import pytest
from fastapi.testclient import TestClient

from modules.research_timing import ResearchTimingMiddleware, stage
from modules.supabase_archive import read_latest_option_snapshot
from tests.test_archive_read_path import ReadOnlyClient
from tests.test_research2_api import boundary, post
from tests.test_website_mcp_parity import prepare_storage
from tests.test_run_market import history


def records(caplog):
    return [json.loads(row.getMessage()) for row in caplog.records
        if row.name == 'alphaos_api.research.timing']


@pytest.fixture(autouse=True)
def capture_timing_logger(monkeypatch, caplog):
    # UI tests can configure/disable process-wide logging. Like the existing
    # OAuth diagnostics tests, enable only the logger this module asserts on.
    logger = logging.getLogger('alphaos_api.research.timing')
    monkeypatch.setattr(logger, 'disabled', False)
    caplog.set_level(logging.WARNING, logger=logger.name)


@pytest.fixture
def timed_boundary(boundary):
    client, storage, service, loader = boundary
    return TestClient(ResearchTimingMiddleware(client.app), base_url='https://alphaos.onrender.com'), storage, service, loader


@pytest.mark.parametrize('symbol', ['SPY','QQQ'])
def test_timings_leave_historical_contract_identical_and_never_log_payload(timed_boundary, boundary, caplog, monkeypatch, symbol):
    client, storage, service, _ = timed_boundary
    import alphaos_api.research2 as interface
    monkeypatch.setattr(interface, 'archive_client', lambda: storage)
    service.read_snapshot = service._read
    prepare_storage(storage, symbol)
    payload = dict(symbol=symbol, research_mode='historical', objective='DO_NOT_LOG_OBJECTIVE')
    expected = post(boundary[0], 'market', payload)
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        actual = client.post('/v1/research/market', json=payload, headers={
            'Authorization':'Bearer owner-test-secret', 'X-AlphaOS-Request-ID':'a'*32})
    assert actual.status_code == 200
    assert actual.json() == expected.json()
    assert actual.headers['X-AlphaOS-Request-ID'] == 'a'*32
    rows = records(caplog)
    assert rows[0]['stage'] == 'request' and rows[0]['phase'] == 'start'
    assert rows[-1]['stage'] == 'request' and rows[-1]['outcome'] == 'complete'
    assert rows[-1]['status'] == 200
    starts = {r['stage'] for r in rows if r['phase'] == 'start'}
    assert starts >= {'research_execution','archive_read','archive_client','archive_metadata_query',
        'archive_metadata_validation','archive_download','archive_checksum','archive_decompression',
        'archive_json_decode','archive_payload_validation','history_load','archive_normalization',
        'session_calendar','history_features','opportunity_classification',
        'candidate_and_economics_pipeline','historical_economics','response_serialization'}
    assert all(r['request_id'] == 'a'*32 and r['elapsed_ms'] >= 0 for r in rows)
    assert all(r.get('duration_ms',0) >= 0 for r in rows)
    assert all(r['symbol'] == symbol and r['research_mode'] == 'historical'
        for r in rows if 'symbol' in r)
    allowed = {'event','request_id','stage','phase','elapsed_ms','inflight_requests',
        'active_executions','duration_ms','outcome','symbol','research_mode','status'}
    assert all(set(r) <= allowed for r in rows)
    assert not any(secret in caplog.text for secret in ('DO_NOT_LOG','owner-test-secret',
        storage.row['archive_path'],storage.row['archive_sha256']))


def test_real_app_timing_middleware_shares_sanitized_id_with_response(boundary, caplog):
    # Exercise the production middleware stack, including its ordering.
    from tests.test_research2_api import api
    response = TestClient(api.app).post('/v1/research/market', json={'symbol':'QQQ'}, headers={
        'Authorization':'Bearer owner-test-secret','X-AlphaOS-Request-ID':'DO_NOT_LOG'})
    assert response.status_code == 200
    assert {r['request_id'] for r in records(caplog)} == {response.headers['X-AlphaOS-Request-ID']}
    assert 'DO_NOT_LOG' not in caplog.text


def test_independent_and_concurrent_historical_requests_keep_contexts_isolated(timed_boundary, caplog):
    client, _, service, _ = timed_boundary
    storages = {symbol:ReadOnlyClient() for symbol in ('SPY','QQQ')}
    for symbol, storage in storages.items():
        prepare_storage(storage, symbol)
    service.read_snapshot = lambda symbol, as_of, **kwargs: read_latest_option_snapshot(
        storages[symbol],symbol,as_of,max_age_seconds=300,**kwargs)
    service.history_loader = lambda symbol: history().assign(symbol=symbol)
    def invoke(symbol):
        return client.post('/v1/research/market',json=dict(symbol=symbol,research_mode='historical'),
            headers={'Authorization':'Bearer owner-test-secret','X-AlphaOS-Request-ID':('a' if symbol=='SPY' else 'b')*32})
    independent = {symbol:invoke(symbol).json() for symbol in storages}
    barrier = Barrier(2)
    def history_with_overlap(symbol):
        barrier.wait(timeout=5)
        return history().assign(symbol=symbol)
    service.history_loader = history_with_overlap
    caplog.clear()
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = dict(zip(storages,pool.map(invoke,storages)))
    assert all(response.status_code == 200 for response in responses.values())
    for symbol, response in responses.items():
        assert response.json() == independent[symbol]
    rows = records(caplog)
    assert any(r['active_executions'] >= 2 for r in rows)
    assert any(r['inflight_requests'] >= 2 for r in rows)
    for row in rows:
        if 'symbol' in row:
            assert row['symbol'] == ('SPY' if row['request_id'] == 'a'*32 else 'QQQ')


def test_archive_timeout_is_attributed_and_does_not_bypass_verification(timed_boundary, caplog):
    client, storage, service, loader = timed_boundary
    def timeout(_):
        raise TimeoutError('DO_NOT_LOG_STORAGE_URL')
    storage.download = timeout
    response = post(client,'market',dict(symbol='QQQ',research_mode='historical'))
    assert response.status_code == 503
    assert response.json()['error']['code'] == 'archive_unavailable'
    rows = records(caplog)
    assert any(r['stage']=='archive_download' and r.get('outcome')=='error' for r in rows)
    assert not any(r['stage']=='archive_checksum' for r in rows)
    loader.assert_not_called()
    assert 'DO_NOT_LOG' not in caplog.text


def test_auth_failure_logs_arrival_without_starting_research(timed_boundary, caplog):
    response = timed_boundary[0].post('/v1/research/market',json={'symbol':'SPY'})
    assert response.status_code == 401
    assert [r['stage'] for r in records(caplog) if r['phase']=='start'] == ['request']


def test_observed_disconnect_signals_worker_without_consuming_extra_messages(caplog):
    async def exercise():
        messages = iter([{'type':'http.request','body':b'private'}, {'type':'http.disconnect'}])
        async def receive(): return next(messages)
        sent = []
        async def send(message): sent.append(message)
        async def app(scope, receive, send):
            assert (await receive())['body'] == b'private'
            with stage('archive_download'):
                assert (await receive())['type'] == 'http.disconnect'
            await send({'type':'http.response.start','status':200,'headers':[]})
            await send({'type':'http.response.body','body':b'private'})
        with pytest.raises(asyncio.CancelledError):
            await ResearchTimingMiddleware(app)(dict(type='http',method='POST',path='/v1/research/market',headers=[]),receive,send)
        assert not sent
    asyncio.run(exercise())
    rows = records(caplog)
    assert any(r['stage']=='client_disconnect' and r['phase']=='observed' for r in rows)
    assert rows[-1]['outcome'] == 'cancelled'
    assert any(r['stage']=='archive_download' and r.get('outcome')=='cancelled' for r in rows)
    assert 'private' not in caplog.text


def test_cancelled_asgi_request_stops_after_blocking_io_returns(boundary, caplog):
    entered, release, finished = Event(), Event(), Event()
    service = boundary[2]
    original_read = service.read_snapshot
    def blocked_read(*args, **kwargs):
        entered.set()
        try:
            assert release.wait(timeout=5)
            return original_read(*args, **kwargs)
        finally:
            finished.set()
    service.read_snapshot = blocked_read
    async def exercise():
        transport = httpx.ASGITransport(app=ResearchTimingMiddleware(boundary[0].app))
        async with httpx.AsyncClient(transport=transport,base_url='https://alphaos.onrender.com') as client:
            task = asyncio.create_task(client.post('/v1/research/market', json=dict(symbol='QQQ',research_mode='historical'),
                headers={'Authorization':'Bearer owner-test-secret','X-AlphaOS-Request-ID':'c'*32}))
            try:
                assert await asyncio.to_thread(entered.wait, 5)
                task.cancel()
                # Starlette/AnyIO may shield the sync worker while unwinding.
                # Release it independently instead of waiting on cancellation
                # to kill a Python thread (which it cannot do).
                await asyncio.sleep(.02)
                assert not finished.is_set()
                release.set()
                with pytest.raises(asyncio.CancelledError):
                    await task
            finally:
                release.set()
            assert await asyncio.to_thread(finished.wait, 5)
            # Wait for the worker's enclosing execution span to finish too.
            for _ in range(500):
                if any(r['stage']=='research_execution' and r['phase']=='end' for r in records(caplog)):
                    break
                await asyncio.sleep(.01)
    asyncio.run(exercise())
    rows = records(caplog)
    assert any(r['stage']=='request' and r.get('outcome')=='cancelled' for r in rows)
    assert any(r['stage']=='research_execution' and r.get('outcome')=='cancelled' for r in rows)
    assert not any(r['stage']=='history_load' for r in rows)
    boundary[3].assert_not_called()
    assert {r['request_id'] for r in rows} == {'c'*32}


def test_nonresearch_requests_have_no_timing_or_receive_interference(caplog):
    async def exercise():
        async def app(scope,receive,send): pass
        async def unused(): raise AssertionError('Must not consume receive')
        await ResearchTimingMiddleware(app)(dict(type='http',method='GET',path='/health'),unused,unused)
    asyncio.run(exercise())
    assert not records(caplog)
