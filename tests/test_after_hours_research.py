"""Explicit historical mode reuses verified storage and the REST/OAuth MCP engine."""
from copy import deepcopy
from datetime import datetime
import pytest

from tests.test_research2_api import boundary, post, repack
from tests.test_website_mcp_parity import prepare_storage
from test_mcp_api import login, call


@pytest.mark.parametrize('symbol', ['SPY', 'QQQ'])
def test_modes_reuse_identical_research_at_the_original_observation(boundary, symbol):
    client, storage, _, _ = boundary
    prepare_storage(storage, symbol)
    current = post(client, 'market', dict(symbol=symbol, available_capital=150)).json()
    historical = post(client, 'market', dict(symbol=symbol, available_capital=150, research_mode='historical')).json()
    expected = deepcopy(current)
    expected['request']['research_mode'] = 'historical'
    expected['research']['research_mode'] = 'historical'
    expected['research']['archive']['freshness']['max_age_seconds'] = None
    expected['caveats'].append('Historical archive research at the observation timestamp; candidates are not current trading opportunities or executable quotes.')
    assert historical == expected


def test_production_reader_wiring_keeps_600_second_current_limit(boundary, monkeypatch):
    import alphaos_api.research2 as interface
    client, storage, service, _ = boundary
    monkeypatch.setattr(interface, 'archive_client', lambda: storage)
    monkeypatch.delenv('ALPHAOS_ARCHIVE_MAX_AGE_SECONDS', raising=False)
    service.read_snapshot = service._read
    service.clock = lambda: datetime.fromisoformat('2030-01-02T22:00:00+00:00')
    assert post(client, 'market', dict(symbol='QQQ')).json()['error']['code'] == 'archive_stale'
    response = post(client, 'market', dict(symbol='QQQ', research_mode='historical'))
    assert response.status_code == 200
    assert response.json()['research']['archive']['freshness']['max_age_seconds'] is None


@pytest.mark.parametrize('value', [float('inf'), float('nan'), float('-inf')])
def test_nonfinite_buying_power_is_rejected(value):
    from alphaos_api.research2 import MarketRequest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        MarketRequest(symbol='QQQ', research_mode='historical', available_capital=value)


@pytest.mark.parametrize('symbol', ['SPY', 'QQQ'])
@pytest.mark.parametrize('at', [
    '2030-01-02T20:33:00+00:00',  # regular session
    '2030-01-02T22:00:00+00:00',  # after close
    '2030-01-05T17:00:00+00:00',  # Saturday, including expired structures
    '2030-01-21T17:00:00+00:00',  # NYSE holiday (MLK Day)
])
def test_historical_rest_mcp_capital_and_observation_parity(boundary, symbol, at):
    client, storage, service, _ = boundary
    prepare_storage(storage, symbol)
    service.clock = lambda: datetime.fromisoformat(at)
    _, tokens = login(client)
    for capital in (150, 500):
        request = dict(symbol=symbol, research_mode='historical',
                       available_capital=capital, expiration='2030-01-02')
        response = post(client, 'market', request)
        assert response.status_code == 200, response.text
        data = response.json()
        research = data['research']; session = research['research_session']
        assert data['read_only'] and research['read_only']
        assert data['request']['research_mode'] == research['research_mode'] == 'historical'
        assert research['as_of'] == storage.payload['observed_at']
        assert research['requested_as_of'] == at
        assert research['expiration'] == session['expiration'] == '2030-01-02'
        assert research['archive']['provider'] == 'Public'
        assert research['archive']['storage']['archive_sha256'] == storage.row['archive_sha256']
        freshness = research['archive']['freshness']
        assert freshness['max_age_seconds'] is None
        assert freshness['age_seconds'] == (datetime.fromisoformat(at) -
            datetime.fromisoformat(research['as_of'])).total_seconds()
        assert 'not current trading opportunities or executable quotes' in ' '.join(data['caveats'])
        assert session['available_capital'] == capital
        assert session['candidates']
        assert all(item['research']['capital_at_risk'] <= capital for item in session['candidates'])
        assert all(item['research']['historical_economics']['eligible_for_consideration'] is False
                   for item in session['candidates'])
        if capital == 150:
            assert any(item['reason'] == 'exceeds_available_capital' for item in session['excluded'])
        result = call(client, tokens['access_token'], 'run_market', request)
        assert not result.get('isError'), result
        assert result['structuredContent'] == data


