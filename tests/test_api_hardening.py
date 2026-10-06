from copy import deepcopy
from datetime import datetime,date,timedelta,timezone
import importlib
import json
import logging
import subprocess
import sys
from unittest.mock import Mock,patch
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from modules.market_state_research import build_research_dataset
from modules.option_scenario_ev import scenario_economics
from modules.public_provider import configuration,PublicProviderError
from alphaos_api.service import ResearchService,required_credits
from alphaos_api.contracts import ResponseMeta
api=importlib.import_module('alphaos_api.app')

class Clock:
    def __init__(self):self.value=datetime(2026,9,24,15,tzinfo=timezone.utc)
    def __call__(self):return self.value
    def advance(self,seconds):self.value+=timedelta(seconds=seconds)


def dataset():
    p=100+3*np.sin(np.arange(260)/6)
    return build_research_dataset(pd.DataFrame(dict(date=pd.bdate_range('2020-01-02',periods=260),symbol='SPY',
        open=p,high=p+1,low=p-1,close=p)),'2022-01-01',dict(source='fixture'))


def leg(k,kind,bid):
    return dict(contract=f"SPY260925{'P' if kind=='Put' else 'C'}{int(k*1000):08d}",type=kind,strike=float(k),bid=bid,ask=bid+.05,
        bid_timestamp='2026-09-24T15:00:00Z',ask_timestamp='2026-09-24T15:00:00Z')


def chain():
    return dict(symbol='SPY',expiration='2026-09-25',puts=[leg(k,'Put',b) for k,b in [(96,.1),(97,.3),(98,.7),(99,1.1)]],
        calls=[leg(k,'Call',b) for k,b in [(101,1.1),(102,.7),(103,.3),(104,.1)]])

@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv('ALPHAOS_API_TOKEN','test-api-secret')
    monkeypatch.setenv('PUBLIC_API_SECRET','fake-public-secret')
    monkeypatch.setenv('PUBLIC_ACCOUNT_NUMBER','fake-account-number')
    provider=Mock();provider.quote.return_value=[dict(symbol='SPY',last=100.,updated_at='2026-09-24T15:00:00Z')]
    provider.expirations.return_value=['2026-09-25'];provider.chain.return_value=chain();provider.history.return_value=dataset()
    clock=Clock();service=ResearchService(provider,clock);monkeypatch.setattr(api.app.state,'service',service)
    client=TestClient(api.app);client.headers['Authorization']='Bearer test-api-secret'
    return client,provider,service,clock


def vertical(client,**params):
    args=dict(expiration='2026-09-25',option_type='put',short_strike=99,long_strike=98,horizon=3);args.update(params)
    return client.get('/v1/options/SPY/vertical',params=args)


def manual():
    return dict(symbol='SPY',expiration='2026-09-25',spot=100,credit=.35,horizon=3,
        legs=[dict(type='Put',strike=99,qty=-1),dict(type='Put',strike=98,qty=1)])


def test_authentication_fail_closed(env,monkeypatch):
    c,p,_,_=env
    assert c.get('/health',headers={'Authorization':''}).status_code==200
    assert c.get('/v1/market/SPY',headers={'Authorization':''}).status_code==401
    assert c.get('/v1/market/SPY',headers={'Authorization':'Bearer wrong'}).status_code==403
    monkeypatch.delenv('ALPHAOS_API_TOKEN')
    assert c.get('/v1/market/SPY').status_code==503
    p.quote.assert_not_called();p.history.assert_not_called()

@pytest.mark.parametrize('h',[1,2,3,5,10])
def test_horizons_schema_and_separate_anchors(env,h):
    c,p,_,_=env;r=c.get('/v1/market/SPY',params={'horizon':h})
    assert r.status_code==200,r.text
    meta=r.json()['meta'];ResponseMeta.model_validate(meta)
    assert meta['current_spot']==100 and meta['research_close']!=100
    assert meta['research_session']<'2026-09-24' and meta['quote_as_of'].startswith('2026-09-24')
    assert meta['observed_session_horizon']==h
    assert r.json()['evidence']['analog_N']>0

@pytest.mark.parametrize('url,code',[('/v1/market/IWM','unsupported_symbol'),('/v1/market/SPY?horizon=4','unsupported_horizon')])
def test_invalid_request_before_provider(env,url,code):
    c,p,_,_=env;r=c.get(url);assert r.status_code==400 and r.json()['error']['code']==code
    p.quote.assert_not_called()

