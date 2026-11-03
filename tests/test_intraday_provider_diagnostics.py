"""Synthetic Public failures: verify diagnostics without provider credentials."""
from unittest.mock import Mock

import pytest
from public_api_sdk.exceptions import APIError, RateLimitError
from requests.exceptions import ConnectionError, ReadTimeout

from modules.daily_public import DailyPublicProvider, ProviderUnavailable, intraday_provider_attempt

SECRET = 'PRIVATE_SENTINEL'


@pytest.mark.parametrize('error,category,status,retryable', [
    (ReadTimeout(SECRET), 'timeout', 'none', 'true'),
    (RateLimitError(SECRET, response_data={'secret': SECRET}), 'rate_limit', '429', 'true'),
    (APIError(SECRET, 403), 'provider_rejection', '403', 'false'),
    (APIError(SECRET, 503), 'provider_server_error', '503', 'true'),
    (ConnectionError(SECRET), 'transport_failure', 'none', 'true'),
    (ValueError(SECRET), 'unknown_failure', 'none', 'false'),
])
def test_request_failure_categories_and_redaction(error, category, status, retryable, capsys):
    client = Mock()
    client.api_client.post.side_effect = error
    provider = DailyPublicProvider(client, SECRET)
    with intraday_provider_attempt(2), pytest.raises(ProviderUnavailable) as caught:
        provider.chain('SPY', '2026-11-06')
    log = capsys.readouterr().err
    assert 'symbol=SPY endpoint=option-chain operation=option_chain expiration=2026-11-06' in log
    assert 'collection_attempt=2 elapsed_ms=' in log
    assert f'phase=provider_request category={category} http_status={status} retryable={retryable}' in log
    assert SECRET not in log and SECRET not in str(caught.value)
    assert client.api_client.post.call_count == 1


@pytest.mark.parametrize('operation,endpoint', [('underlying','quotes'), ('expirations','option-expirations'), ('chain','option-chain')])
def test_invalid_envelope_identifies_operation(operation, endpoint, capsys):
    client = Mock()
    client.api_client.post.return_value = {'raw_content': SECRET}
    provider = DailyPublicProvider(client, SECRET)
    with intraday_provider_attempt(1), pytest.raises(ProviderUnavailable):
        getattr(provider, operation)('SPY', *(['2026-11-06'] if operation == 'chain' else []))
    log = capsys.readouterr().err
    assert f'endpoint={endpoint}' in log
    assert 'phase=response_validation category=invalid_response' in log
    assert SECRET not in log


def test_refresh_failure_not_misattributed_to_provider_request(capsys):
    client = Mock()
    client.auth_manager.refresh_token_if_needed.side_effect = APIError(SECRET, 401)
    provider = DailyPublicProvider(client, SECRET)
    with intraday_provider_attempt(1), pytest.raises(ProviderUnavailable):
        provider.underlying('SPY')
    assert 'phase=auth_refresh category=provider_rejection http_status=401' in capsys.readouterr().err
    client.api_client.post.assert_not_called()


def test_attempt_scope_and_untrusted_parameters_do_not_leak(capsys):
    client = Mock()
    client.api_client.post.side_effect = ReadTimeout(SECRET)
    provider = DailyPublicProvider(client, SECRET)
    with intraday_provider_attempt(2), pytest.raises(ProviderUnavailable):
        provider.chain(SECRET, '2026-11-06\n'+SECRET)
    log = capsys.readouterr().err
    assert 'symbol=other' in log and 'expiration=none' in log and SECRET not in log
    with pytest.raises(ProviderUnavailable):
        provider.expirations('QQQ')
    assert capsys.readouterr().err == ''


@pytest.mark.parametrize('failed_endpoint', ['option-expirations', 'option-chain'])
def test_spy_failure_logs_bounded_attempts_and_qqq_still_archives(monkeypatch, capsys, failed_endpoint):
    from datetime import datetime, timezone
    from scripts import run_intraday_snapshot as runner
    now = datetime(2026, 11, 3, 18, 50, tzinfo=timezone.utc)
    client = Mock()
    def post(path, json_data):
        endpoint = path.rsplit('/', 1)[-1]
        if endpoint == 'quotes':
            instrument = json_data['instruments'][0]
            return dict(quotes=[dict(instrument=instrument, outcome='SUCCESS', last=600)])
        symbol = json_data['instrument']['symbol']
        if symbol == 'SPY' and endpoint == failed_endpoint:
            raise APIError(SECRET, 403)
        if endpoint == 'option-expirations':
            return dict(baseSymbol=symbol, expirations=['2026-11-06'])
        return dict(baseSymbol=symbol, calls=[dict(instrument=dict(symbol='QQQ261106C00600000', type='OPTION'),
            optionDetails=dict(strikePrice=600), outcome='SUCCESS')], puts=[])
    client.api_client.post.side_effect = post
    provider = DailyPublicProvider(client, SECRET)
    monkeypatch.setattr(provider, 'now', lambda: now)
    monkeypatch.setattr(runner.DailyPublicProvider, 'from_environment', lambda: provider)
    monkeypatch.setattr(runner, 'archive_client', object)
    monkeypatch.setattr(runner, 'find_slot_snapshot', lambda *args: None)
    monkeypatch.setattr(runner, 'fetch_intraday_bars', lambda *args: [])
    monkeypatch.setattr(runner, 'persist_candles', lambda *args: 0)
    writes = []
    def persist(db, payload, config):
        writes.append((payload['symbol'], payload['options']['status']))
        return dict(quality_status=payload['options']['status'], observed_at=payload['observed_at'])
    monkeypatch.setattr(runner, 'persist_option_snapshot', persist)
    sleeps = []
    assert runner.main(clock=lambda: now, sleep=sleeps.append) == 1
    logs = capsys.readouterr()
    if failed_endpoint == 'option-expirations':
        assert writes == [('QQQ', 'complete')] and sleeps == [10]
        assert logs.err.count('operation=expiration_discovery') == 2
        assert 'collection_attempt=2' in logs.err
    else:
        assert writes == [('SPY', 'partial'), ('QQQ', 'complete')] and sleeps == []
        assert 'operation=option_chain expiration=2026-11-06' in logs.err
        assert 'failed_expirations=1' in logs.err
        assert 'collection_attempt=2' not in logs.err
    assert 'collection_attempt=1' in logs.err
    assert SECRET not in logs.err and 'archived QQQ' in logs.out
