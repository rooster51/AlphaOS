import json
from copy import deepcopy
from datetime import date

import pytest

from modules.opportunity_session import research_market_opportunities
from modules.premium_engine import demo_chain
from modules.position_research import research_position


def run(direction='bullish', **kwargs):
    chain = demo_chain(30, as_of=date(2030, 1, 1))
    chain['symbol'] = 'QQQ'
    for row in chain['calls'] + chain['puts']:
        row['delta'] = max(.01, min(.99, .5 + (500-row['strike'])/400))
        if row['type'] == 'Put':
            row['delta'] -= 1
    market = dict(spot=500, support_resistance={'support': 490},
                  opportunity_state=dict(direction=direction, premium_state='rich', movement_state='breakout'))
    return research_market_opportunities('QQQ', kwargs.pop('market', market),
        kwargs.pop('chain', chain), as_of='2030-01-01T12:00:00Z', **kwargs)


def trade(legs, credit):
    return dict(symbol='QQQ', spot=500, expiration='2030-01-31', credit=credit,
                legs=[dict(type=k, strike=s, qty=q) for k, s, q in legs])


@pytest.mark.parametrize('direction,expected', [
    ('bullish', {'long_call', 'call_debit_spread', 'put_credit_spread', 'bullish_bwb'}),
    ('bearish', {'long_put', 'put_debit_spread', 'call_credit_spread', 'bearish_bwb'})])
def test_directional_session(direction, expected):
    result = run(direction)
    assert expected <= {r['strategy_family'] for r in result['candidates']}
    assert result['comparison']['winner'] is None
    assert result['comparison']['recommendation'] is None
    assert result['market']['support_resistance'] == {'support': 490}
    assert 'not a ranking' in result['candidate_order']
    json.dumps(result, allow_nan=False)


def test_capital_is_only_eligibility_and_preserves_input_order():
    supplied = [trade([('Call', 500, 1)], -2.5),
                trade([('Call', 500, 1), ('Call', 505, -1)], -1.5),
                trade([('Call', 505, 1)], -2)]
    before = deepcopy(supplied)
    result = run(candidates=supplied, available_capital=200)
    assert [x['input_index'] for x in result['candidates']] == [1, 2]
    assert [x['capital_at_risk'] for x in result['comparison']['candidates']] == [150, 200]
    excluded = result['excluded'][0]
    assert excluded['reason'] == 'exceeds_available_capital'
    assert excluded['research']['capital_at_risk'] == 250
    assert result['comparison']['winner'] is None
    assert supplied == before


def test_unknown_evidence_does_not_route():
    result = run(market={'spot': 500})
    assert result['candidates'] == []
    assert result['strategy_routes']['routes'] == []
    assert result['opportunity_state']['time_state'] == 'unknown'
    assert not result['opportunity_state']['evidence_sufficiency']['sufficient_for_routing']


def test_missing_greeks_iv_allows_quoted_research_but_not_delta_discovery():
    chain = demo_chain(30, as_of=date(2030, 1, 1))
    chain['symbol'] = 'QQQ'
    for row in chain['calls'] + chain['puts']:
        for key in ('delta', 'gamma', 'theta', 'vega', 'iv'):
            row.pop(key, None)
        row['quote_timestamp'] = '2030-01-01T11:59:00Z'
    result = run(chain=chain)
    families = {x['strategy_family'] for x in result['candidates']}
    assert {'long_call', 'put_credit_spread'} <= families
    assert 'call_debit_spread' not in families
    for x in result['candidates']:
        assert x['research']['position']['legs'][0]['iv'] is None
        assert x['research']['position']['legs'][0]['delta'] is None
        assert x['research']['position']['legs'][0]['quote_timestamp'] == '2030-01-01T11:59:00Z'
        assert x['research']['expected_move_context'] is None


@pytest.mark.parametrize('chain', [
    {'symbol': 'QQQ', 'expiration': '2030-01-31', 'calls': [None, {}, {'type': 'Call', 'strike': 500, 'bid': 3, 'ask': 2}], 'puts': 'bad'},
    {'symbol': 'QQQ', 'expiration': '2030-01-31'},
    {}, {'symbol': 'SPY', 'expiration': '2030-01-31'}])
