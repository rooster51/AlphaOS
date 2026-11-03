"""Synthetic fixtures verify mechanics, never historical performance."""
from copy import deepcopy
from dataclasses import replace
import pytest
from modules.intraday_paper import Strategy, Policy, simulate, summarize

ENTRY = '2026-11-02T15:00:00+00:00'
CLOSE = '2026-11-02T20:55:00+00:00'


def leg(strike, qty, kind='Put'):
    return dict(contract=f"SPY261106{kind[0]}{strike*1000:08d}", type=kind, strike=strike, qty=qty)


def position(legs=None):
    return Strategy('SPY', 'credit_vertical', '2026-11-06', tuple(legs or [leg(600, -1), leg(599, 1)]))


def frame(at, legs=None, prices=None):
    legs = legs or position().legs
    prices = prices or [(1, 1.02), (.70, .72)]
    return dict(at=at, quotes=[dict(contract=l['contract'], bid=b, ask=a, bid_size=10, ask_size=10,
        bid_timestamp=at, ask_timestamp=at, observed_at=at, source='fixture', source_ref='fixture/1',
        quote_outcome='SUCCESS', evidence_kind='synthetic_option_quote') for l, (b, a) in zip(legs, prices)])


def run(frames=None, **kwargs):
    return simulate(position(), frames or [frame(ENTRY), frame(CLOSE)], mode='hypothetical_example', **kwargs)


def test_risk_fees_slippage_and_forced_close():
    r = run()
    assert r['status'] == 'closed'
    assert r['reason'] == 'mandatory_same_day_exit'
    assert r['entry']['cash'] == pytest.approx(26)
    assert r['maximum_loss'] == pytest.approx(78.6)
    assert r['net_pnl'] == pytest.approx(-10.6)
    assert r['exit']['slippage'] == 2
    assert r['marks'][0]['pnl'] == r['net_pnl']


@pytest.mark.parametrize('field,value,reason', [
    ('bid_timestamp', ENTRY, 'stale_future_or_wrong_session_quote'),
    ('ask_timestamp', None, 'Timestamp missing or invalid.'),
    ('source_ref', '', 'unverified_provenance'),
    ('ask_size', 0, 'insufficient_displayed_size'),
    ('ask', 2, 'unverified_liquidity'),
    ('bid', float('nan'), 'invalid_numeric_data'),
])
def test_partial_or_invalid_exit_never_fabricates_fill(field, value, reason):
    f = frame(CLOSE); f['quotes'][0][field] = value
    r = run([frame(ENTRY), f])
    assert r['status'] == 'no_trade' and r['net_pnl'] is None and r['exit'] is None
    assert r['marks'][0]['reason'] == reason
    assert summarize([r])[0]['unresolved_count'] == 1


def test_missing_entry_and_exit_legs():
    f = frame(ENTRY); f['quotes'].pop()
    assert run([f, frame(CLOSE)])['reason'] == 'missing_leg_quote'
    f = frame(CLOSE); f['quotes'].pop()
    assert run([frame(ENTRY), f])['reason'] == 'unfillable_same_day_exit'


def test_historical_refuses_synthetic_and_missing_quotes():
    assert simulate(position(), [frame(ENTRY), frame(CLOSE)], mode='historical_backtest')['reason'] == 'evidence_mode_mismatch'
    assert run([frame(ENTRY)])['net_pnl'] is None


@pytest.mark.parametrize('mode', ['historical_backtest', 'forward_paper'])
def test_observed_quote_modes_and_unresolved_exposure(mode):
    frames = [frame(ENTRY), frame(CLOSE)]
    for f in frames:
        for q in f['quotes']:
            q['evidence_kind'] = 'observed_option_quote'
    assert simulate(position(), frames, mode=mode)['status'] == 'closed'
    r = simulate(position(), frames[:1], mode=mode)
    assert r['status'] == ('unresolved_exposure' if mode == 'forward_paper' else 'no_trade')


@pytest.mark.parametrize('prices,reason', [([(1, 1.02), (.8, .82)], 'credit_economics_failed'),
                                        ([(1, 1.02), (.3, .32)], None)])
def test_credit_threshold(prices, reason):
    r = run([frame(ENTRY, prices=prices), frame(CLOSE, prices=prices)])
    assert r['reason'] == (reason or 'mandatory_same_day_exit')


def test_fees_can_disqualify_and_capital_is_enforced():
    assert run(policy=Policy(fee_per_contract=3))['reason'] == 'credit_economics_failed'
    assert run(policy=Policy(capital=50))['reason'] == 'unbounded_or_insufficient_capital'


@pytest.mark.parametrize('prices,reason', [([(.7, .72), (.7, .72)], 'profit_target'),
                                        ([(1.3, 1.32), (.7, .72)], 'stop_loss')])
def test_configurable_exits(prices, reason):
    r = run([frame(ENTRY), frame('2026-11-02T15:05:00+00:00', prices=prices)], policy=Policy(stop_loss=15))
    assert r['reason'] == reason


