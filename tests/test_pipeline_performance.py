"""Dense synthetic observations, real verification/REST, no production SLA claim."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
import asyncio
import json
from math import inf, nan
from time import perf_counter

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from alphaos_api.app import sanitized
from alphaos_api.research_compression import ResearchCompressionMiddleware
from modules.options_payoff import trade_analysis
from modules.position_research import research_position
from modules.premium_engine import payoff
from modules.research_control import cancellable_research, checkpoint
from modules.research_timing import ResearchTimingMiddleware
from modules.supabase_archive import read_latest_option_snapshot
from tests.performance_archive_fixture import dense_storage, dense_history, AS_OF, LATE_AS_OF
from tests.test_research2_api import boundary, post
from tests.test_opportunity_session import trade
from tests.benchmark_research_pipeline import WireCapture


def prepare_dense(boundary, delay=0, *, late=False):
    from time import sleep
    client, _, service, _ = boundary
    storages = {symbol:dense_storage(symbol,late=late) for symbol in ('SPY','QQQ')}
    def read(symbol, as_of, **kwargs):
        sleep(delay)
        return read_latest_option_snapshot(storages[symbol], symbol, as_of,
            max_age_seconds=300, **kwargs)
    def history(symbol):
        sleep(delay)
        return dense_history(symbol)
    service.read_snapshot = read
    service.history_loader = history
    service.clock = lambda:datetime.fromisoformat(LATE_AS_OF if late else AS_OF)
    stack = WireCapture(ResearchTimingMiddleware(ResearchCompressionMiddleware(client.app)))
    return TestClient(stack,base_url='https://alphaos.onrender.com'), storages, service, stack


@pytest.mark.parametrize('expiration',['2030-01-02','2030-01-18','2031-01-17'])
@pytest.mark.parametrize('width',[None,5])
def test_four_concurrent_cold_warm_requests_have_deadline_headroom(boundary, expiration, width):
    from modules.research_calendar import _schedule
    _schedule.cache_clear()
    client, _, _, wire = prepare_dense(boundary, delay=.02)
    expected = {}
    def invoke(index):
        symbol = ('SPY','QQQ')[index%2]
        started = perf_counter()
        response = post(client,'market',dict(symbol=symbol,expiration=expiration,
            available_capital=150,width=width))
        assert response.status_code == 200
        assert response.headers['content-encoding'] == 'gzip'
        assert wire.sizes[response.headers['x-alphaos-request-id']] < len(response.content)/5
        data = response.json(); session = data['research']['research_session']
        assert data['request']['width'] == width
        assert session['expiration'] == expiration
        assert session['diagnostics']['width_selection']['search_complete'] is False
        assert session['diagnostics']['capital_rejection_count'] > 0
        assert all(x['research']['max_loss'] <= 150 for x in session['candidates'])
        if width is None:
            assert session['diagnostics']['generated_count'] == 1024
            assert len(session['candidates']) == 105
            assert all(x['research']['trade']['expiration'] == expiration for x in session['candidates'])
            assert all(x['research']['historical_economics']['eligible_for_consideration'] is False for x in session['candidates'])
            assert all(len(x['research']['payoff']['grid']) <= 7 for x in session['candidates'])
        else:
            assert not session['candidates']
            assert session['diagnostics']['zero_candidate_reason'] == 'bounded_search_incomplete'
        return symbol, data, perf_counter()-started
    for _ in range(2):
        with ThreadPoolExecutor(4) as pool:
            rows = list(pool.map(invoke,range(4)))
        assert max(elapsed for _,_,elapsed in rows) < 10.5
        for symbol,data,_ in rows:
            if symbol in expected:
                assert data == expected[symbol]
            else:
                expected[symbol] = data


def test_late_session_constructor_overlap_has_one_explicit_request_budget(boundary):
    client,_,_,_=prepare_dense(boundary,delay=.02,late=True)
    def invoke(index):
        started=perf_counter()
        response=post(client,'market',dict(symbol=('SPY','QQQ')[index%2],available_capital=150))
        assert response.status_code==200
        session=response.json()['research']['research_session']
        assert session['opportunity_state']['time_state']=='late_0dte'
        reports=session['diagnostics']['construction']
        assert len(reports)>=6
        assert sum(report.get('attempted_count',0) for report in reports)<=1024
        assert sum(report['max_attempts'] for report in reports)==1024
        assert all(report['max_total_attempts']==1024 for report in reports)
        assert session['diagnostics']['width_selection']['search_complete'] is False
        assert session['candidates']
        assert all(candidate['research']['max_loss']<=150 for candidate in session['candidates'])
        # Each retained structure still receives the same complete exact math.
        for candidate in session['candidates']:
            result=candidate['research']
            reference=research_position(result['trade'],symbol=session['symbol'],spot=500,as_of='2030-01-02')
            assert (result['max_loss'],result['max_profit'],result['breakevens']) == (
                reference['max_loss'],reference['max_profit'],reference['breakevens'])
        return perf_counter()-started
    with ThreadPoolExecutor(4) as pool:
        assert max(pool.map(invoke,range(4)))<10.5


@pytest.mark.parametrize('legs,credit', [
    ([('Call',500,1),('Call',505,-1)],-1),
    ([('Put',490,1),('Put',495,-1)],1),
    ([('Call',505,-1),('Call',510,1)],1),
    ([('Put',495,-1),('Put',490,1),('Call',505,-1),('Call',510,1)],2),
    ([('Put',500,-1),('Put',495,1),('Call',500,-1),('Call',505,1)],2),
    ([('Put',480,1),('Put',490,-2),('Put',495,1)],1),
    ([('Call',505,1),('Call',510,-2),('Call',520,1)],1),
    ([('Call',495,1),('Call',500,-2),('Call',505,1)],-1),
    ([('Call',500,1)],-1)])
def test_compact_presentation_preserves_all_exact_economics_and_quotes(legs,credit):
    candidate=trade(legs,credit); before=deepcopy(candidate)
    full=research_position(candidate,symbol='QQQ',spot=500,as_of='2030-01-01')
    compact=research_position(candidate,symbol='QQQ',spot=500,as_of='2030-01-01',payoff_detail='landmarks')
    analysis=compact['payoff']
    assert analysis['grid_sampling'] == 'exact_landmarks_and_midpoints'
    for point in analysis['grid']:
        assert point['Expiration P&L ($)'] == payoff(candidate['legs'],credit,
            point['Terminal underlying ($)'])
    assert set([500,*analysis['strikes'],*analysis['breakevens']]) <= {p['Terminal underlying ($)'] for p in analysis['grid']}
    for result in (full,compact):
        for key in ('grid','grid_sampling'):
            result['payoff'].pop(key,None)
    assert compact == full
    assert candidate == before
    assert len(trade_analysis(dict(candidate,shares=0,fees=0))['grid']) > len(analysis['strikes'])


def test_single_pass_sanitization_retains_scalar_and_credential_safety(monkeypatch):
    monkeypatch.setenv('ALPHAOS_API_TOKEN','secret-test-value')
    from enum import IntEnum, StrEnum
    class Number(IntEnum): ONE=1
    class Text(StrEnum): VALUE='secret-test-value'
    value=dict(numeric=[np.int64(1), np.float64(2), nan, inf], enums=[Number.ONE,Text.VALUE],
        nested={'secret_field':'x','ok':'prefix secret-test-value suffix'},
        frame=pd.DataFrame({'v':[1]}), day=datetime(2030,1,2))
    clean=sanitized(value)
    assert clean['numeric'] == [1,2,None,None]
    assert clean['enums'] == [1,'[REDACTED]']
    assert clean['nested'] == {'ok':'prefix [REDACTED] suffix'}
    assert clean['frame'] == [{'v':1}]
    assert clean['day'] == '2030-01-02T00:00:00'
    assert sanitized(dict(schema_version='alphaos-interface-v2',x=inf))['x']=='unlimited'
    json.dumps(clean,allow_nan=False)


def test_cancellation_is_local_and_checked_inside_enumeration():
    from modules.width_discovery import discover_widths
    from tests.test_width_discovery import chain
    with cancellable_research() as event:
        event.set()
        with pytest.raises(asyncio.CancelledError):
            discover_widths(chain(),100,{'call_debit_spread'})
    checkpoint()  # The cancelled event does not leak into another request.


def test_observed_disconnect_stops_worker_after_io_without_cancelling_peer(boundary,monkeypatch):
    import httpx
    from fastapi import Request
    from threading import Event
    from tests.test_archive_read_path import ReadOnlyClient
    from tests.test_website_mcp_parity import prepare_storage
    client,_,service,loader=boundary
    storages={symbol:ReadOnlyClient() for symbol in ('SPY','QQQ')}
    for symbol,storage in storages.items(): prepare_storage(storage,symbol)
    entered,release,finished=Event(),Event(),Event()
    def read(symbol,as_of,**kwargs):
        if symbol=='QQQ':
            entered.set()
            try:
                assert release.wait(5)
            finally:
                finished.set()
        return read_latest_option_snapshot(storages[symbol],symbol,as_of,max_age_seconds=300,**kwargs)
    service.read_snapshot=read
    async def observed(request):
        return request.headers.get('x-alphaos-request-id')=='c'*32 and entered.is_set()
    # Exercise the handler's observed-disconnect path after body validation.
    monkeypatch.setattr(Request,'is_disconnected',observed)
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client.app),base_url='https://alphaos.onrender.com') as transport:
            def invoke(symbol,identifier):
                return transport.post('/v1/research/market',json=dict(symbol=symbol,available_capital=150),headers={
                    'Authorization':'Bearer owner-test-secret','X-AlphaOS-Request-ID':identifier*32})
            cancelled=asyncio.create_task(invoke('QQQ','c'))
            peer=asyncio.create_task(invoke('SPY','d'))
            try:
                assert await asyncio.to_thread(entered.wait,5)
                abandoned=await asyncio.wait_for(cancelled,2)
                assert abandoned.status_code==499 and not abandoned.content
                response=await peer
                assert response.status_code==200 and response.json()['request']['symbol']=='SPY'
                assert not finished.is_set()  # No claim that a blocking call was killed.
            finally:
                release.set()
            assert await asyncio.to_thread(finished.wait,5)
            await asyncio.sleep(.05)
    asyncio.run(exercise())
    assert [call.args[0] for call in loader.call_args_list]==['SPY']


@pytest.mark.parametrize('defect',['stale','missing','checksum'])
def test_concurrent_bad_archive_never_uses_peer_or_history_fallback(boundary,defect):
    from tests.test_archive_read_path import ReadOnlyClient
    from tests.test_website_mcp_parity import prepare_storage
    client,_,service,loader=boundary
    storages={symbol:ReadOnlyClient() for symbol in ('SPY','QQQ')}
    for symbol,storage in storages.items(): prepare_storage(storage,symbol)
    if defect=='stale': storages['QQQ'].row['observed_at']='2030-01-02T19:00:00+00:00'
    elif defect=='missing': storages['QQQ'].row=None
    else: storages['QQQ'].row['archive_sha256']='invalid'
    service.read_snapshot=lambda symbol,as_of,**kwargs:read_latest_option_snapshot(
        storages[symbol],symbol,as_of,max_age_seconds=300,**kwargs)
    with ThreadPoolExecutor(2) as pool:
        responses=list(pool.map(lambda symbol:post(client,'market',dict(symbol=symbol,available_capital=150)),['SPY','QQQ']))
    assert [response.status_code for response in responses]==[200,503]
    assert [call.args[0] for call in loader.call_args_list]==['SPY']


@pytest.mark.parametrize('limits',[{'max_attempts':1.5},{'max_total_attempts':1.5}])
def test_fractional_search_budgets_cannot_disable_attempt_limit(limits):
    from modules.width_discovery import discover_widths
    from tests.test_width_discovery import chain
    with pytest.raises(ValueError):
        discover_widths(chain(),100,{'call_debit_spread'},**limits)