@pytest.mark.parametrize('kind,short,long',[('put',99,98),('call',101,102)])
def test_exact_lookup_credit_mapping_and_provenance(env,kind,short,long):
    c,p,service,_=env;r=vertical(c,option_type=kind,short_strike=short,long_strike=long)
    assert r.status_code==200,r.text
    e=r.json()['evidence'];assert e['context']['credit']==pytest.approx(.35)
    assert e['context']['short_strike']==short and e['context']['long_strike']==long
    assert e['quotes']['short_contract']['contract'].startswith('SPY260925')
    assert e['quotes']['pricing_method'].startswith('short bid minus long ask')
    assert e['analog_N']>0 and 'required_credit' in e and len(e['robustness'])==5
    assert e['threshold']['touch_frequency']==e['historical_touch_breach']
    p.quote.assert_called_once_with('SPY');p.chain.assert_called_once_with('SPY','2026-09-25');p.history.assert_called_once()

@pytest.mark.parametrize('params,code',[
 ({'short_strike':98,'long_strike':99},'invalid_vertical_orientation'),
 ({'expiration':'2026-09-23'},'expired_option'),
 ({'expiration':'2026-09-26'},'expiration_unavailable'),
 ({'short_strike':99.5},'contract_unavailable')])
def test_invalid_vertical_requests(env,params,code):
    r=vertical(env[0],**params);assert r.json()['error']['code']==code

@pytest.mark.parametrize('mutation,code',[
 ('missing','missing_quote'),('crossed','crossed_market'),('zero','nonpositive_natural_credit'),
 ('duplicate','contract_unavailable'),('identity','contract_mismatch'),('wrong_expiry','incomplete_chain')])
def test_quote_and_contract_validation(env,mutation,code):
    c,p,_,_=env;raw=chain()
    if mutation=='missing':raw['puts'][-1]['ask']=None
    if mutation=='crossed':raw['puts'][-1]['ask']=.1
    if mutation=='zero':raw['puts'][-1]['bid']=.5
    if mutation=='duplicate':raw['puts'].append(deepcopy(raw['puts'][-1]))
    if mutation=='identity':raw['puts'][-1]['contract']='SPY260926P00099000'
    if mutation=='wrong_expiry':raw['expiration']='2026-09-26'
    p.chain.return_value=raw
    r=vertical(c);assert r.status_code>=400 and r.json()['error']['code']==code,r.text

@pytest.mark.parametrize('status,code',[(401,'public_authentication_failure'),(403,'public_authentication_failure'),(429,'public_rate_limit'),(500,'provider_unavailable')])
def test_provider_errors_never_expose_credentials(env,status,code,caplog):
    c,p,_,_=env;error=RuntimeError('fake-public-secret fake-account-number test-api-secret bearer-auth-value')
    error.status_code=status;p.quote.side_effect=error
    with caplog.at_level(logging.DEBUG):r=c.get('/v1/quote/SPY')
    assert r.json()['error']['code']==code
    for secret in ['fake-public-secret','fake-account-number','test-api-secret','bearer-auth-value']:
        assert secret not in r.text and secret not in caplog.text


def test_validation_and_unexpected_errors_are_sanitized(env,caplog):
    c,p,service,_=env;r=c.post('/v1/trade/research',json={'symbol':'fake-public-secret','secret':'test-api-secret'})
    assert r.status_code==422 and 'fake-public-secret' not in r.text and 'test-api-secret' not in r.text
    with patch.object(service,'quote',side_effect=RuntimeError('fake-public-secret')):
        r=c.get('/v1/quote/SPY')
    assert r.status_code==500 and 'fake-public-secret' not in r.text and 'fake-public-secret' not in caplog.text


def test_allowlisted_response_and_redaction(env):
    c,p,_,_=env;p.quote.return_value[0].update(account_id='actual-private-account',authentication_token='private-auth',bid='fake-public-secret')
    r=c.get('/v1/quote/SPY')
    assert r.status_code==200
    for secret in ['actual-private-account','private-auth','fake-public-secret']:assert secret not in r.text


