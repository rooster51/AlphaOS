"""Explicit scenario contract audit; no new quotes, bars, provider or storage access.

Geometry/cashflows reuse the deterministic cases in test_structure_research and
its historical integration tests. These are supplied scenarios, not market data.
"""
from datetime import datetime

import pytest

from tests.test_research2_api import boundary, post
from tests.test_mcp_api import login, call

# Legs, signed cashflow, family, exact dollar profit/loss, expiration roots.
CASES = [
    ([('Call', 100, 1)], -2, 'long_call', 'unlimited', 200, [102]),
    ([('Put', 100, 1)], -2, 'long_put', 9800, 200, [98]),
    ([('Call', 100, 1), ('Call', 105, -1)], -2, 'call_debit_spread', 300, 200, [102]),
    ([('Put', 100, 1), ('Put', 95, -1)], -2, 'put_debit_spread', 300, 200, [98]),
    ([('Put', 95, 1), ('Put', 100, -1)], 2, 'put_credit_spread', 200, 300, [98]),
    ([('Call', 100, -1), ('Call', 105, 1)], 2, 'call_credit_spread', 200, 300, [102]),
    ([('Call', 95, 1), ('Call', 100, -2), ('Call', 105, 1)], -2, 'butterfly', 300, 200, [97, 103]),
    ([('Put', 95, 1), ('Put', 100, -2), ('Put', 105, 1)], -2, 'butterfly', 300, 200, [97, 103]),
    ([('Put', 90, 1), ('Put', 100, -2), ('Put', 105, 1)], 1, 'bullish_bwb', 600, 400, [94]),
    ([('Call', 95, 1), ('Call', 100, -2), ('Call', 110, 1)], 1, 'bearish_bwb', 600, 400, [106]),
    ([('Put', 90, 1), ('Put', 95, -1), ('Call', 105, -1), ('Call', 115, 1)], 2, 'iron_condor', 200, 800, [93, 107]),
    ([('Put', 95, 1), ('Put', 100, -1), ('Call', 100, -1), ('Call', 105, 1)], 2, 'butterfly', 200, 300, [98, 102]),
]


@pytest.mark.parametrize('symbol', ['SPY', 'QQQ'])
@pytest.mark.parametrize('expiration', ['2030-01-18', '2031-01-17'])
@pytest.mark.parametrize('legs,credit,family,profit,loss,roots', CASES)
def test_monthly_long_dated_explicit_contract_matrix(boundary, symbol, expiration,
                                                    legs, credit, family, profit, loss, roots):
    client, storage, service, loader = boundary
    service.clock = lambda: datetime.fromisoformat('2030-01-03T22:00:00+00:00')
    scenario = dict(symbol=symbol, expiration=expiration, as_of='2030-01-02',
                    spot=100, credit=credit, fees=0,
                    legs=[dict(type=t, strike=k, qty=q) for t, k, q in legs])
    response = post(client, 'structure', scenario)
    assert response.status_code == 200, response.text
    result = response.json()
    research = result['research']
    assert research['strategy_family'] == family
    assert research['trade']['expiration'] == research['position']['expiration'] == expiration
    assert research['max_profit'] == profit
    assert research['max_loss'] == research['capital_at_risk'] == loss
    assert research['payoff']['breakevens'] == roots
    assert result['provenance']['source'] == 'Explicit user-supplied scenario'
    historical = research['historical_economics']
    assert 'unsupported_expiration_session_horizon' in historical['missing_evidence']
    assert historical['historical_economics']['expected_value_dollars'] is None
    assert historical['eligible_for_consideration'] is False
    comparison_request = dict(structures=[scenario, scenario])
    compared = post(client, 'structures/compare', comparison_request)
    assert compared.status_code == 200
    compared_body = compared.json()
    assert [c['max_loss'] for c in compared_body['research']['candidates']] == [loss, loss]
    assert compared_body['research']['comparison']['winner'] is None
    _, tokens = login(client)
    for name, args, expected in [
        ('research_structure', dict(structure=scenario), result),
        ('compare_structures', dict(comparison=comparison_request), compared_body),
    ]:
        actual = call(client, tokens['access_token'], name, args)
        assert not actual.get('isError'), actual
        assert actual['structuredContent'] == expected
    assert not storage.calls
    loader.assert_not_called()


@pytest.mark.parametrize('symbol', ['SPY', 'QQQ'])
@pytest.mark.parametrize('expiration', ['2030-01-18', '2031-01-17'])
@pytest.mark.parametrize('legs,credit', [
    ([('Call', 100, 1), ('Put', 100, 1)], -4),  # straddle
    ([('Call', 105, 1), ('Put', 95, 1)], -4),   # strangle
    ([('Call', 100, -1)], 2),                 # naked short call
    ([('Put', 100, -1)], 2),                  # naked short put
])
def test_unimplemented_structures_fail_before_archive_or_history(boundary, symbol,
                                                                  expiration, legs, credit):
    client, storage, _, loader = boundary
    scenario = dict(symbol=symbol, expiration=expiration, as_of='2030-01-02',
                    spot=100, credit=credit,
                    legs=[dict(type=t, strike=k, qty=q) for t, k, q in legs])
    response = post(client, 'structure', scenario)
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'invalid_structure'
    assert not storage.calls
    loader.assert_not_called()
