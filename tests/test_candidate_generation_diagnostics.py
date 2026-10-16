"""Observed-style test quotes, not live observations: stage accounting and parity."""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import pandas as pd
import pytest

from tests.test_research2_api import boundary, post, repack
from tests.test_website_mcp_parity import prepare_storage
from tests.test_run_market import history
from test_mcp_api import login, call
from tests.test_website_mcp_parity import expected_fixture


def prepare(boundary, symbol, *, classified=False):
    client, storage, service, _ = boundary
    prepare_storage(storage, symbol)
    def dates(value):
        return json.loads(json.dumps(value).replace('2030-01-02','2026-10-16')
            .replace('2030-01-03','2026-10-19').replace('2030-01-04','2026-10-23')
            .replace('300102','261016').replace('300103','261019').replace('300104','261023')
            .replace('T20:', 'T19:'))
    storage.payload = dates(storage.payload)
    storage.row = dates(storage.row)
    bars = history()
    bars['date'] = pd.bdate_range(end='2026-10-15', periods=len(bars))
    bars['symbol'] = symbol
    if not classified:
        bars.loc[bars.index[-1], ['open','high','low','close']] = [175,176,174,175]
    service.history_loader = lambda symbol: bars.copy()
    service.clock = lambda: datetime.fromisoformat('2026-10-16T19:33:00+00:00')
    repack(storage)
    return client, storage, service


@pytest.mark.parametrize('case', json.loads((Path(__file__).parents[1] / 'web/tests/fixtures/candidate-diagnostics-parity.json').read_text()), ids=['SPY', 'QQQ'])
def test_exact_website_fixture_diagnostics_match_rest_and_oauth_mcp(boundary, case):
    client, storage, _ = prepare(boundary, case['request']['symbol'])
    response = post(client, 'market', case['request'])
    assert response.status_code == 200
    expected = deepcopy(case['response'])
    expected['research']['archive']['storage']['archive_sha256'] = storage.row['archive_sha256']
    assert response.json() == expected_fixture(expected)
    _, tokens = login(client)
    assert call(client, tokens['access_token'], 'run_market', case['request'])['structuredContent'] == response.json()


@pytest.mark.parametrize('symbol', ['SPY','QQQ'])
@pytest.mark.parametrize('mode', ['current','historical'])
def test_unknown_classification_is_not_a_quote_geometry_rejection(boundary, symbol, mode):
    client, storage, service = prepare(boundary, symbol)
    if mode == 'historical':
        service.clock = lambda: datetime.fromisoformat('2026-10-18T18:00:00+00:00')
    before = deepcopy(storage.payload)
    _, tokens = login(client)
    request = dict(symbol=symbol, expiration='2026-10-19', available_capital=1000, research_mode=mode)
    response = post(client, 'market', request)
    assert response.status_code == 200, response.text
    data = response.json(); session = data['research']['research_session']
    assert session['opportunity_state']['direction'] == 'unknown'
    assert session['opportunity_state']['premium_state'] == 'unknown'
    assert session['strategy_routes']['routes'] == []
    assert {item['strategy_family'] for item in session['candidates']} == {'call_debit_spread','put_debit_spread'}
    assert all(item['classification_supported'] is False for item in session['candidates'])
    assert all(item['generation_basis'] == 'unclassified_quote_research' for item in session['candidates'])
    assert all(item['research']['historical_economics']['eligible_for_consideration'] is False for item in session['candidates'])
    assert session['comparison']['winner'] is None and session['comparison']['recommendation'] is None
    assert session['diagnostics']['generated_count'] == 2
    stages = {item['stage']: item for item in session['diagnostics']['pipeline']}
    assert stages['archive_selection']['input_count'] == 12
    assert stages['archive_selection']['output_count'] == 4
    assert stages['archive_selection']['reason_counts']['different_expiration'] == 8
    assert stages['chain_validation']['output_count'] == 4
    assert stages['routing']['output_count'] == 0
    assert stages['construction']['output_count'] == stages['economics']['output_count'] == 2
    assert stages['capital_eligibility']['output_count'] == 2
    assert stages['historical_evidence']['output_count'] == 0
    assert stages['historical_evidence']['reason_counts']
    assert session['diagnostics']['zero_candidate_reason'] is None
    assert call(client, tokens['access_token'], 'run_market', request)['structuredContent'] == data
    assert storage.payload == before