def test_no_candidate_returns_payload(chain):
    result = run(chain=chain)
    assert result['status'] == 'no_candidate'
    assert result['candidates'] == []
    assert result['unavailable_routes']


@pytest.mark.parametrize('legs,credit,family,risk', [
    ([('Put', 490, 1), ('Put', 495, -1)], 1, 'put_credit_spread', 400),
    ([('Call', 505, -1), ('Call', 510, 1)], 1, 'call_credit_spread', 400),
    ([('Call', 495, 1), ('Call', 500, -2), ('Call', 505, 1)], -1, 'butterfly', 100),
    ([('Put', 480, 1), ('Put', 490, -2), ('Put', 495, 1)], 1, 'bullish_bwb', 400),
    ([('Call', 505, 1), ('Call', 510, -2), ('Call', 520, 1)], 1, 'bearish_bwb', 400),
    ([('Put', 490, 1), ('Put', 495, -1), ('Call', 505, -1), ('Call', 515, 1)], 2, 'iron_condor', 800)])
def test_shared_position_economics(legs, credit, family, risk):
    result = research_position(trade(legs, credit), symbol='QQQ', spot=500, as_of='2030-01-01')
    assert result['strategy_family'] == family
    assert result['capital_at_risk'] == risk
    assert all(x['expiration'] == '2030-01-31' for x in result['position']['legs'])
    assert result['payoff']['max_loss'] == risk


def test_range_routes_and_supplied_order():
    candidates = [trade([('Put', 490, 1), ('Put', 495, -1), ('Call', 505, -1), ('Call', 510, 1)], 2),
                  trade([('Call', 495, 1), ('Call', 500, -2), ('Call', 505, 1)], -1)]
    result = run(market={'spot': 500, 'opportunity_state': {'movement_state': 'range_bound'}}, candidates=candidates)
    assert [x['strategy_family'] for x in result['candidates']] == ['iron_condor', 'butterfly']
    assert any(x['route'] == 'calendar' for x in result['unavailable_routes'])


def test_bad_supplied_candidates_do_not_hide_valid():
    result = run(candidates=[None, {}, trade([('Call', 500, 1)], -1)])
    assert [x['input_index'] for x in result['candidates']] == [2]
    assert len(result['excluded']) == 2


def test_known_direction_does_not_infer_cheap_premium():
    result = run(market={'spot': 500, 'opportunity_state': {'direction': 'bullish'}})
    assert {x['strategy_family'] for x in result['candidates']} == {'call_debit_spread'}


def test_negative_capital_rejected():
    with pytest.raises(ValueError):
        run(available_capital=-1)


def test_duplicate_and_wrong_expiry_contracts_are_excluded():
    row = dict(type='Call', strike=500, bid=1, ask=1.1)
    chain = dict(symbol='QQQ', expiration='2030-01-31',
                 calls=[row, dict(row), dict(row, strike=505, expiration='2030-02-01')])
    result = run(chain=chain)
    assert not result['candidates']
    assert len(result['excluded']) == 3


def test_breakout_without_direction_does_not_choose_one():
    result = run(market={'spot': 500, 'opportunity_state': {'movement_state': 'breakout'}})
    assert not result['candidates']
    assert result['opportunity_state']['direction'] == 'unknown'
    assert all(r['reason'] == 'unsupported_or_requires_known_direction' for r in result['unavailable_routes'])


def test_expired_and_missing_spot_contexts_fail_closed():
    assert run(market={})['context_error'] == 'missing_or_invalid_spot'
    assert run(chain={'symbol': 'QQQ', 'expiration': '2029-01-01'})['context_error'] == 'expired_chain'


def test_zero_dte_constructs_premium_without_modeled_probability():
    chain = demo_chain(0, as_of=date(2030, 1, 1))
    chain['symbol'] = 'QQQ'
    result = run(chain=chain)
    premium = [x for x in result['candidates'] if x['strategy_family'] == 'put_credit_spread']
    assert premium
    assert all(x['research']['payoff']['pop'] is None for x in premium)
    assert not any('0DTE construction unavailable' in c for c in result['caveats'])