def test_scan_order_ids_snapshot_reuse_and_staleness(env):
    c,p,service,clock=env
    params=dict(expiration='2026-09-25',research_horizon=3,maximum_candidates=20,minimum_credit=.01)
    a=c.get('/v1/options/SPY/scan',params=params);assert a.status_code==200,a.text
    first=a.json()['evidence'];rows=first['candidates'];assert len(rows)>1
    assert rows[0]['strategy']=='Bull put spread' and rows[1]['strategy']=='Bear call spread'
    b=c.get('/v1/options/SPY/scan',params=params).json()['evidence']
    assert [r['candidate_id'] for r in rows]==[r['candidate_id'] for r in b['candidates']]
    r=c.get('/v1/candidates/'+rows[0]['candidate_id']);assert r.status_code==200,r.text
    p.quote.assert_called_once();p.history.assert_called_once();p.chain.assert_called_once()
    assert not any('score' in k.lower() or 'rank' in k.lower() for row in rows for k in row)
    clock.advance(121)
    stale=c.get('/v1/candidates/'+rows[0]['candidate_id'])
    assert stale.status_code==410 and stale.json()['error']['code']=='stale_snapshot'
    assert c.get('/v1/candidates/not-an-id').status_code==404
    assert c.get('/v1/structure/SPY',params={'snapshot_id':a.json()['meta']['snapshot_id']}).status_code==410


def test_snapshot_reuse_and_mismatch(env):
    c,p,_,_=env;meta=c.get('/v1/market/SPY').json()['meta']
    for endpoint in ('structure','distribution'):
        assert c.get('/v1/'+endpoint+'/SPY',params={'snapshot_id':meta['snapshot_id']}).status_code==200
    assert c.get('/v1/market/QQQ',params={'snapshot_id':meta['snapshot_id']}).status_code==409
    p.quote.assert_called_once();p.history.assert_called_once()


def test_stale_and_incomplete_timestamps_are_reported(env):
    c,p,_,_=env;p.quote.return_value[0]['updated_at']='2026-09-23T15:00:00Z';p.chain.return_value['puts'][-1]['bid_timestamp']=None
    r=vertical(c);assert r.status_code==503,r.text
    assert r.json()['error']['code']=='stale_quote'
    quote=c.get('/v1/quote/SPY').json()
    assert quote['evidence']['timing']['stale_quote']
    assert quote['meta']['current_spot'] is None
    assert c.get('/v1/options/SPY/chain/2026-09-25').json()['evidence']['quality']['timing']['timestamps_incomplete']


def test_required_credit_equations_use_existing_payoff(env):
    c,_,service,_=env;req=api.TradeRequest(**manual());trade=service.manual_trade(req);s=service.snapshot('SPY',3,100)
    ev=scenario_economics(s['prepared']['analog'],trade,3,entry_slippage=2)
    needed=required_credits(trade,ev)
    adjusted={**trade,'credit':needed['required_credit_for_zero_scenario_EV']}
    assert scenario_economics(s['prepared']['analog'],adjusted,3,entry_slippage=2)['net_summary']['expected_payoff']==pytest.approx(0,abs=1e-9)
    adjusted['credit']=needed['required_credit_for_5pct_EV_max_risk']
    assert scenario_economics(s['prepared']['analog'],adjusted,3,entry_slippage=2)['net_summary']['expected_payoff_on_max_risk']==pytest.approx(.05)


def test_compare_preserves_order_and_rejects_mixed_context(env):
    c,_,_,_=env;a=manual();b=deepcopy(a);b['legs'][0]['strike']=98;b['legs'][1]['strike']=97
    r=c.post('/v1/trade/compare',json=dict(research_trade=a,candidates=[b,a]))
    assert r.status_code==200,r.text
    assert [e['context']['short_strike'] for e in r.json()['evidence']['candidates']]==[98,99]
    b['horizon']=5
    assert c.post('/v1/trade/compare',json=dict(research_trade=a,candidates=[b])).json()['error']['code']=='comparison_context_mismatch'


def test_empty_analog_error(env):
    c,p,service,_=env;s=service.snapshot('SPY',3);s['prepared']['analog']['analogs']=s['prepared']['analog']['analogs'].iloc[:0]
    from modules.daily_archive import digest
    s['prepared']['snapshot_id']=digest({k:v for k,v in s['prepared'].items() if k!='snapshot_id'})
    req=api.TradeRequest(**manual())
    with pytest.raises(api.APIError) as exc:service.research(s,service.manual_trade(req))
    assert exc.value.code=='insufficient_analog_sample'


def test_configuration_precedence_without_streamlit(monkeypatch):
    monkeypatch.setenv('PUBLIC_API_SECRET','env-secret');monkeypatch.setenv('PUBLIC_ACCOUNT_NUMBER','env-account')
    assert configuration({'PUBLIC_API_SECRET':'ui-secret','PUBLIC_ACCOUNT_NUMBER':'ui-account'})==('env-secret','env-account')
    monkeypatch.delenv('PUBLIC_API_SECRET');monkeypatch.delenv('PUBLIC_ACCOUNT_NUMBER')
    assert configuration({'PUBLIC_API_SECRET':'ui-secret'})==('ui-secret',None)


