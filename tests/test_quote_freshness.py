from datetime import datetime, timezone, timedelta
from unittest.mock import Mock
import json
import pytest
from modules.quote_freshness import freshness, normalize_timestamp, require_research_quote, QuoteUnavailable
from alphaos_api.service import ResearchService
from test_api_hardening import env, vertical, manual


def dt(value):
    return datetime.fromisoformat(value.replace('Z','+00:00'))


def q(stamp='2026-09-25T14:00:00Z', **changes):
    return dict(dict(symbol='QQQ',last=745.4,bid=745.2,ask=745.5,updated_at=stamp),**changes)


@pytest.mark.parametrize('stamp',['2026-09-25T14:00:00Z','2026-09-25T10:00:00-04:00',dt('2026-09-25T14:00:00Z'),1790344800,1790344800000])
def test_normalization_preserves_instant(stamp):
    assert normalize_timestamp(stamp)=='2026-09-25T14:00:00+00:00'


@pytest.mark.parametrize('stamp',[None,True,'2026-09-25 14:00:00','bad',float('nan'),1790344800000000])
def test_ambiguous_timestamp_fails_closed(stamp):
    assert normalize_timestamp(stamp) is None
    f=freshness(q(stamp),dt('2026-09-25T14:01:00Z'))
    assert f['data_status']=='unknown' and not f['usable_for_live_research']


@pytest.mark.parametrize('now,stamp,state,status',[
 ('2026-09-25T14:00:30Z','2026-09-25T14:00:00Z','regular_open','fresh'),
 ('2026-09-25T14:03:00Z','2026-09-25T14:00:00Z','regular_open','stale'),
 ('2026-09-26T14:00:00Z','2026-09-25T19:59:55Z','closed','latest_available'),
 ('2026-09-27T14:00:00Z','2026-09-25T19:59:55Z','closed','latest_available'),
 ('2026-09-28T12:00:00Z','2026-09-28T11:59:50Z','extended_hours','fresh'),
 ('2026-09-28T12:00:00Z','2026-09-25T19:59:55Z','extended_hours','stale'),
 ('2026-09-28T14:00:00Z','2026-09-25T19:59:55Z','regular_open','stale'),
 ('2026-09-07T14:00:00Z','2026-09-04T19:59:55Z','closed','latest_available'),
 ('2026-11-27T18:30:00Z','2026-11-27T18:29:50Z','extended_hours','fresh'),
 ('2026-09-26T03:05:51Z','2026-09-25T07:55:31Z','closed','stale'),
])
def test_market_calendar(now,stamp,state,status):
    f=freshness(q(stamp),dt(now))
    assert (f['market_state'],f['data_status'])==(state,status)
    assert f['usable_for_live_research']==(status=='fresh')
    assert f['usable_for_contextual_research']==(status in ('fresh','latest_available'))
    if status!='fresh':
        with pytest.raises(QuoteUnavailable):require_research_quote(q(stamp),dt(now))
    if status=='latest_available':
        assert require_research_quote(q(stamp),dt(now),live=False)['usable_for_contextual_research']


@pytest.mark.parametrize('bid,ask,reason',[(745.2,745.5,'within_spread_limit'),(745.2,754.33,'abnormally_wide_spread'),
 (746,745,'crossed_market'),(0,745,'nonpositive_or_nonfinite_bid_or_ask'),(-1,745,'nonpositive_or_nonfinite_bid_or_ask'),
 (None,745,'missing_bid_or_ask'),(745,None,'missing_bid_or_ask')])
def test_bid_ask_does_not_replace_or_invalidate_fresh_last(bid,ask,reason):
    quote=q(bid=bid,ask=ask);original=quote.copy()
    f=freshness(quote,dt('2026-09-25T14:00:10Z'))
    assert quote==original
    assert f['quote_quality']['bid_ask_reason']==reason
    assert f['usable_for_live_research'] and f['quote_quality']['last_price_valid']
    assert f['usable_for_execution_analysis']==(reason=='within_spread_limit')
    if reason=='abnormally_wide_spread':
        assert f['quote_quality']['bid_ask_spread']==pytest.approx(9.13)
        assert f['quote_quality']['bid_ask_spread_pct']==pytest.approx(9.13/749.765*100)


def test_limits_future_calendar_failure(monkeypatch):
    monkeypatch.setenv('ALPHAOS_MAX_QUOTE_AGE_SECONDS','10')
    assert freshness(q(),dt('2026-09-25T14:00:11Z'))['data_status']=='stale'
    monkeypatch.setenv('ALPHAOS_MAX_QUOTE_AGE_SECONDS','nan')
    assert freshness(q(),dt('2026-09-25T14:00:11Z'))['max_age_seconds']==120
    assert freshness(q('2026-09-25T15:00:00Z'),dt('2026-09-25T14:00:00Z'))['data_status']=='unknown'
    monkeypatch.setattr('modules.quote_freshness.session_schedule',Mock(side_effect=ValueError))
    assert freshness(q(),dt('2026-09-25T14:00:11Z'))['data_status']=='unknown'


