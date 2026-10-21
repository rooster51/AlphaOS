"""Regression evidence uses synthetic observations, never production SLA claims."""
import asyncio
from copy import deepcopy
import json
import logging
from threading import Event

import httpx
import pandas as pd
import pytest

from alphaos_api.app import sanitized
from modules.market_state import market_state_features, validate_ohlc
from modules.opportunity_classifier import history_evidence
from modules.position_research import research_position
from modules.research_control import checkpoint
from modules.research_timing import ResearchTimingMiddleware, execution, stage
from modules.historical_economics import evaluate_historical_economics, _evaluate_validated_position
from tests.performance_archive_fixture import dense_history
from tests.test_research2_api import boundary
from tests.test_opportunity_session import trade


def test_shared_calendar_ranges_match_authoritative_rules_and_are_isolated():
    import pandas_market_calendars as mcal
    from modules.research_calendar import nyse_schedule, _calendar, _schedule
    _schedule.cache_clear()
    _calendar.cache_clear()
    authority=mcal.get_calendar('NYSE')
    for start,end in [('2026-10-21','2026-10-21'),('2026-11-26','2026-11-27'),
                      ('2026-10-21','2028-01-21')]:
        actual=nyse_schedule(start,end)
        pd.testing.assert_frame_equal(actual,authority.schedule(start_date=start,end_date=end))
        original=actual.copy(deep=True)
        actual.iloc[0,0]=pd.Timestamp('2000-01-01',tz='UTC')
        pd.testing.assert_frame_equal(nyse_schedule(start,end),original)


@pytest.mark.parametrize('legs,credit',[
    ([('Call',500,1),('Call',505,-1)],-1),
    ([('Put',500,1),('Put',495,-1)],-1),
    ([('Put',490,1),('Put',495,-1)],1),
    ([('Call',505,-1),('Call',510,1)],1),
    ([('Put',495,-1),('Put',490,1),('Call',505,-1),('Call',510,1)],2),
    ([('Put',500,-1),('Put',495,1),('Call',500,-1),('Call',505,1)],2),
    ([('Put',480,1),('Put',490,-2),('Put',495,1)],1),
    ([('Call',505,1),('Call',510,-2),('Call',520,1)],1),
    ([('Call',495,1),('Call',500,-2),('Call',505,1)],-1),
    ([('Call',500,1)],-1),([('Put',500,1)],-1)])
def test_reused_economics_match_independent_validation_for_all_families(legs,credit):
    candidate=trade(legs,credit)
    candidate.update(fees=2.6,source='Synthetic observed quotes')
    position=research_position(candidate,symbol='QQQ',spot=500,as_of='2030-01-01',payoff_detail='none')
    before=deepcopy(position)
    reused=_evaluate_validated_position(position['trade'],position,as_of='2030-01-01',capital=150)
    validated=evaluate_historical_economics(position['trade'],as_of='2030-01-01',
        holding_period='intraday',available_capital=150)
    assert reused == validated
    assert position == before  # Annotation must not mutate the shared identity.
    forged=dict(candidate,max_loss=0,capital_at_risk=0,max_profit=999999,pop=1)
    assert evaluate_historical_economics(forged,as_of='2030-01-01',holding_period='intraday',available_capital=150) == validated


@pytest.mark.parametrize('length',[1,19,20,49,50,61,1260])
def test_classifier_subset_is_exactly_the_full_indicator_result(length):
    source = dense_history('QQQ').iloc[-length:]
    original = source.copy(deep=True)
    result = history_evidence(source,'QQQ','2030-01-02T18:15:00+00:00')
    full = market_state_features(source,'2030-01-02')
    for index,key in [(-1,'latest'),(-2,'previous')]:
        if len(full) < abs(index):
            assert result[key] == {}
            continue
        for name,value in result[key].items():
            if name != 'date':
                expected = full.iloc[index][name]
                assert value is None if pd.isna(expected) else value == expected
    assert result['audit'] == validate_ohlc(source,'2030-01-02')[1]
    pd.testing.assert_frame_equal(source,original)