@pytest.mark.parametrize('symbol', ['SPY','QQQ'])
def test_valid_completed_evidence_still_routes_a_supported_candidate(boundary, symbol):
    client, _, _ = prepare(boundary, symbol, classified=True)
    data = post(client, 'market', dict(symbol=symbol, expiration='2026-10-19', available_capital=1000)).json()
    session = data['research']['research_session']
    assert session['opportunity_state']['direction'] == 'bullish'
    assert session['strategy_routes']['routes'] == ['call_debit_spread']
    assert session['candidates']
    assert session['diagnostics']['generation_basis'] == 'evidence_routed'
    assert all(item['strategy_family'] == 'call_debit_spread' for item in session['candidates'])


@pytest.mark.parametrize('symbol', ['SPY','QQQ'])
@pytest.mark.parametrize('defect, reason', [
    ('missing_delta','insufficient_observed_delta_contracts'),
    ('bad_quotes','missing_valid_quotes'),
    ('no_protection','insufficient_observed_delta_contracts'),
    ('nonpositive_debit','nonpositive_debit'),
])
def test_honest_zero_and_unreached_stages(boundary, symbol, defect, reason):
    client, storage, _ = prepare(boundary, symbol)
    rows = storage.payload['options']['valid_contracts']
    if defect == 'no_protection':
        storage.payload['options']['valid_contracts'] = [row for row in rows if row['strike'] in (500,495)]
    else:
        for row in rows:
            if defect == 'missing_delta': row['delta'] = None
            elif defect == 'bad_quotes': row.update(bid=5, ask=1)
            else: row.update(bid=1, ask=1.2)
    repack(storage)
    response = post(client, 'market', dict(symbol=symbol, expiration='2026-10-19', available_capital=1000))
    assert response.status_code == 200
    session = response.json()['research']['research_session']
    assert session['candidates'] == []
    assert session['diagnostics']['generated_count'] == 0
    assert session['diagnostics']['zero_candidate_reason'] == 'no_constructible_structure'
    assert all(row['reason'] == reason for row in session['diagnostics']['construction'])
    stages = {item['stage']: item for item in session['diagnostics']['pipeline']}
    assert stages['economics']['status'] == stages['capital_eligibility']['status'] == 'not_attempted'
    if defect == 'bad_quotes':
        assert stages['chain_validation']['reason_counts']['invalid_bid_ask_or_strike'] == 4
    else:
        assert stages['chain_validation']['output_count'] > 0


@pytest.mark.parametrize('symbol', ['SPY','QQQ'])
def test_capital_is_after_generation_and_does_not_change_quotes(boundary, symbol):
    client, storage, _ = prepare(boundary, symbol)
    for row in storage.payload['options']['valid_contracts']:
        if row['type'] == 'call' and row['strike'] == 500:
            row.update(bid=3.2, ask=3.4)
    repack(storage)
    sessions = []
    for capital in (1,150,500,1000,5000):
        session = post(client, 'market', dict(symbol=symbol, expiration='2026-10-19', available_capital=capital)).json()['research']['research_session']
        assert session['diagnostics']['generated_count'] == 2
        assert all(item['research']['capital_at_risk'] <= capital for item in session['candidates'])
        sessions.append(session)
    assert sessions[0]['diagnostics']['zero_candidate_reason'] == 'all_structures_exceed_capital'
    assert [len(s['candidates']) for s in sessions] == [0,1,2,2,2]
    low_call = next(item['research'] for item in sessions[1]['excluded'] if item.get('research',{}).get('strategy_family') == 'call_debit_spread')
    high_call = next(item['research'] for item in sessions[2]['candidates'] if item['strategy_family'] == 'call_debit_spread')
    # Capital filtering does not alter payoff or quote evidence.
    assert low_call['trade'] == high_call['trade']
    assert low_call['max_loss'] == high_call['max_loss']


def test_optional_premium_counters_do_not_change_existing_constructor_output():
    from datetime import date
    from modules.premium_engine import demo_chain, generate
    chain = demo_chain(30, as_of=date(2030,1,1))
    report = {}
    expected = generate(chain,500,30/365,None,as_of=date(2030,1,1),min_net_credit=0)
    actual = generate(chain,500,30/365,None,as_of=date(2030,1,1),min_net_credit=0,diagnostics=report)
    assert actual == expected
    assert report
    assert all(row['attempted_count'] == row['generated_count'] + sum(row['rejection_counts'].values()) for row in report.values())
