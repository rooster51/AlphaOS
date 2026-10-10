"""Real REST/MCP boundaries, fixture storage, no secrets or production requests."""
from copy import deepcopy
from datetime import datetime
from functools import partial
import gzip
import hashlib
import importlib
import json
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from alphaos_api.mcp_server import build_mcp
from alphaos_api.research2 import ArchiveResearchService, MarketRequest
from modules.supabase_archive import read_latest_option_snapshot
from modules.position_research import research_position
from tests.test_archive_read_path import ReadOnlyClient, AS_OF
from tests.test_run_market import history
from test_mcp_api import login, call, rpc

api = importlib.import_module('alphaos_api.app')


@pytest.fixture
def boundary(monkeypatch):
    monkeypatch.setenv('ALPHAOS_API_TOKEN', 'owner-test-secret')
    storage = ReadOnlyClient()
    loader = Mock(side_effect=lambda symbol: history().assign(symbol=symbol))
    service = ArchiveResearchService(
        read_snapshot=partial(read_latest_option_snapshot, storage, max_age_seconds=300),
        history_loader=loader, clock=lambda: datetime.fromisoformat(AS_OF))
    monkeypatch.setattr(api.app.state, 'archive_research', service)
    app = FastAPI()
    app.include_router(api.router)
    app.exception_handlers.update(api.app.exception_handlers)
    app.middleware('http')(api.safe_boundary)
    build_mcp(app, api.sanitized)
    with TestClient(app, base_url='https://alphaos.onrender.com', follow_redirects=False) as client:
        yield client, storage, service, loader


def post(client, path, data):
    return client.post('/v1/research/'+path, json=data,
                       headers={'Authorization': 'Bearer owner-test-secret'})


def repack(storage):
    storage.raw = gzip.compress(json.dumps(storage.payload).encode(), mtime=0)
    storage.row['archive_sha256'] = hashlib.sha256(storage.raw).hexdigest()


@pytest.mark.parametrize('symbol', ['QQQ', 'SPY'])
def test_market_end_to_end_rest_and_oauth_mcp(boundary, symbol):
    client, storage, service, loader = boundary
    if symbol == 'SPY':
        storage.payload = json.loads(json.dumps(storage.payload).replace('QQQ', 'SPY'))
        storage.row['symbol'] = symbol
        storage.row['archive_path'] = storage.row['archive_path'].replace('QQQ', 'SPY')
        repack(storage)
    before = deepcopy(storage.payload)
    request = dict(symbol=symbol, available_capital=150, objective='bullish research', expiration='2030-01-02')
    response = post(client, 'market', request)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['read_only'] and data['research']['read_only']
    research = data['research']; session = research['research_session']
    assert session['opportunity_state']['classifier_version'] == 'opportunity-classifier-v1'
    assert session['opportunity_state']['direction'] == 'bullish'
    assert session['opportunity_state']['time_state'] == 'late_0dte'
    assert session['opportunity_state']['premium_state'] == 'unknown'
    assert session['opportunity_state']['volatility_state'] == 'unknown'
    assert session['strategy_routes']['routes'] and session['candidates']
    assert all(x['research']['capital_at_risk'] <= 150 for x in session['candidates'])
    assert any(x['reason'] == 'exceeds_available_capital' for x in session['excluded'])
    assert session['comparison']['winner'] is None and session['comparison']['recommendation'] is None
    assert research['archive']['storage']['archive_sha256'] == storage.row['archive_sha256']
    assert research['archive']['observation']['slot_time'] == storage.payload['slot_time']
    assert research['as_of'] == storage.payload['observed_at'] != research['requested_as_of']
    assert all(x['research']['dte'] == 0 for x in session['candidates'])
    assert all('pop' not in x['research'] for x in session['candidates'])
    assert storage.payload == before
    json.dumps(data, allow_nan=False)
    _, tokens = login(client)
    result = call(client, tokens['access_token'], 'run_market', request)
    assert not result.get('isError'), result
    assert result['structuredContent'] == data


def test_unknown_history_and_thesis_do_not_invent_evidence(boundary):
    c, _, service, loader = boundary
    loader.side_effect = RuntimeError('sensitive provider failure')
    data = post(c, 'market', dict(symbol='QQQ', objective='bullish')).json()
    state = data['research']['research_session']['opportunity_state']
    assert state['direction'] == state['premium_state'] == state['volatility_state'] == 'unknown'
    assert 'sensitive' not in json.dumps(data)


