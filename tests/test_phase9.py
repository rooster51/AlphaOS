from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import Mock
import json
import pytest
from test_api_hardening import env, manual, dataset
from alphaos_api.phase9 import UnifiedResearch
from alphaos_api.phase9_contracts import UnifiedTradeResponse, SymbolResearchResponse
from modules.market_state_research import build_research_dataset
from modules.threshold_survival import threshold_research
from modules.unified_trade import SCENARIO_CAVEAT
from modules.daily_archive import json_value


def qqq(provider):
    provider.quote.return_value[0]['symbol']='QQQ'
    provider.quote.return_value[0].update(bid=99.99,ask=100.01)
    provider.chain.return_value['symbol']='QQQ'
    for side in ('puts','calls'):
        for leg in provider.chain.return_value[side]:leg['contract']=leg['contract'].replace('SPY','QQQ')
    bars=dataset()['features'][['date','symbol','open','high','low','close']].assign(symbol='QQQ')
    provider.history.return_value=build_research_dataset(bars,'2022-01-01',dict(source='fixture'))


def run(client,**changes):
    args=dict(expiration='2026-09-25',maximum_candidates=2,minimum_credit=.01)
    args.update(changes)
    return client.get('/v1/research/QQQ/run',params=args)


def test_run_qqq_one_snapshot_unranked_trade_sections(env):
    c,p,s,clock=env;qqq(p)
    r=run(c);assert r.status_code==200,r.text
    out=r.json();SymbolResearchResponse.model_validate(out)
    assert out['status']=='complete' and out['stages']==['data_validation','market_snapshot','price_structure','candidate_scan','unified_candidate_research']
    assert len(out['qualifying_candidates'])==2
    assert out['live_trade_state']['usable_for_live_research']
    assert out['live_trade_state']['current_spot']!=out['market_snapshot']['research_close']
    scan=out['candidate_scan']['candidates']
    assert [t['trade_snapshot']['candidate_id'] for t in out['qualifying_candidates']]==[t['candidate_id'] for t in scan]
    assert [t['strategy'] for t in scan]==['Bull put spread','Bear call spread']
    for trade in out['qualifying_candidates']:
        UnifiedTradeResponse.model_validate(trade)
        assert trade['advanced_research']['snapshot_id']==out['market_snapshot']['snapshot_id']
        assert trade['historical_scenario_payoff']['caveat']==SCENARIO_CAVEAT
        assert trade['trade_snapshot']['live_trade_state']['quote_as_of']==out['live_trade_state']['quote_as_of']
        assert 'probability' not in json.dumps(trade['historical_analog_behavior'])
    p.quote.assert_called_once_with('QQQ');p.history.assert_called_once();p.chain.assert_called_once()


@pytest.mark.parametrize('status',['stale','unknown','closed'])
def test_data_gate_precedes_scan(env,status):
    c,p,s,clock=env;qqq(p)
    if status=='stale':p.quote.return_value[0]['updated_at']='2026-09-23T15:00:00Z'
    elif status=='unknown':p.quote.return_value[0]['updated_at']='2026-09-24 15:00:00'
    else:
        clock.value=datetime(2026,9,26,14,tzinfo=timezone.utc)
        p.quote.return_value[0]['updated_at']='2026-09-25T23:59:55Z'
    result=run(c).json()
    assert result['status']==('context_only' if status=='closed' else 'live_research_stopped')
    assert result['live_trade_state']['current_spot'] is None
    assert not result['live_trade_state']['usable_for_live_research']
    assert result['qualifying_candidates']==[] and result['candidate_scan'] is None
    p.chain.assert_not_called();p.expirations.assert_not_called()
    if status!='closed':p.history.assert_not_called()
    else:assert result['market_snapshot']['research_session'] is not None


def test_bad_bid_ask_does_not_stop_last_price_research(env):
    c,p,s,clock=env;qqq(p);p.quote.return_value[0].update(bid=99,ask=110)
    out=run(c).json()
    assert out['status']=='complete'
    state=out['live_trade_state']
    assert state['usable_for_live_research'] and not state['usable_for_execution_analysis']
    assert state['quote_quality']['bid_ask_reason']=='abnormally_wide_spread'
    assert all(not t['trade_snapshot']['live_trade_state']['usable_for_execution_analysis'] for t in out['qualifying_candidates'])


