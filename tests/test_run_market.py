import pandas as pd
import json
from copy import deepcopy
import pytest

from modules.run_market import run_market
from tests.test_market_archive_adapter import payload


def history():
    days = pd.bdate_range("2029-09-01", "2030-01-01")
    return pd.DataFrame(dict(
        date=days, symbol="QQQ",
        open=range(100,100+len(days)), close=range(100,100+len(days)),
        high=range(101,101+len(days)), low=range(99,99+len(days)),
    ))


def test_run_qqq_archive_to_research_session_is_read_only_and_unranked():
    source = payload()
    source['slot_time'] = '2030-01-02T20:25:00Z'
    source['collection_finished_at'] = '2030-01-02T20:31:00Z'
    before = deepcopy(source)
    result = run_market(
        source, expiration="2030-01-02", history=history(),
        session_context={"open":"2030-01-02T14:30:00Z","close":"2030-01-02T21:00:00Z"},
        available_capital=150,
    )
    assert result["command"] == "Run QQQ"
    assert result["read_only"] is True
    assert result["status"] == "complete"
    session = result["research_session"]
    assert session["opportunity_state"]["direction"] == "bullish"
    assert session["opportunity_state"]["time_state"] == "late_0dte"
    assert session["candidates"]
    assert result['symbol'] == 'QQQ'
    assert result['archive']['session_date'] == source['session']
    assert result['archive']['observation']['slot_time'] == source['slot_time']
    assert result['archive']['observation']['observed_at'] == source['observed_at']
    assert result['archive']['observation']['collection_finished_at'] == source['collection_finished_at']
    assert all(x['research']['capital_at_risk'] <= 150 for x in session['candidates'])
    assert any(x['reason'] == 'exceeds_available_capital' for x in session['excluded'])
    assert session['opportunity_state']['premium_state'] == 'unknown'
    assert session['opportunity_state']['volatility_state'] == 'unknown'
    assert session['opportunity_state']['classifier_version'] == 'opportunity-classifier-v1'
    assert source == before
    json.dumps(result, allow_nan=False)
    assert session["comparison"]["winner"] is None
    assert session["comparison"]["recommendation"] is None


def test_run_without_history_does_not_invent_direction():
    result = run_market(
        payload(), expiration="2030-01-02",
        session_context={"open":"2030-01-02T14:30:00Z","close":"2030-01-02T21:00:00Z"},
    )
    state = result["research_session"]["opportunity_state"]
    assert state["direction"] == "unknown"
    assert state["premium_state"] == "unknown"
    assert state["volatility_state"] == "unknown"


def test_calendar_default_and_conflicting_supplied_context():
    assert run_market(payload())['research_session']['opportunity_state']['time_state'] == 'late_0dte'
    with pytest.raises(ValueError, match='calendar'):
        run_market(payload(), session_context={'open': '2030-01-02T13:00:00Z', 'close': '2030-01-02T22:00:00Z'})


def test_questionable_warnings_reach_research_positions():
    p = payload()
    row = p['options']['valid_contracts'].pop(0)
    row['quality_warnings'] = ['open_interest_missing']
    p['options']['questionable_contracts'] = [row]
    result = run_market(p, history=history())
    legs = [leg for candidate in result['research_session']['candidates']
            for leg in candidate['research']['position']['legs'] if leg['contract'] == row['contract']]
    assert legs
    assert all(leg['quality_warnings'] == ['open_interest_missing'] for leg in legs)


def test_actual_collector_payload_reaches_run_market_without_provider_reads():
    from datetime import datetime
    from modules.intraday_archive import collect_symbol
    class Provider:
        name = 'Public'
        def now(self): return datetime.fromisoformat('2030-01-02T20:30:00+00:00')
        def underlying(self, symbol):
            return dict(instrument=dict(symbol=symbol, type='EQUITY'), outcome='SUCCESS', last=500)
        def expirations(self, symbol): return ['2030-01-02']
        def chain(self, symbol, expiration):
            def option(strike, bid, delta):
                return dict(instrument=dict(symbol=f'QQQ300102C{strike*1000:08d}', type='OPTION'),
                            outcome='SUCCESS', bid=bid, ask=bid+.2,
                            optionDetails=dict(strikePrice=strike, greeks=dict(delta=delta)))
            return dict(calls=[option(500, 2, .5), option(505, .8, .2)], puts=[])
    archive = collect_symbol(Provider(), 'QQQ', dict(min_dte=0, max_dte=7, strike_band=.05))
    result = run_market(archive, history=history(), available_capital=150)
    assert result['status'] == 'complete'
    assert result['read_only'] is True
    assert result['archive']['observation']['provenance'] == archive['options']['provenance']
    assert result['research_session']['comparison']['winner'] is None
    json.dumps(result, allow_nan=False)


def test_archive_early_close_uses_shared_nyse_calendar():
    p = payload()
    old = '2030-01-02'
    new = '2026-11-27'
    p = json.loads(json.dumps(p).replace(old, new).replace('20:30:00', '17:30:00'))
    result = run_market(p)
    state = result['research_session']['opportunity_state']
    assert state['time_state'] == 'late_0dte'
    assert state['evidence']['time_state']['observations']['session']['close'] == '2026-11-27T18:00:00+00:00'


def test_after_close_archive_is_not_intraday_research():
    p = payload()
    p['observed_at'] = '2030-01-02T22:00:00+00:00'
    with pytest.raises(ValueError, match='outside'):
        run_market(p)
