from copy import deepcopy
from datetime import timedelta
from uuid import uuid4
import pytest
from test_api_hardening import env, chain
from alphaos_api.positions import PositionStore


@pytest.fixture(autouse=True)
def position_db(tmp_path,monkeypatch):
    path=tmp_path/'positions.sqlite3'
    monkeypatch.setenv('ALPHAOS_POSITIONS_DB',str(path))
    return path


def entry(**changes):
    value=dict(request_id=str(uuid4()),symbol='SPY',strategy='PCS',expiration='2026-09-25',
        short_strike=99,long_strike=98,quantity=2,entry_credit=.35,entry_timestamp='2026-09-24T14:00:00Z')
    value.update(changes)
    return value


def record(c,**changes):
    r=c.post('/v1/positions',json=entry(**changes))
    assert r.status_code==200,r.text
    return r.json()


def monitor(c,p):
    r=c.get('/v1/positions/'+p['position_id']+'/monitor')
    assert r.status_code==200,r.text
    return r.json()


@pytest.mark.parametrize('strategy,short,long,breakeven',[('PCS',99,98,98.65),('CCS',101,102,101.35)])
def test_entry_economics_and_immutable_refresh(env,position_db,strategy,short,long,breakeven):
    c,provider,service,clock=env
    p=record(c,strategy=strategy,short_strike=short,long_strike=long)
    assert p['max_profit_at_entry']==70
    assert p['max_loss_at_entry']==130
    assert p['contract_multiplier']==100 and p['breakeven_at_entry']==breakeven
    saved=deepcopy(p['entry_snapshot'])
    assert saved['captured_at']!=p['entry_timestamp']
    assert saved['historical_evidence'] is not None
    assert saved['structure'] is not None
    provider.history.reset_mock()
    result=monitor(c,p);current=result['current_snapshot']
    assert current['estimated_close_debit']==pytest.approx(.45)
    assert current['estimated_pl']==pytest.approx(-20)
    assert current['percent_max_profit_captured']==pytest.approx(-100*.1/.35)
    assert current['remaining_max_loss_exposure']==pytest.approx(110)
    assert result['monitoring_state']['state']=='THESIS_INTACT'
    assert result['entry_vs_current']['underlying_move']==0
    provider.history.assert_not_called()
    assert PositionStore(position_db).get(p['position_id'])['entry_snapshot']==saved


@pytest.mark.parametrize('strategy,short,long,spot,boundaries',[
    ('PCS',99,98,99,['short_strike']),('PCS',99,98,98.5,['short_strike','breakeven']),
    ('CCS',101,102,101,['short_strike']),('CCS',101,102,101.5,['short_strike','breakeven'])])
def test_boundary_crossings(env,strategy,short,long,spot,boundaries):
    c,provider,_,_=env;p=record(c,strategy=strategy,short_strike=short,long_strike=long)
    provider.quote.return_value[0]['last']=spot
    state=monitor(c,p)['monitoring_state']
    assert state['state']=='BOUNDARY_BREACHED'
    assert state['breached_boundaries']==boundaries


def test_pressure_buffer_and_delta(env):
    c,provider,_,_=env
    provider.chain.return_value['puts'][-1]['delta']=-.20
    p=record(c)
    provider.quote.return_value[0]['last']=99.4
    provider.chain.return_value['puts'][-1]['delta']=-.31
    result=monitor(c,p)
    assert result['monitoring_state']['state']=='UNDER_PRESSURE'
    assert 'short_strike_buffer_reduced_by_at_least_half' in result['monitoring_state']['reasons']
    assert 'absolute_short_delta_increased_at_least_0.10' in result['monitoring_state']['reasons']
    assert result['entry_vs_current']['short_delta_change']==pytest.approx(-.11)


@pytest.mark.parametrize('problem',['stale_underlying','stale_leg','missing_bid','missing_ask','crossed','identity','absent_contract','invalid_spread'])
def test_unavailable_quotes_never_fabricate_pl(env,problem):
    c,provider,_,_=env;p=record(c)
    leg=provider.chain.return_value['puts'][-1]
    if problem=='stale_underlying':provider.quote.return_value[0]['updated_at']='2026-09-23T15:00:00Z'
    elif problem=='stale_leg':leg['bid_timestamp']='2015-01-01T00:00:00Z'
    elif problem=='missing_bid':leg['bid']=None
    elif problem=='missing_ask':leg['ask']=None
    elif problem=='crossed':leg['ask']=.01
    elif problem=='identity':leg['contract']='SPY260925P00199000'
    elif problem=='absent_contract':provider.chain.return_value['puts'].pop()
    else:leg.update(bid=3,ask=3.1)
    result=monitor(c,p)
    assert result['current_snapshot']['estimated_pl'] is None
    assert result['current_snapshot']['errors']
    assert result['monitoring_state']['state']!='THESIS_INTACT'
    assert result['position']['status']=='active'