def test_redaction_aliases_are_request_local_and_do_not_change_evidence(monkeypatch):
    source = dict(observed_at='2030-01-02',token='hidden',quote=[{'bid':1.0,'ask':1.2}])
    before = deepcopy(source)
    monkeypatch.setenv('PUBLIC_API_SECRET','first-secret')
    output = sanitized(dict(left=source,right=source,message='first-secret'))
    assert output['left'] == output['right'] == dict(observed_at='2030-01-02',quote=[{'bid':1.0,'ask':1.2}])
    assert output['message'] == '[REDACTED]'
    assert source == before
    monkeypatch.setenv('PUBLIC_API_SECRET','second-secret')
    assert sanitized({'message':'second-secret'}) == {'message':'[REDACTED]'}


@pytest.mark.parametrize('phase',['historical_economics','response_serialization'])
def test_real_asgi_disconnect_stops_cpu_work_through_full_middleware(boundary,caplog,monkeypatch,phase):
    """No Request.is_disconnected mock: send an actual ASGI disconnect through
    the BaseHTTPMiddleware stack which can consume it before the route does.
    """
    entered,stopped = Event(),Event()
    logger=logging.getLogger('alphaos_api.research.timing')
    monkeypatch.setattr(logger,'disabled',False)
    monkeypatch.setattr(logger,'propagate',True)
    caplog.set_level(logging.WARNING,logger=logger.name)
    client,_,service,_ = boundary
    from tests.test_website_mcp_parity import prepare_storage
    prepare_storage(boundary[1],'SPY')
    original = service.run
    def run(request,**kwargs):
        if request.symbol == 'SPY':
            assert entered.wait(5)
            return original(request,**kwargs)
        with execution('QQQ','historical'):
            try:
                with stage(phase):
                    entered.set()
                    while True:
                        checkpoint()
            finally:
                stopped.set()
    service.run = run
    stack = ResearchTimingMiddleware(client.app)
    async def exercise():
        disconnect = asyncio.Event()
        consumed = False
        async def receive():
            nonlocal consumed
            if not consumed:
                consumed = True
                return dict(type='http.request',body=json.dumps(dict(symbol='QQQ',research_mode='historical')).encode(),more_body=False)
            await disconnect.wait()
            return dict(type='http.disconnect')
        sent=[]
        async def send(message): sent.append(message)
        scope=dict(type='http',asgi={'version':'3.0','spec_version':'2.3'},http_version='1.1',
            method='POST',scheme='https',path='/v1/research/market',raw_path=b'/v1/research/market',
            root_path='',query_string=b'',server=('alphaos.onrender.com',443),client=('127.0.0.1',1234),
            headers=[(b'content-type',b'application/json'),(b'authorization',b'Bearer owner-test-secret'),
                     (b'x-alphaos-request-id',b'c'*32)])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=stack),base_url='https://alphaos.onrender.com') as transport:
            peer=asyncio.create_task(transport.post('/v1/research/market',json=dict(symbol='SPY',available_capital=150),
                headers={'Authorization':'Bearer owner-test-secret','X-AlphaOS-Request-ID':'d'*32}))
            task=asyncio.create_task(stack(scope,receive,send))
            try:
                assert await asyncio.to_thread(entered.wait,5)
                disconnect.set()
                await asyncio.wait_for(task,3)
                assert await asyncio.to_thread(stopped.wait,1)
                response=await peer
                assert response.status_code == 200
            finally:
                disconnect.set()
                if not task.done(): task.cancel()
                if not peer.done(): peer.cancel()
        assert not any(m.get('status') == 200 for m in sent)
    asyncio.run(exercise())
    records=[json.loads(r.getMessage()) for r in caplog.records if r.name=='alphaos_api.research.timing']
    assert any(r['stage']==phase and r.get('outcome')=='cancelled' for r in records)
    assert any(r['stage']=='client_disconnect' for r in records)
