"""Release 1 no-candidate diagnosis; synthetic prices are not staging evidence."""
import json
import pytest
from modules.opportunity_router import opportunity_state, route_strategies
from modules.opportunity_session import research_market_opportunities
from modules.public_provider import PublicProviderError
from tests.test_research2_api import boundary, post


def session(symbol, capital, width, *, known=True, delta=True):
    expiration = '2026-10-30'
    calls = [dict(type='Call', strike=strike, bid=mid-.05, ask=mid+.05,
        delta=d if delta else None) for strike,mid,d in [(500,3,.5),(501,2.5,.4),(502,2,.3)]]
    return research_market_opportunities(symbol,
        dict(spot=500, opportunity_state=dict(direction='bullish' if known else 'unknown', time_state='standard'),
             classification_evidence={} if known else dict(unavailable='Completed history unavailable.')),
        dict(symbol=symbol, expiration=expiration, calls=calls, puts=[]),
        as_of='2026-10-13T15:00:00Z', available_capital=capital, width=width)


@pytest.mark.parametrize('symbol,capital,width', [('QQQ',20,1),('SPY',150,1),('QQQ',300,1),('QQQ',300,2)])
def test_missing_history_does_not_misreport_structural_or_capital_failure(symbol, capital, width):
    result = session(symbol, capital, width, known=False)
    d = result['diagnostics']
    accepted = int(capital >= (50 if width == 1 else 100))
    assert result['status'] == ('complete' if accepted else 'no_candidate')
    assert d['route_count'] == 0
    count = 2 if width == 1 else 1
    assert d['generated_count'] == count
    assert d['accepted_count'] == accepted * count
    assert d['capital_rejection_count'] == (1 - accepted) * count
    assert d['classification_limitations'] == ['no_evidence_supported_routes']
    assert d['zero_candidate_reason'] == (None if accepted else 'all_structures_exceed_capital')
    assert not result['opportunity_state']['evidence_sufficiency']['sufficient_for_routing']


@pytest.mark.parametrize('symbol,capital,width,accepted,risk', [('QQQ',20,1,0,50),('SPY',150,1,1,50),('QQQ',300,1,1,50),('QQQ',300,2,1,100)])
def test_observed_evidence_then_capital_has_distinct_counts(symbol, capital, width, accepted, risk):
    result = session(symbol, capital, width)
    d = result['diagnostics']
    count = 2 if width == 1 else 1
    assert d['generated_count'] == count
    assert d['accepted_count'] == accepted * count
    assert d['capital_rejection_count'] == (1-accepted) * count
    selected = result['candidates'][0]['research'] if accepted else result['excluded'][0]['research']
    assert selected['capital_at_risk'] == risk
    assert result['comparison']['winner'] is None


def test_missing_delta_explains_constructor_failure_without_imputation():
    d = session('QQQ',300,1,delta=False)['diagnostics']
    assert d['generated_count'] == d['capital_rejection_count'] == 0
    assert d['construction'][0]['reason'] == 'insufficient_observed_delta_contracts'
    assert d['construction'][0]['delta_eligible_contract_count'] == 0


@pytest.mark.parametrize('state', [opportunity_state(), opportunity_state(time_state='standard')])
def test_standard_time_alone_is_not_routing_evidence(state):
    assert not state['evidence_sufficiency']['sufficient_for_routing']
    assert route_strategies(state)['routes'] == []


def test_api_expiration_is_specific_and_never_substituted(boundary):
    client, _, _, _ = boundary
    # Use an unarchived future expiry for this 2030 fixture, rather than an expired one.
    response = post(client,'market',dict(symbol='QQQ', expiration='2030-01-30', available_capital=20, width=1))
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'archive_expiration_unavailable'


@pytest.mark.parametrize('error,reason', [
    (PublicProviderError('public_not_configured'),'public_not_configured'),
    (PublicProviderError('public_authentication_failure'),'public_authentication_failure'),
    (PublicProviderError('private-secret-value'),'completed_history_unavailable'),
    (RuntimeError('private-secret-value'),'completed_history_unavailable')])
def test_history_error_is_allowlisted_and_secret_safe(boundary,error,reason):
    client, _, _, loader = boundary
    loader.side_effect = error
    response = post(client,'market',dict(symbol='QQQ'))
    assert response.status_code == 200
    d = response.json()['research']['research_session']['diagnostics']
    assert d['history_loading'] == dict(status='unavailable',reason=reason)
    assert 'private-secret-value' not in json.dumps(response.json())


@pytest.mark.parametrize('stage,status,reason', [
    ('provider_request', 401, 'public_authentication_failure'),
    ('provider_request', 429, 'public_rate_limit'),
    ('provider_request', 400, 'public_history_request_failed'),
    ('provider_schema', None, 'public_history_schema_or_empty'),
    ('normalization', None, 'public_history_schema_or_empty'),
    ('ohlc_validation', None, 'public_history_validation_failed'),
    ('coverage_validation', None, 'public_history_validation_failed'),
    ('unknown_private_stage', None, 'completed_history_unavailable'),
])
def test_history_stage_diagnostics_are_safe(boundary, stage, status, reason):
    from modules.history_diagnostics import HistoryError
    client, _, _, loader = boundary
    loader.side_effect = HistoryError('private-secret-value', {
        'symbol': 'QQQ', 'requested_period': 'FIVE_YEARS',
        'stage': stage, 'http_status': status,
        'provider_reason_terms': ['private-secret-value'],
    })
    response = post(client, 'market', dict(symbol='QQQ'))
    assert response.status_code == 200
    diagnostics = response.json()['research']['research_session']['diagnostics']
    assert diagnostics['history_loading'] == dict(status='unavailable', reason=reason)
    assert 'private-secret-value' not in json.dumps(response.json())
