"""Synthetic observations only; no claims about production fills or latency."""
from copy import deepcopy
from datetime import datetime

import pytest

from modules.width_discovery import discover_widths
from modules.opportunity_session import research_market_opportunities
from modules.position_research import research_position
from tests.test_research2_api import boundary, post, repack
from tests.test_website_mcp_parity import prepare_storage
from test_mcp_api import login, call

FAMILIES = ['call_debit_spread', 'put_debit_spread', 'put_credit_spread',
            'call_credit_spread', 'iron_condor', 'butterfly', 'bullish_bwb', 'bearish_bwb']


def chain(symbol='SPY', expiration='2030-01-03'):
    result = dict(symbol=symbol, expiration=expiration, calls=[], puts=[])
    for kind, pool in [('Call', 'calls'), ('Put', 'puts')]:
        for strike in [94, 96, 97.5, 98, 99, 100, 101, 102, 102.5, 104, 106]:
            mid = 4 + (100 - strike if kind == 'Call' else strike - 100) * .5
            result[pool].append(dict(type=kind, strike=strike, bid=mid-.01, ask=mid+.01,
                delta=.5 if kind == 'Call' else -.5, contract=f'{symbol}-{expiration}-{kind}-{strike}',
                quote_timestamp='2030-01-02T20:30:00Z', volume=10, open_interest=100))
    return result


@pytest.mark.parametrize('symbol', ['SPY', 'QQQ'])
@pytest.mark.parametrize('expiry', ['2030-01-02', '2030-01-03', '2030-01-18', '2031-01-17'])
@pytest.mark.parametrize('family', FAMILIES)
def test_multiple_observed_widths_and_shared_economics(symbol, expiry, family):
    source = chain(symbol, expiry); before = deepcopy(source)
    rows, reports = discover_widths(source, 100, {family})
    assert rows and not reports[0]['search_truncated']
    widths = set()
    valid = []
    for row in rows:
        for leg in row['legs']:
            assert any(all(leg[k] == observed[k] for k in observed)
                       for observed in source['calls' if leg['type'] == 'Call' else 'puts'])
        try:
            research = research_position(row, symbol=symbol, spot=100, as_of='2030-01-02')
        except ValueError:
            continue  # Exact payoff engine still rejects impossible packages.
        assert research['strategy_family'] == family
        assert research['max_loss'] == research['capital_at_risk'] > 0
        assert research['max_profit'] > 0 and research['breakevens']
        assert 'pop' not in research['payoff']
        valid.append(research)
        widths.update(abs(a['strike']-b['strike']) for a in row['legs'] for b in row['legs'] if a['type']==b['type'])
    assert valid and len(widths - {0}) > 1
    assert source == before


@pytest.mark.parametrize('family', FAMILIES)
def test_manual_exact_geometry_no_nearest_substitution(family):
    source = chain()
    rows, _ = discover_widths(source, 100, {family}, width=1)
    assert rows
    for row in rows:
        for kind in ('Call', 'Put'):
            strikes = sorted(leg['strike'] for leg in row['legs'] if leg['type'] == kind)
            if not strikes:
                continue
            gaps = [b-a for a,b in zip(strikes, strikes[1:])]
            assert sorted(gaps) == ([1, 2] if family.endswith('bwb') else [1])
    absent, report = discover_widths(source, 100, {family}, width=1.1)
    assert absent == []
    assert report[0]['reason'] == 'no_structure_at_exact_requested_width'


def test_150_budget_computes_all_economics_before_filtering_and_keeps_multiple_widths():
    source = chain()
    def run(capital):
        return research_market_opportunities('SPY', {'spot':100, 'opportunity_state':{'direction':'bullish'}},
            source, as_of='2030-01-02', available_capital=capital)
    low, high = run(150), run(10000)
    assert low['candidates'] and low['diagnostics']['capital_rejection_count']
    assert low['diagnostics']['generated_count'] == high['diagnostics']['generated_count']
    widths = {abs(x['research']['position']['legs'][0]['strike'] - x['research']['position']['legs'][1]['strike']) for x in low['candidates']}
    assert .5 in widths and 2 in widths
    assert all(x['research']['max_loss'] <= 150 for x in low['candidates'])
    for row in low['excluded']:
        if row['reason'] == 'exceeds_available_capital':
            assert row['research']['max_profit'] > 0 and row['research']['breakevens']
            assert row['required_capital'] > 150