@pytest.mark.parametrize('defect', ['checksum','identity','stale','missing','future','path'])
def test_bad_archive_fails_closed_without_history_fallback(boundary, defect):
    c, storage, service, loader = boundary
    if defect == 'checksum': storage.row['archive_sha256'] = 'bad'
    elif defect == 'identity': storage.payload['symbol'] = 'SPY'; repack(storage)
    elif defect == 'stale': service.clock = lambda: datetime.fromisoformat('2030-01-02T21:00:00+00:00')
    elif defect == 'future': storage.row['created_at'] = '2030-01-03T00:00:00Z'
    elif defect == 'path': storage.row['archive_path'] = 'wrong/path'
    else: storage.row = None
    r = post(c, 'market', dict(symbol='QQQ'))
    assert r.status_code == 503 and r.json()['error']['code'] == 'archive_unavailable'
    loader.assert_not_called()


def test_partial_archive_and_rejected_evidence_remain_visible(boundary):
    c, storage, _, _ = boundary
    options = storage.payload['options']
    options['status'] = storage.row['quality_status'] = 'partial'
    row = options['valid_contracts'].pop()
    row['rejection_reasons'] = ['crossed_market']
    options['rejected_contracts'].append(row)
    options['expiration_failures'] = [dict(expiration='2030-01-02', error='provider_unavailable')]
    repack(storage)
    data = post(c, 'market', dict(symbol='QQQ')).json()['research']
    assert data['archive']['excluded']
    assert not data['research_session']['candidates']
    assert data['archive']['storage']['quality_status'] == 'partial'


def structure(**updates):
    return dict(symbol='QQQ', expiration='2030-01-02', as_of='2030-01-02', spot=500,
        credit=-1.2, legs=[dict(type='Call',strike=500,qty=1),dict(type='Call',strike=505,qty=-1)], **updates)


def test_explicit_structure_and_ordered_comparison_delegate(boundary):
    c, storage, service, loader = boundary
    first = structure()
    second = {**first, 'credit': -2.2, 'legs': first['legs'][:1]}
    response = post(c, 'structure', first)
    assert response.status_code == 200, response.text
    expected = research_position(dict(first, shares=0), symbol='QQQ',spot=500,as_of='2030-01-02')
    actual = response.json()['research']['payoff']
    assert {k:v for k,v in actual.items() if k != 'trade'} == {k:v for k,v in expected['payoff'].items() if k != 'trade'}
    assert actual['trade']['source'] == 'Explicit user-supplied scenario'
    compared = post(c, 'structures/compare', dict(structures=[first,second])).json()
    comparison = compared['research']['comparison']
    assert [r['strategy_family'] for r in comparison['candidates']] == ['call_debit_spread','long_call']
    assert comparison['winner'] is comparison['recommendation'] is None
    assert compared['research']['candidates'][1]['max_profit'] == 'unlimited'
    assert not storage.calls
    loader.assert_not_called()
    _, tokens = login(c)
    for name, args, expected_result in [('research_structure',dict(structure=first),response.json()),
            ('compare_structures',dict(comparison=dict(structures=[first,second])),compared)]:
        result = call(c, tokens['access_token'], name, args)
        assert not result.get('isError'), result
        assert result['structuredContent'] == expected_result


@pytest.mark.parametrize('invalid_input', [dict(symbol='SPX'),dict(symbol='QQQ',available_capital=-1),
    dict(symbol='QQQ',width=0),dict(symbol='QQQ',expiration='Friday'),dict(symbol='QQQ',payload={})])
def test_input_validation(boundary, invalid_input):
    c, storage, _, _ = boundary
    assert post(c, 'market', invalid_input).status_code == 422
    assert not storage.calls


def test_authentication_and_no_mutation_tools(boundary):
    c, storage, _, _ = boundary
    assert c.post('/v1/research/market',json=dict(symbol='QQQ')).status_code == 401
    _, tokens = login(c)
    tools = rpc(c,tokens['access_token'],'tools/list').json()['result']['tools']
    assert all(t['annotations']['readOnlyHint'] for t in tools)
    assert not {'record_position','close_position','get_trade_journal'} & {t['name'] for t in tools}
    assert not storage.calls


def test_missing_expiration_is_not_substituted(boundary):
    c, _, _, _ = boundary
    r = post(c, 'market', dict(symbol='QQQ',expiration='2030-01-04'))
    assert r.status_code == 422


def test_default_production_wiring_uses_existing_reader(boundary, monkeypatch):
    _, storage, _, _ = boundary
    import alphaos_api.research2 as module
    monkeypatch.setattr(module, 'archive_client', lambda: storage)
    monkeypatch.setenv('ALPHAOS_ARCHIVE_MAX_AGE_SECONDS','300')
    service = ArchiveResearchService(history_loader=lambda symbol: history(),
        clock=lambda: datetime.fromisoformat(AS_OF))
    assert service.run(MarketRequest(symbol='QQQ'))['research']['symbol'] == 'QQQ'
    monkeypatch.setenv('ALPHAOS_ARCHIVE_MAX_AGE_SECONDS','nan')
    from alphaos_api.contracts import APIError
    with pytest.raises(APIError):
        service.run(MarketRequest(symbol='QQQ'))