@pytest.mark.parametrize('kind,short,long',[('put',99,98),('call',101,102)])
def test_unified_vertical_level_evidence_and_payoff_parity(env,kind,short,long):
    c,p,s,clock=env
    url='/v1/research/SPY/vertical'
    args=dict(expiration='2026-09-25',option_type=kind,short_strike=short,long_strike=long,include_advanced=True)
    r=c.get(url,params=args);assert r.status_code==200,r.text
    out=r.json();UnifiedTradeResponse.model_validate(out)
    t=out['trade_snapshot'];assert t['width']==1 and t['credit']==pytest.approx(.35)
    assert t['max_profit']==pytest.approx(35) and t['max_loss']==pytest.approx(65)
    assert t['return_on_risk']==pytest.approx(35/65)
    assert t['breakeven']==pytest.approx(short+(.35 if kind=='call' else -.35))
    bundle,trade,_=s.exact_trade('SPY','2026-09-25',kind,short,long,3)
    raw=s.research(bundle,trade)
    assert out['historical_scenario_payoff']['summary']==json_value(raw['evidence']['economics']['net_summary'])
    counts=out['historical_scenario_payoff']['outcome_counts']
    assert counts['n']==sum(counts[k] for k in ('full_profit','max_loss','partial'))
    bridged={**raw['primary'],'target':dict(raw['primary']['target'])};bridged['target']['close']=100
    levels=out['historical_analog_behavior']['levels']
    assert [x['level'] for x in levels]==['short_strike','breakeven','long_strike']
    for level in levels:
        expected=threshold_research(bridged,kind,3,threshold_price=level['price'],allow_opposite=True)
        assert level['statistics']==expected['summary']
        assert level['distance']['fraction']==pytest.approx(level['price']/100-1)
    assert out['advanced_research']['metadata']['ohlc_sha256']==raw['provenance']['ohlc_sha256']
    assert len(out['advanced_research']['analog_table'])==len(raw['primary']['analogs'])
    prices=[x['price'] for x in out['market_structure']['price_ladder']]
    assert prices==sorted(prices,reverse=True)


def test_overview_find_refresh_and_saved_candidate(env):
    c,p,s,clock=env;qqq(p)
    overview=run(c,mode='overview').json()
    assert overview['candidate_scan'] is None
    p.chain.assert_not_called()
    find=run(c,mode='find').json()
    assert find['qualifying_candidates']==[] and find['candidate_scan']['candidates']
    cid=find['candidate_scan']['candidates'][0]['candidate_id']
    result=c.get('/v1/research/candidates/'+cid)
    assert result.status_code==200
    assert result.json()['trade_snapshot']['candidate_id']==cid
    assert p.quote.call_count==1
    assert run(c,mode='overview',refresh=True).status_code==200 and p.quote.call_count==2
    clock.advance(121)
    assert c.get('/v1/research/candidates/'+cid).status_code==410


def test_explicit_trade_remains_non_live_and_existing_endpoints_unchanged(env):
    c,p,s,clock=env;p.quote.side_effect=RuntimeError('must not fetch')
    r=c.post('/v1/research/trade',json=manual());assert r.status_code==200,r.text
    state=r.json()['trade_snapshot']['live_trade_state']
    assert state['current_spot'] is None and not state['usable_for_live_research']
    assert r.json()['trade_snapshot']['scenario_spot']==100
    assert r.json()['trade_snapshot']['research_state']['research_close']!=100
    assert c.post('/v1/trade/research',json=manual()).status_code==200
    p.quote.assert_not_called()


def test_partial_provider_failure_and_invalid_input(env):
    c,p,s,clock=env;qqq(p);p.chain.side_effect=RuntimeError('SECRET-DO-NOT-EXPOSE')
    r=run(c);assert r.status_code==200 and r.json()['status']=='partial'
    assert 'SECRET' not in r.text
    assert run(c,maximum_candidates=100).status_code==422
    assert run(c,mode='guess').status_code==422
    assert c.get('/v1/research/QQQ/vertical?short_strike=735&long_strike=734&option_type=put').status_code==422


def test_quote_expiring_during_overview_cannot_be_reported_live(env):
    c,p,s,clock=env;qqq(p)
    history=p.history.return_value
    def slow_history(*args):
        clock.advance(121)
        return history
    p.history.side_effect=slow_history
    out=run(c,mode='overview').json()
    assert out['status']=='live_research_stopped'
    assert not out['live_trade_state']['usable_for_live_research']
    assert out['live_trade_state']['current_spot'] is None
    p.chain.assert_not_called()


def test_unified_view_preserves_advanced_workspace(env):
    from streamlit.testing.v1 import AppTest
    c,p,s,clock=env
    bundle,trade,_=s.exact_trade('SPY','2026-09-25','put',99,98,3)
    raw=s.research(bundle,trade)
    app=AppTest.from_string('import streamlit as st\nfrom modules.unified_trade_view import render_unified_trade\nrender_unified_trade(st.session_state["fixture"])',default_timeout=60)
    app.session_state['fixture']=raw;app.run()
    assert not app.exception
    headings=' '.join(x.value for x in app.markdown)
    for name in ('Trade Snapshot','Market Structure','Historical Analog Behavior','Historical Scenario Payoff'):
        assert name in headings
    assert any(SCENARIO_CAVEAT in w.value for w in app.warning)
    level_table=next(x.value for x in app.dataframe if 'Level' in x.value.columns)
    assert list(level_table.Level)==['short_strike','breakeven','long_strike']
