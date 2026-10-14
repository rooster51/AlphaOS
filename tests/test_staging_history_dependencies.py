"""Real history-loader wiring with synthetic transport; never live credentials."""
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

from alphaos_api.research2 import ArchiveResearchService
from modules.public_provider import PublicProviderError, authenticated_context
from modules.history_diagnostics import HistoryError
from tests.test_public_history import response, client_for
from tests.test_research2_api import boundary, post


@pytest.mark.parametrize('symbol', ['SPY', 'QQQ'])
def test_missing_public_secret_fails_before_any_provider_transport(monkeypatch, symbol):
    monkeypatch.delenv('PUBLIC_API_SECRET', raising=False)
    monkeypatch.delenv('PUBLIC_ACCOUNT_NUMBER', raising=False)
    authenticated_context.cache_clear()
    constructor = Mock(side_effect=AssertionError('Provider transport must not be reached'))
    monkeypatch.setattr('public_api_sdk.PublicApiClient', constructor)
    with pytest.raises(PublicProviderError) as caught:
        ArchiveResearchService._history(symbol)
    assert caught.value.code == 'public_not_configured'
    constructor.assert_not_called()


def test_real_missing_configuration_reason_survives_research_api(boundary, monkeypatch):
    client, _, service, _ = boundary
    monkeypatch.delenv('PUBLIC_API_SECRET', raising=False)
    monkeypatch.delenv('PUBLIC_ACCOUNT_NUMBER', raising=False)
    authenticated_context.cache_clear()
    service.history_loader = ArchiveResearchService._history
    result = post(client, 'market', dict(symbol='QQQ')).json()
    diagnostics = result['research']['research_session']['diagnostics']
    assert diagnostics['history_loading'] == dict(status='unavailable', reason='public_not_configured')
    # Unknown evidence remains unknown; a user objective cannot replace it.
    assert result['research']['research_session']['opportunity_state']['direction'] == 'unknown'


@pytest.mark.parametrize('symbol', ['SPY', 'QQQ'])
def test_existing_five_year_schema_through_actual_service_loader(monkeypatch, symbol):
    today = pd.Timestamp.now(tz='America/New_York').normalize().tz_localize(None)
    raw = response(symbol, 'FIVE_YEARS', (today-pd.DateOffset(years=5)).date().isoformat(), today.date().isoformat())
    provider = client_for(raw)
    monkeypatch.setattr('modules.public_provider._public_context', lambda: (provider, 'fixture-account'))
    frame = ArchiveResearchService._history(symbol)
    provider.api_client.get.assert_called_once_with(
        f'/userapigateway/historicdata/EQUITY/{symbol}/FIVE_YEARS/ONE_DAY', params=None)
    provider.auth_manager.refresh_token_if_needed.assert_called_once()
    assert list(frame.columns) == ['date','open','high','low','close','volume','symbol']
    assert set(frame.symbol) == {symbol}
    assert len(frame) > 1200
    assert frame.attrs['provider_diagnostics']['stage'] == 'validated'
    assert frame.close.iloc[0] == 101


def test_invalid_provider_schema_is_not_repaired(monkeypatch):
    raw = response('QQQ', 'FIVE_YEARS')
    raw['regularMarket']['bars'][0]['close'] = 'private-provider-payload'
    monkeypatch.setattr('modules.public_provider._public_context', lambda: (client_for(raw), 'fixture-account'))
    with pytest.raises(HistoryError) as caught:
        ArchiveResearchService._history('QQQ')
    assert caught.value.diagnostics['stage'] == 'provider_schema'
    assert 'private-provider-payload' not in str(caught.value.diagnostics)


def test_staging_blueprint_declares_dependencies_without_values():
    blueprint = (Path(__file__).resolve().parents[1]/'render.staging.yaml').read_text()
    for key in ('PUBLIC_API_SECRET','PUBLIC_ACCOUNT_NUMBER','SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','ALPHAOS_API_TOKEN'):
        assert f'- key: {key}\n        sync: false' in blueprint
    assert 'branch: web/research-api-integration' in blueprint


@pytest.mark.parametrize('canonical', [False, True])
def test_linux_case_sensitive_configuration_contract(monkeypatch, canonical):
    # Windows normalizes environment-key case; model Linux's exact-key mapping.
    from modules import public_provider
    environment = {'Public_API_Secret': 'synthetic-wrong-case',
                   'PUBLIC_ACCOUNT_NUMBER': 'synthetic-account'}
    if canonical:
        environment['PUBLIC_API_SECRET'] = 'synthetic-canonical'
    monkeypatch.setattr(public_provider.os, 'environ', environment)
    secret, account = public_provider.configuration()
    assert account == 'synthetic-account'
    assert secret == ('synthetic-canonical' if canonical else None)
    if not canonical:
        public_provider.authenticated_context.cache_clear()
        with pytest.raises(PublicProviderError) as caught:
            public_provider.authenticated_context(secret, account)
        assert caught.value.code == 'public_not_configured'