def test_orchestration_parameters_and_zero_time_constructor_preserved(boundary, monkeypatch):
    import alphaos_api.research2 as interface
    import modules.opportunity_session as session
    c, _, _, _ = boundary
    run = Mock(wraps=interface.run_latest_market)
    generate = Mock(wraps=session.generate)
    monkeypatch.setattr(interface, 'run_latest_market', run)
    monkeypatch.setattr(session, 'generate', generate)
    response = post(c, 'market', dict(symbol='QQQ',expiration='2030-01-02',available_capital=300,objective='bearish'))
    assert response.status_code == 200
    assert run.call_args.kwargs['expiration'] == '2030-01-02'
    assert run.call_args.kwargs['available_capital'] == 300
    assert run.call_args.kwargs['objective'] == 'bearish'
    assert response.json()['research']['research_session']['opportunity_state']['direction'] == 'bullish'
    assert generate.call_args.args[2] == 0
    assert generate.call_args.kwargs['min_net_credit'] == 0
    import inspect
    assert inspect.signature(generate._mock_wraps).parameters['min_net_credit'].default == 50


@pytest.mark.parametrize('change', [dict(legs=[]),dict(credit=10),dict(as_of='2030-01-03'),
    dict(legs=[dict(type='Call',strike=500,qty=0)]),dict(legs=[dict(type='Call',strike=500,qty=-1)])])
def test_invalid_structure_is_rejected_without_data_access(boundary, change):
    c, storage, _, loader = boundary
    assert post(c, 'structure', {**structure(), **change}).status_code == 422
    assert not storage.calls
    loader.assert_not_called()


@pytest.mark.parametrize('variable', ['SUPABASE_SERVICE_ROLE_KEY', 'SUPABASE_URL'])
def test_new_secret_values_are_redacted_at_boundary(boundary, monkeypatch, variable):
    c, _, _, _ = boundary
    sentinel = 'private-test-value'
    monkeypatch.setenv(variable, sentinel)
    request = dict(symbol='QQQ', objective=sentinel)
    r = post(c, 'market', request)
    assert r.status_code == 200
    assert sentinel not in r.text
    _, tokens = login(c)
    result = call(c, tokens['access_token'], 'run_market', request)
    assert not result.get('isError'), result
    assert sentinel not in json.dumps(result)


def test_questionable_quote_warnings_cross_boundary(boundary):
    c, storage, _, _ = boundary
    row = storage.payload['options']['valid_contracts'].pop(0)
    row['quality_warnings'] = ['open_interest_missing']
    storage.payload['options']['questionable_contracts'].append(row)
    repack(storage)
    data = post(c,'market',dict(symbol='QQQ')).json()['research']
    legs = [leg for candidate in data['research_session']['candidates']
            for leg in candidate['research']['position']['legs'] if leg['contract'] == row['contract']]
    assert legs and all('open_interest_missing' in leg['quality_warnings'] for leg in legs)


@pytest.mark.parametrize('symbol', ['SPY', 'QQQ'])
def test_market_http_contract_is_authenticated_post_json(boundary, symbol):
    """Protect the browser bridge from assuming a GET market endpoint."""
    client, storage, _, _ = boundary
    path = '/v1/research/market'
    assert client.get(path, params={'symbol': symbol},
                      headers={'Authorization': 'Bearer owner-test-secret'}).status_code == 404
    # Missing credentials are 401; a supplied but invalid bearer token is
    # deliberately rejected as 403 by alphaos_api.app.authenticate.
    missing = client.post(path, json={'symbol': symbol})
    assert missing.status_code == 401
    assert missing.json()['error']['code'] == 'authentication_required'
    invalid = client.post(path, json={'symbol': symbol},
                          headers={'Authorization': 'Bearer invalid'})
    assert invalid.status_code == 403
    assert invalid.json()['error']['code'] == 'forbidden'


def test_market_research_preserves_non_executable_status(boundary):
    client, _, _, _ = boundary
    response = post(client, 'market', {'symbol': 'QQQ'})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['read_only'] is True
    session = data['research']['research_session']
    assert session['comparison']['winner'] is None
    assert session['comparison']['recommendation'] is None
    for candidate in session['candidates']:
        research = candidate['research']
        assert 'pop' not in research