@pytest.mark.parametrize('symbol',['QQQ','SPY'])
def test_cache_age_is_not_quote_age(env,symbol):
    c,p,s,clock=env
    p.quote.return_value=[dict(symbol=symbol,last=100,updated_at='2026-09-24T14:58:10Z')]
    a=c.get('/v1/quote/'+symbol).json()
    assert not a['evidence']['cache']['hit']
    assert a['evidence']['freshness']['age_seconds']==110
    assert a['evidence']['freshness']['cache_age_seconds']==0
    clock.advance(5)
    b=c.get('/v1/quote/'+symbol).json()
    assert b['evidence']['cache']['hit'] and b['evidence']['freshness']['data_status']=='fresh'
    clock.advance(10)
    b=c.get('/v1/quote/'+symbol).json()
    assert b['evidence']['cache']['hit'] and b['evidence']['freshness']['data_status']=='stale'
    assert b['meta']['current_spot'] is None and b['meta']['research_close'] is None
    assert b['evidence']['freshness']['cache_age_seconds']==15
    assert b['meta']['quote_freshness']==b['evidence']['freshness']
    clock.advance(16)
    d=c.get('/v1/quote/'+symbol).json()
    assert not d['evidence']['cache']['hit'] and d['evidence']['freshness']['data_status']=='stale'
    assert d['evidence']['freshness']['cache_age_seconds']==0
    assert d['evidence']['freshness']['age_seconds']==141
    assert p.quote.call_count==2


def test_stale_gate_scan_vertical_snapshot_and_manual_separation(env):
    c,p,s,clock=env
    p.quote.return_value[0]['updated_at']='2026-09-24T14:58:10Z'
    scan=c.get('/v1/options/SPY/scan?expiration=2026-09-25&minimum_credit=.01').json()
    cid=scan['evidence']['candidates'][0]['candidate_id']
    snapshot=scan['meta']['snapshot_id']
    clock.advance(11)
    for url in ('/v1/market/SPY?snapshot_id='+snapshot,'/v1/candidates/'+cid,'/v1/options/SPY/scan?expiration=2026-09-25'):
        r=c.get(url);assert r.status_code==503 and r.json()['error']['code']=='stale_quote'
    assert vertical(c).status_code==503
    explicit=c.post('/v1/trade/research',json=manual())
    assert explicit.status_code==200
    assert explicit.json()['meta']['current_spot']==100
    assert explicit.json()['meta']['research_close']!=100
    assert not explicit.json()['meta']['quote_freshness']['usable_for_live_research']


def test_closed_quote_context_available_live_scan_blocked(env):
    c,p,s,clock=env;clock.value=dt('2026-09-24T00:30:00Z')
    p.quote.return_value[0]['updated_at']='2026-09-23T19:59:59Z'
    r=c.get('/v1/market/SPY');assert r.status_code==200,r.text
    assert r.json()['meta']['current_spot'] is None
    assert r.json()['meta']['quote_freshness']['data_status']=='latest_available'
    assert c.get('/v1/options/SPY/scan?expiration=2026-09-25').json()['error']['code']=='market_closed_quote'
    assert vertical(c).json()['error']['code']=='market_closed_quote'


def test_streamlit_cache_rechecks_shared_freshness(monkeypatch):
    from modules import public_data
    quote=q();quote['retrieved_at']='2026-09-25T14:00:00Z'
    monkeypatch.setattr(public_data,'_cached_public_quotes',lambda symbols:[quote])
    from modules import quote_freshness
    actual=quote_freshness.freshness
    monkeypatch.setattr(quote_freshness,'freshness',lambda value:actual(value,dt('2026-09-25T14:00:10Z')))
    assert public_data.get_public_quotes(('QQQ',))[0]['freshness']['data_status']=='fresh'
    monkeypatch.setattr(quote_freshness,'freshness',lambda value:actual(value,dt('2026-09-25T14:03:00Z')))
    assert public_data.get_public_quotes(('QQQ',))[0]['freshness']['data_status']=='stale'


@pytest.mark.parametrize('state',['closed','stale'])
def test_strategy_selector_stops_before_candidate_generation(monkeypatch,state):
    from streamlit.testing.v1 import AppTest
    from modules import premium_workspace, public_data
    monkeypatch.setattr(premium_workspace.st,'page_link',Mock())
    original=require_research_quote
    when=dt('2026-09-26T14:00:00Z' if state=='closed' else '2026-09-28T14:00:00Z')
    monkeypatch.setattr(premium_workspace,'require_research_quote',lambda quote,**kw:original(quote,when,**kw))
    monkeypatch.setattr(public_data,'get_public_quotes',lambda symbols:[dict(q('2026-09-25T19:59:55Z'),symbol='SPY')])
    generator=Mock();monkeypatch.setattr(premium_workspace,'generate',generator)
    app=AppTest.from_string('from modules.premium_workspace import render; render()',default_timeout=60).run()
    next(r for r in app.radio if r.label=='Market data').set_value('Public · connected quotes').run()
    next(b for b in app.button if b.label=='Find premium trades →').click().run()
    assert not app.exception
    assert any('not usable for new live research' in w.value for w in app.warning)
    generator.assert_not_called()
    assert 'premium_result' not in app.session_state


def test_saved_trade_research_explicitly_non_live(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from test_selector_quant_workflow import selected_state
    from modules import phase6_workspace
    actual=freshness
    monkeypatch.setattr(phase6_workspace,'freshness',lambda quote:actual(quote,dt('2026-09-28T14:00:00Z')))
    state,_,_=selected_state()
    app=AppTest.from_string('from modules.phase6_workspace import render_phase6; render_phase6()',default_timeout=60)
    for k,v in state.items():app.session_state[k]=v
    app.run()
    assert not app.exception
    assert any('non-live historical scenario research' in w.value for w in app.warning)
    assert any('not a verified live price' in c.value for c in app.caption)
    assert any(b.label=='Run integrated trade research' for b in app.button)