@pytest.mark.parametrize('legs,family,prices', [
    ([leg(600, 1, 'Call')], 'long_call', [(.2, .22)]),
    ([leg(599, 1), leg(600, -2), leg(601, 1)], 'butterfly', [(.5, .52), (.4, .42), (.5, .52)]),
    ([leg(599, 1), leg(600, -1), leg(605, -1, 'Call'), leg(606, 1, 'Call')], 'iron_condor',
     [(.5, .52), (.7, .72), (.7, .72), (.5, .52)]),
])
def test_common_multi_leg_interface(legs, family, prices):
    s = replace(position(legs), family=family)
    r = simulate(s, [frame(ENTRY, legs, prices), frame(CLOSE, legs, prices)], mode='scenario_analysis')
    assert r['status'] == 'closed'
    assert r['maximum_loss'] <= 100


def test_debit_limit_unbounded_identity_and_dte():
    s = position([leg(600, 1, 'Call')])
    r = simulate(s, [frame(ENTRY, s.legs, [(.5, .52)])], mode='hypothetical_example')
    assert r['reason'] == 'debit_economics_failed'
    s = position([leg(600, -1, 'Call')])
    assert simulate(s, [frame(ENTRY, s.legs, [(1, 1.02)])], mode='hypothetical_example')['reason'] == 'unbounded_or_insufficient_capital'
    assert simulate(replace(position(), expiration='2026-12-01'), [frame(ENTRY)], mode='hypothetical_example')['status'] == 'no_trade'
    s = position(); s.legs[0]['contract'] = 'wrong'
    assert simulate(s, [frame(ENTRY)], mode='hypothetical_example')['reason'] == 'contract_identity_mismatch'


def test_early_close_no_overnight_and_ordering():
    entry = '2026-11-27T15:00:00+00:00'
    close = '2026-11-27T17:55:00+00:00'
    legs = [dict(l, contract=l['contract'].replace('261106', '261127')) for l in position().legs]
    s = replace(position(legs), expiration='2026-11-27')
    r = simulate(s, [frame(entry, legs), frame(close, legs)], mode='hypothetical_example')
    assert r['status'] == 'closed' and r['close_deadline'].startswith('2026-11-27T17:55')
    assert run([frame(ENTRY), frame('2026-11-03T15:00:00+00:00')])['net_pnl'] is None
    assert run([frame(CLOSE), frame(ENTRY)])['reason'] == 'missing_or_unordered_frames'


def test_metrics_segmentation_empty_and_unresolved():
    a = run(); a['net_pnl'] = 20
    b = deepcopy(a); b['net_pnl'] = -10
    c = deepcopy(a); c['net_pnl'] = 0
    summary = summarize([a, b, c])[0]
    assert summary['net_pnl'] == 10 and summary['expectancy'] == pytest.approx(10/3)
    assert summary['win_rate'] == pytest.approx(1/3)
    assert summary['average_win'] == 20 and summary['average_loss'] == -10
    assert summary['profit_factor'] == 2 and summary['drawdown'] == 10
    other = deepcopy(a); other.update(mode='scenario_analysis', symbol='QQQ')
    assert len(summarize([a, other])) == 2
    assert summarize([run([frame(ENTRY)])])[0]['net_pnl'] is None
    assert summarize([]) == []


@pytest.mark.parametrize('kwargs', [dict(capital=float('nan')), dict(fee_per_contract=-1), dict(close_buffer_minutes=0)])
def test_invalid_policy(kwargs):
    with pytest.raises(ValueError): Policy(**kwargs)


def test_catalog_families_are_not_filtered_by_vertical_name():
    from modules.premium_engine import CATALOG
    for family in CATALOG:
        r = simulate(replace(position(), family=family), [frame(ENTRY), frame(CLOSE)], mode='hypothetical_example')
        assert r['status'] == 'closed' and r['strategy'] == family
    # Eligibility is based on actual risk/backing, never the supplied label.
    r = simulate(replace(position(), shares=100), [frame(ENTRY)], mode='hypothetical_example')
    assert r['reason'] == 'unsupported_symbol_or_stock_backing'


@pytest.mark.parametrize('field,value', [('bid_timestamp', '2026-11-02T15:00:01+00:00'),
                                       ('bid_size', None), ('quote_outcome', 'UNKNOWN'),
                                       ('rejection_reasons', ['invalid_contract_identifier'])])
def test_invalid_entry_evidence(field, value):
    f = frame(ENTRY); f['quotes'][0][field] = value
    r = run([f, frame(CLOSE)])
    assert r['status'] == 'no_trade' and r['entry'] is None and r['net_pnl'] is None


def test_break_even_and_no_loss_metrics_are_explicit():
    r = run(); r['net_pnl'] = 0
    s = summarize([r])[0]
    assert s['win_rate'] == 0 and s['profit_factor'] is None
    assert s['average_win'] is None and s['average_loss'] is None
