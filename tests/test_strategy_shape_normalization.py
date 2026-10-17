"""Native pair inference uses supplied cashflows and the existing payoff engine."""
from copy import deepcopy

import pytest

from modules.options_payoff import trade_analysis
from modules.premium_engine import payoff
from modules.strategy_compare import compare_strategy_research, normalize_comparison_candidate


def candidate(put=100, call=100, qty=1):
    return dict(trade=dict(symbol='QQQ', expiration='2030-01-18', spot=100,
        credit=-3*qty, shares=0, fees=2*qty,
        legs=[dict(type='Put', strike=put, qty=qty), dict(type='Call', strike=call, qty=qty)]))


@pytest.mark.parametrize('put,call,family', [(100,100,'long_straddle'), (95,105,'long_strangle')])
@pytest.mark.parametrize('qty', [1,2])
@pytest.mark.parametrize('reverse', [False,True])
def test_long_pair_shape_and_existing_payoff(put, call, family, qty, reverse):
    item = candidate(put,call,qty)
    if reverse:
        item['trade']['legs'].reverse()
    before = deepcopy(item)
    result = normalize_comparison_candidate(item, 4)
    assert result['strategy_family'] == family
    assert result['input_index'] == 4
    assert result['max_loss'] == result['capital_at_risk'] == 302*qty
    assert result['max_profit'] == 'unlimited'
    assert result['breakevens'] == pytest.approx([put-3.02,call+3.02])
    analysis = trade_analysis(item['trade'])
    assert analysis['option_premium'] == -300*qty
    assert analysis['net_cash'] == -302*qty
    for price, expected in [(100,-302*qty), (put-10,698*qty), (call+10,698*qty)]:
        assert payoff(item['trade']['legs'], item['trade']['credit'], price, fees=2*qty) == pytest.approx(expected)
    assert result['market_evidence_available']['bid'] is False
    assert item == before


@pytest.mark.parametrize('change', [
    lambda t: t.update(credit=0), lambda t: t.update(credit=3),
    lambda t: t.pop('credit'), lambda t: t.update(credit=True),
    lambda t: t.update(shares=100), lambda t: t.update(fees=-1),
    lambda t: t.update(spot=float('nan')), lambda t: t.update(expiration='bad'),
    lambda t: t.update(symbol=''), lambda t: t.update(underlying='SPY'),
    lambda t: t['legs'][0].update(symbol='SPY'),
    lambda t: t['legs'][0].update(underlying='SPY'),
    lambda t: t['legs'][0].update(expiration='2030-01-19'),
    lambda t: t['legs'][0].update(qty=-1), lambda t: t['legs'][0].update(qty=2),
    lambda t: t['legs'][0].update(qty=.5), lambda t: t['legs'][0].update(qty=True),
    lambda t: t['legs'][0].update(strike=105), lambda t: t['legs'][0].update(strike=True),
    lambda t: t['legs'][0].update(strike=float('inf')),
    lambda t: t['legs'][0].update(type='Call'),
    lambda t: t['legs'][0].update(action='Sell'),
    lambda t: t['legs'][0].update(quantity=2),
    lambda t: t['legs'].append(dict(type='Call',strike=110,qty=1)),
    lambda t: t.update(legs=None), lambda t: t.update(legs=[None,None]),
])
def test_invalid_unlabeled_pair_excluded(change):
    item = candidate()
    change(item['trade'])
    result = compare_strategy_research([item])
    assert result['candidates'] == []
    assert result['excluded'] == [dict(input_index=0,reason='invalid_or_insufficient_research')]
    assert result['winner'] is result['recommendation'] is None


@pytest.mark.parametrize('location', ['item', 'trade_family', 'trade_strategy'])
def test_explicit_classification_and_economics_preserved(location):
    item = candidate()
    item.update(capital_at_risk=123,max_loss=123,max_profit=456,breakevens=[101])
    if location == 'item': item['strategy_family'] = 'existing_explicit_family'
    elif location == 'trade_family': item['trade']['strategy_family'] = 'existing_explicit_family'
    else: item['trade']['strategy'] = 'existing_explicit_family'
    r = normalize_comparison_candidate(item,0)
    assert r['strategy_family'] == 'existing_explicit_family'
    assert r['max_loss'] == 123
    assert r['max_profit'] == 456
    assert r['breakevens'] == [101]


def test_inferred_economics_ignore_stale_cached_values_and_keep_order():
    item = candidate()
    item.update(capital_at_risk=1,max_loss=1,max_profit=999,breakevens=[1])
    result = compare_strategy_research([{},item,candidate(95,105)])
    assert [r['input_index'] for r in result['candidates']] == [1,2]
    assert [r['strategy_family'] for r in result['candidates']] == ['long_straddle','long_strangle']
    assert result['candidates'][0]['max_loss'] == 302
    assert result['winner'] is result['recommendation'] is None