def test_import_without_streamlit():
    script="import sys;sys.path="+repr(sys.path)+";import alphaos_api.app;assert 'streamlit' not in sys.modules"
    r=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True)
    assert r.returncode==0,r.stderr


def test_no_order_routes_and_bearer_openapi(env):
    schema=env[0].get('/openapi.json').json();paths=schema['paths']
    assert not any('order' in path or 'portfolio' in path for path in paths)
    assert all(operation.get('security') for path,methods in paths.items() if path.startswith('/v1') for operation in methods.values())
    assert '/v1/options/{symbol}/scan' in paths and '/v1/candidates/{candidate_id}' in paths


def test_history_rate_limit_and_missing_underlying(env):
    c,p,_,_=env
    p.quote.return_value=[]
    assert c.get('/v1/quote/SPY').json()['error']['code']=='missing_quote'
    p.quote.return_value=[dict(symbol='SPY',last=100,updated_at='2026-09-24T15:00:00Z')]
    from modules.history_diagnostics import HistoryError
    p.history.side_effect=HistoryError('safe',{'symbol':'SPY','requested_period':'FIVE_YEARS','http_status':429})
    assert c.get('/v1/market/SPY').json()['error']['code']=='public_rate_limit'


def test_scan_cap_prefix_and_explicit_refresh(env):
    c,p,_,_=env;params=dict(expiration='2026-09-25',maximum_candidates=2)
    first=c.get('/v1/options/SPY/scan',params=params).json()['evidence']
    assert len(first['candidates'])==2 and first['truncated']
    second=c.get('/v1/options/SPY/scan',params={**params,'maximum_candidates':20}).json()['evidence']
    assert [x['short_strike'] for x in first['candidates']]==[x['short_strike'] for x in second['candidates'][:2]]
    assert c.get('/v1/options/SPY/scan',params={**params,'refresh':True}).status_code==200
    assert p.quote.call_count==2 and p.chain.call_count==2 and p.history.call_count==1


def test_cache_defensive_copy_and_day_cutoff(env):
    c,p,service,clock=env
    s=service.snapshot('SPY',3);s['prepared']['current_spot']=1234
    assert service.snapshot('SPY',3)['prepared']['current_spot']==100
    clock.value=datetime(2026,9,25,1,tzinfo=timezone.utc) # Still Sep 24 in New York.
    p.quote.return_value[0]['updated_at']='2026-09-24T19:59:59Z' # Valid completed-session observation.
    service.snapshot('SPY',3)
    assert p.history.call_args.args[1]==date(2026,9,24)


def test_nonfinite_inputs_and_unsupported_routes(env):
    c,p,_,_=env
    assert c.get('/v1/market/SPY?spot=NaN').status_code==422
    req=manual();req['legs'][0]['qty']=0
    assert c.post('/v1/trade/research',json=req).status_code==422
    assert c.post('/v1/orders',json={}).status_code==404


def test_single_quote_even_if_chain_fetch_exceeds_quote_ttl(env):
    c,p,_,clock=env
    def slow_chain(*args):clock.advance(31);return chain()
    p.chain.side_effect=slow_chain
    assert vertical(c).status_code==200
    p.quote.assert_called_once()


def test_standalone_startup_fails_closed_and_uses_one_worker(monkeypatch):
    from alphaos_api.__main__ import main
    monkeypatch.delenv('ALPHAOS_API_TOKEN',raising=False)
    with pytest.raises(SystemExit,match='must be configured'):main()
    monkeypatch.setenv('ALPHAOS_API_TOKEN','startup-test')
    monkeypatch.setenv('PORT','not-a-port')
    with pytest.raises(SystemExit,match='PORT must'):main()
    monkeypatch.setenv('PORT','8123')
    with patch('uvicorn.run') as run:
        main()
        assert run.call_args.kwargs['port']==8123
        assert run.call_args.kwargs['workers']==1
        assert run.call_args.kwargs['access_log'] is False


def test_chain_timing_and_vertical_economics_fields(env):
    c,_,_,_=env
    r=c.get('/v1/options/SPY/chain/2026-09-25')
    assert not r.json()['evidence']['quality']['timing']['timestamps_incomplete']
    e=vertical(c).json()['evidence']
    assert e['credit']==pytest.approx(.35)
    assert e['max_profit']==pytest.approx(35)
    assert e['max_loss']==pytest.approx(65)
    assert e['short_strike']==99 and e['long_strike']==98
    assert e['quotes']['chain_quality']['incomplete_quote_count']==0