def test_list_ambiguous_close_and_reload(env,position_db):
    c,provider,_,clock=env;p=record(c);record(c)
    listed=c.get('/v1/positions?symbol=SPY').json()
    assert listed['match_count']==2 and listed['requires_selection']
    assert c.get('/v1/positions?symbol=QQQ').json()['positions']==[]
    close=dict(amount=.07,cashflow='debit',timestamp=clock().isoformat())
    url='/v1/positions/'+p['position_id']+'/close'
    r=c.post(url,json=close);assert r.status_code==200,r.text
    assert r.json()['close']['declared_pl']==pytest.approx(56)
    assert c.post(url,json=close).json()==r.json()
    assert c.post(url,json={**close,'amount':.08}).status_code==409
    assert PositionStore(position_db).get(p['position_id'])['status']=='closed'
    assert len(PositionStore(position_db).active())==1
    assert c.get('/v1/positions/'+p['position_id']+'/monitor').status_code==409


def test_credit_close_and_timestamps(env):
    c,_,_,clock=env;p=record(c,quantity=3)
    url='/v1/positions/'+p['position_id']+'/close'
    assert c.post(url,json=dict(amount=.1,timestamp='2026-09-24T13:00:00Z')).status_code==422
    assert c.post(url,json=dict(amount=.1,timestamp='2026-09-25T15:00:00Z')).status_code==422
    r=c.post(url,json=dict(amount=.1,cashflow='credit',timestamp=clock().isoformat()))
    assert r.json()['close']['declared_pl']==pytest.approx(135)


def test_idempotency_and_no_future_entry(env):
    c,provider,_,_=env;req=entry()
    first=c.post('/v1/positions',json=req)
    provider.reset_mock()
    assert c.post('/v1/positions',json=req).json()==first.json()
    provider.quote.assert_not_called();provider.chain.assert_not_called()
    assert c.post('/v1/positions',json={**req,'entry_credit':.4}).status_code==409
    assert c.post('/v1/positions',json=entry(entry_timestamp='2026-09-25T15:00:00Z')).status_code==422


@pytest.mark.parametrize('changes',[dict(strategy='IC'),dict(quantity=0),dict(quantity=1.5),dict(entry_credit=1),
    dict(entry_credit=-.1),dict(short_strike=97),dict(entry_timestamp='2026-09-24T14:00:00'),dict(symbol='IWM')])
def test_invalid_inputs(env,changes):
    assert env[0].post('/v1/positions',json=entry(**changes)).status_code==422


def test_expiration_does_not_close_and_monitor_never_calls_history(env):
    c,provider,_,clock=env;p=record(c);clock.advance(3*86400)
    provider.history.reset_mock()
    result=monitor(c,p)
    assert result['position']['status']=='active'
    assert result['current_snapshot']['calendar_dte']==-2
    assert result['current_snapshot']['estimated_pl'] is None
    provider.history.assert_not_called()


def test_auth_and_no_broker_calls(env):
    c,provider,_,_=env
    assert c.post('/v1/positions',json=entry(),headers={'Authorization':''}).status_code==401
    p=record(c);monitor(c,p)
    assert {call[0] for call in provider.mock_calls} <= {'chain','quote','expirations','history'}


def test_positive_pl_and_quality_recovery(env):
    c,provider,_,_=env;p=record(c)
    provider.chain.return_value['puts'][-1].update(bid=.75,ask=.77)
    r=monitor(c,p)['current_snapshot']
    assert r['estimated_close_debit']==pytest.approx(.07)
    assert r['estimated_pl']==pytest.approx(56)
    assert r['percent_max_profit_captured']==pytest.approx(80)


def test_missing_evidence_is_not_reconstructed(env):
    c,provider,_,_=env
    provider.quote.return_value[0]['updated_at']='2026-09-23T15:00:00Z'
    provider.chain.return_value['puts'][-1]['ask']=None
    p=record(c)
    assert p['entry_snapshot']['historical_evidence'] is None
    assert p['entry_snapshot']['estimated_close_debit'] is None
    assert monitor(c,p)['monitoring_state']['state'] is None


def test_fixture_latency_profile(env):
    import json
    from statistics import median
    from time import perf_counter
    c,provider,_,_=env
    start=perf_counter();p=record(c);record_ms=(perf_counter()-start)*1000
    samples=[]
    provider.history.reset_mock()
    for _ in range(10):
        start=perf_counter();monitor(c,p);samples.append((perf_counter()-start)*1000)
    provider.history.assert_not_called()
    print('\nPOSITION_LATENCY '+json.dumps(dict(environment='Deterministic in-process TestClient; provider fixtures, no network',
        record_with_full_entry_research_ms=round(record_ms,2),monitor_samples=10,
        monitor_median_ms=round(median(samples),2),monitor_max_ms=round(max(samples),2),historical_calls_during_monitor=0)))