@pytest.mark.parametrize('symbol', ['SPY', 'QQQ'])
@pytest.mark.parametrize('at, status', [
    ('2030-01-02T20:33:00+00:00', 200),
    ('2030-01-02T20:50:00+00:00', 503),  # stale while still open
    ('2030-01-02T22:00:00+00:00', 503),
    ('2030-01-05T17:00:00+00:00', 503),
    ('2030-01-21T17:00:00+00:00', 503),
])
def test_current_keeps_strict_freshness_without_automatic_fallback(boundary, symbol, at, status):
    client, storage, service, loader = boundary
    prepare_storage(storage, symbol)
    service.clock = lambda: datetime.fromisoformat(at)
    response = post(client, 'market', dict(symbol=symbol, available_capital=150))
    assert response.status_code == status
    if status == 503:
        assert response.json()['error']['code'] == 'archive_stale'
        loader.assert_not_called()
    else:
        assert response.json()['research']['research_mode'] == 'current'


@pytest.mark.parametrize('mode', ['current', 'historical'])
@pytest.mark.parametrize('defect', ['missing', 'checksum', 'identity', 'path', 'future', 'finish', 'quality', 'corrupt'])
def test_historical_does_not_bypass_integrity(boundary, mode, defect):
    client, storage, _, loader = boundary
    if defect == 'missing': storage.row = None
    elif defect == 'checksum': storage.row['archive_sha256'] = 'bad'
    elif defect == 'identity': storage.payload['symbol'] = 'SPY'; repack(storage)
    elif defect == 'path': storage.row['archive_path'] = 'invalid/path'
    elif defect == 'future': storage.row['created_at'] = '2030-01-03T00:00:00Z'
    elif defect == 'finish': storage.payload['collection_finished_at'] = '2030-01-03T00:00:00Z'; repack(storage)
    elif defect == 'quality': storage.row['quality_status'] = 'partial'
    else:
        import hashlib
        storage.raw = b'not a gzip archive'
        storage.row['archive_sha256'] = hashlib.sha256(storage.raw).hexdigest()
    response = post(client, 'market', dict(symbol='QQQ', research_mode=mode))
    assert response.status_code == 503
    assert response.json()['error']['code'] == ('archive_missing' if defect == 'missing' else 'archive_unavailable')
    loader.assert_not_called()


@pytest.mark.parametrize('capital', [0, -1, '150', '', True])
def test_invalid_capital_rejected_by_rest_and_mcp(boundary, capital):
    client, storage, _, loader = boundary
    request = dict(symbol='SPY', research_mode='historical', available_capital=capital)
    assert post(client, 'market', request).status_code == 422
    _, tokens = login(client)
    result = call(client, tokens['access_token'], 'run_market', request)
    assert result.get('isError') or 'error' in result
    assert not storage.calls
    loader.assert_not_called()


@pytest.mark.parametrize('mode', ['current', 'historical'])
def test_invalid_expiration_never_substituted(boundary, mode):
    client, _, _, _ = boundary
    request = dict(symbol='QQQ', research_mode=mode, expiration='2030-01-10')
    response = post(client, 'market', request)
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'archive_expiration_unavailable'
    _, tokens = login(client)
    result = call(client, tokens['access_token'], 'run_market', request)
    assert result['structuredContent']['error']['code'] == 'archive_expiration_unavailable'