@pytest.mark.parametrize('family', FAMILIES)
def test_each_family_has_150_capital_eligibility_separate_from_evidence(family):
    direction = 'bearish' if family in ('put_debit_spread', 'call_credit_spread', 'bearish_bwb') else 'bullish'
    source = chain()
    if family == 'butterfly':
        for row in source['calls'] + source['puts']:
            row.update(bid=1.5 if row['strike'] == 100 else 1.3, ask=1.52 if row['strike'] == 100 else 1.4)
    result = research_market_opportunities('SPY', {'spot':100, 'opportunity_state':{
        'direction':direction, 'premium_state':'rich', 'movement_state':'range_bound'}},
        source, as_of='2030-01-02', available_capital=150)
    accepted = [r['research'] for r in result['candidates'] if r['strategy_family'] == family]
    rejected = [r['research'] for r in result['excluded'] if
        r['reason'] == 'exceeds_available_capital' and r['research']['strategy_family'] == family]
    assert accepted and rejected
    assert all(r['max_loss'] <= 150 and r['max_profit'] > 0 and r['breakevens'] for r in accepted)
    assert all(r['max_loss'] > 150 and r['max_profit'] > 0 and r['breakevens'] for r in rejected)


def test_bounds_are_deterministic_visible_and_independent_of_capital():
    source = chain()
    one = discover_widths(source, 100, {'call_debit_spread'}, max_attempts=2)
    assert one == discover_widths(source, 100, {'call_debit_spread'}, max_attempts=2)
    assert len(one[0]) == 2 and one[1][0]['search_truncated']
    assert discover_widths(source, 100, {'call_debit_spread'}, max_contracts_per_side=3)[1][0]['search_truncated']


def test_dense_unpriceable_condors_have_a_work_bound_and_not_a_capital_failure(monkeypatch):
    source = chain()
    for row in source['calls'] + source['puts']:
        row.update(bid=1, ask=1.1)
    rows, reports = discover_widths(source, 100, {'iron_condor'}, max_attempts=2)
    assert not rows
    assert reports[0]['attempted_count'] == 2 and reports[0]['search_truncated']
    assert reports[0]['rejection_counts'] == {'credit_does_not_cover_fees': 2}
    import modules.opportunity_session as session
    monkeypatch.setattr(session, 'discover_widths', lambda *args, **kwargs:
        discover_widths(*args, **kwargs, max_attempts=2))
    result = session.research_market_opportunities('SPY',
        {'spot':100, 'opportunity_state':{'movement_state':'range_bound'}}, source,
        as_of='2030-01-02', available_capital=150)
    assert result['diagnostics']['width_selection']['search_complete'] is False
    assert result['diagnostics']['zero_candidate_reason'] == 'bounded_search_incomplete'
    assert result['diagnostics']['capital_rejection_count'] == 0


@pytest.mark.parametrize('symbol', ['SPY', 'QQQ'])
@pytest.mark.parametrize('width', [None, 1, 5, 1.1])
def test_rest_oauth_mcp_width_semantics_and_verified_archive(boundary, symbol, width):
    client, storage, _, _ = boundary
    prepare_storage(storage, symbol)
    request = dict(symbol=symbol, available_capital=150, expiration='2030-01-03', width=width)
    response = post(client, 'market', request)
    assert response.status_code == 200
    result = response.json()
    selection = result['research']['research_session']['diagnostics']['width_selection']
    assert selection['mode'] == ('auto' if width is None else 'manual')
    assert selection['requested_width'] == width
    _, tokens = login(client)
    assert call(client,tokens['access_token'],'run_market',request)['structuredContent'] == result
    if width in (1, 1.1):
        assert not result['research']['research_session']['candidates']
        assert result['research']['research_session']['diagnostics']['capital_rejection_count'] == 0


@pytest.mark.parametrize('width', [None, 1])
@pytest.mark.parametrize('defect', ['stale', 'checksum', 'missing_quotes', 'duplicate', 'wide_quotes', 'missing_delta', 'rejected_stale_quotes'])
def test_width_never_bypasses_archive_or_quote_gates(boundary, width, defect):
    client, storage, service, _ = boundary
    if defect == 'stale':
        service.clock = lambda: datetime.fromisoformat('2030-01-02T21:00:00+00:00')
    elif defect == 'checksum':
        storage.row['archive_sha256'] = 'invalid'
    else:
        rows = storage.payload['options']['valid_contracts']
        if defect == 'rejected_stale_quotes':
            for row in rows:
                row.update(bid_timestamp='2029-12-31T20:00:00Z', ask_timestamp='2029-12-31T20:00:00Z', rejection_reasons=['stale_quote'])
            storage.payload['options']['rejected_contracts'] = rows
            storage.payload['options']['valid_contracts'] = []
        elif defect == 'duplicate': rows.extend(deepcopy(rows))
        else:
            for row in rows:
                if defect == 'missing_quotes': row['ask'] = None
                elif defect == 'wide_quotes': row.update(bid=.01, ask=100)
                else: row['delta'] = None
        repack(storage)
    response = post(client, 'market', dict(symbol='QQQ', width=width))
    if defect in ('stale', 'checksum'):
        assert response.status_code == 503
    elif response.status_code == 200:
        session = response.json()['research']['research_session']
        if defect == 'missing_delta':
            assert all(not row['strategy_family'].endswith('debit_spread') for row in session['candidates'])
        else:
            assert not session['candidates']
        assert session['diagnostics']['capital_rejection_count'] == 0
    else:
        assert response.status_code in (422, 503)
