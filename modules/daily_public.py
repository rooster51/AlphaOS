"""Read-only Public provider for scheduled research; no Streamlit or orders."""
import os
import sys
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timezone
from modules.public_history import fetch_research_bars
from modules.public_session import _select_account


class ProviderUnavailable(RuntimeError):
    """Messages are fixed public diagnostics, never interpolated SDK errors."""


_attempt = ContextVar('intraday_provider_attempt', default=None)
_operations = {'quotes': 'underlying_quote', 'option-expirations': 'expiration_discovery',
               'option-chain': 'option_chain'}


@contextmanager
def intraday_provider_attempt(attempt):
    token = _attempt.set(attempt if type(attempt) is int and attempt in (1, 2) else None)
    try:
        yield
    finally:
        _attempt.reset(token)


class _InvalidResponse(ValueError):
    pass


def _failure_category(exc):
    from requests import exceptions as requests_errors
    from public_api_sdk.exceptions import APIError

    status = None
    if isinstance(exc, APIError):
        status = exc.status_code
    elif isinstance(exc, requests_errors.HTTPError) and exc.response is not None:
        status = exc.response.status_code
    status = status if type(status) is int and 400 <= status <= 599 else None
    if status == 429:
        return 'rate_limit', status, True
    if status == 408 or isinstance(exc, (TimeoutError, requests_errors.Timeout)):
        return 'timeout', status, True
    if status is not None:
        return ('provider_server_error', status, True) if status >= 500 else ('provider_rejection', status, False)
    if isinstance(exc, (_InvalidResponse, requests_errors.InvalidJSONError)):
        return 'invalid_response', None, False
    if isinstance(exc, (requests_errors.SSLError, requests_errors.ProxyError)):
        return 'transport_failure', None, False
    if isinstance(exc, (ConnectionError, requests_errors.ConnectionError, requests_errors.ChunkedEncodingError)):
        return 'transport_failure', None, True
    return 'unknown_failure', None, False


def _report_failure(endpoint, body, phase, started, exc):
    attempt = _attempt.get()
    if attempt is None:
        return
    instrument = body['instruments'][0] if endpoint == 'quotes' else body['instrument']
    symbol = instrument.get('symbol')
    symbol = symbol if symbol in ('SPY', 'QQQ') else 'other'
    expiry = body.get('expirationDate')
    try:
        parsed = date.fromisoformat(expiry).isoformat() if isinstance(expiry, str) else None
        expiry = parsed if parsed == expiry else None
    except ValueError:
        expiry = None
    category, status, retryable = _failure_category(exc)
    elapsed = round((time.monotonic() - started) * 1000)
    print(f'public_request_failed provider=Public symbol={symbol} endpoint={endpoint} operation={_operations[endpoint]} '
          f'expiration={expiry or "none"} collection_attempt={attempt} elapsed_ms={elapsed} phase={phase} '
          f'category={category} http_status={status or "none"} retryable={str(retryable).lower()}', file=sys.stderr)


class DailyPublicProvider:
    name = 'Public'

    def __init__(self, client, account_id):
        self.client, self.account_id = client, account_id

    @classmethod
    def from_environment(cls):
        secret = os.environ.get('PUBLIC_API_SECRET')
        if not secret:
            raise ProviderUnavailable('PUBLIC_API_SECRET is not configured.')
        try:
            from public_api_sdk import ApiKeyAuthConfig, PublicApiClient
            client = PublicApiClient(ApiKeyAuthConfig(api_secret_key=secret,validity_minutes=60))
            accounts = client.get_accounts().accounts
            if not accounts:
                raise ValueError
            account = _select_account(accounts,os.environ.get('PUBLIC_ACCOUNT_NUMBER'))
            return cls(client,account.account_id)
        except Exception:
            raise ProviderUnavailable('Public authentication/account selection failed. Check repository secrets and market-data access.') from None

    def history(self, symbol, period, as_of):
        return fetch_research_bars(self.client,symbol,period,as_of=as_of)

    def _marketdata(self, endpoint, body, validate):
        # Keep the SDK's transport and retry policy. Time the logical call,
        # including any SDK retries, without exposing its exception contents.
        started = time.monotonic()
        phase = 'auth_refresh'
        try:
            self.client.auth_manager.refresh_token_if_needed()
            phase = 'provider_request'
            data = self.client.api_client.post(
                f'/userapigateway/marketdata/{self.account_id}/{endpoint}',json_data=body)
            phase = 'response_validation'
            if not isinstance(data, dict) or not validate(data):
                raise _InvalidResponse
            return data
        except Exception as exc:
            _report_failure(endpoint, body, phase, started, exc)
            raise ProviderUnavailable('Public market-data retrieval failed.') from None

    def underlying(self, symbol):
        def valid(raw):
            quotes = raw.get('quotes')
            return isinstance(quotes, list) and len(quotes) == 1 and isinstance(quotes[0], dict)
        raw = self._marketdata('quotes', {'instruments': [{'symbol': symbol, 'type': 'EQUITY'}]}, valid)
        return raw['quotes'][0]

    def expirations(self, symbol):
        raw = self._marketdata('option-expirations', {'instrument': {'symbol': symbol, 'type': 'EQUITY'}},
            lambda data: data.get('baseSymbol') == symbol and isinstance(data.get('expirations'), list))
        return raw['expirations']

    def chain(self, symbol, expiration):
        raw = self._marketdata('option-chain', {'instrument': {'symbol': symbol, 'type': 'EQUITY'},
            'expirationDate': expiration}, lambda data: data.get('baseSymbol') == symbol and
            all(isinstance(data.get(k), list) for k in ('calls', 'puts')))
        return {'calls':raw['calls'],'puts':raw['puts']}

    @staticmethod
    def now():
        return datetime.now(timezone.utc)
