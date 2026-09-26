"""Shared Public market-data adapter; no Streamlit imports or account responses."""
from __future__ import annotations
from typing import Any
from functools import lru_cache
import os
import pandas as pd
from datetime import datetime, timezone
from modules.quote_freshness import normalize_timestamp
from modules.public_session import _select_account

INDEX_SYMBOLS = {"SPX", "NDX", "RUT", "DJX", "VIX"}
SYMBOL_ALIASES = {"^SPX":"SPX","$SPX":"SPX","SPX.X":"SPX","^NDX":"NDX","$NDX":"NDX","^RUT":"RUT","$RUT":"RUT","^VIX":"VIX","$VIX":"VIX"}

class PublicProviderError(RuntimeError):
    def __init__(self,code='provider_unavailable'):
        self.code=code
        super().__init__('Public market data is unavailable.')


def provider_error(exc):
    if isinstance(exc,PublicProviderError): return exc
    status=getattr(exc,'status_code',None)
    if status is None: status=getattr(getattr(exc,'response',None),'status_code',None)
    if status is None: status=getattr(exc,'diagnostics',{}).get('http_status')
    return PublicProviderError('public_authentication_failure' if status in (401,403) else 'public_rate_limit' if status==429 else 'provider_unavailable')


def configuration(fallback=None):
    # Environment is authoritative; Streamlit fallback is supplied only by the UI.
    def value(name):
        if name in os.environ: return os.environ[name]
        try: return fallback.get(name) if fallback is not None else None
        except (FileNotFoundError,KeyError): return None
    return value('PUBLIC_API_SECRET'),value('PUBLIC_ACCOUNT_NUMBER')


@lru_cache(maxsize=2)
def authenticated_context(secret,preferred):
    if not secret: raise PublicProviderError('public_not_configured')
    try:
        from public_api_sdk import ApiKeyAuthConfig,PublicApiClient
        client=PublicApiClient(ApiKeyAuthConfig(api_secret_key=secret,validity_minutes=60))
        accounts=client.get_accounts().accounts
        if not accounts: raise PublicProviderError('public_authentication_failure')
        return client,_select_account(accounts,preferred).account_id
    except Exception as exc:
        raise provider_error(exc) from None


def _public_context():
    return authenticated_context(*configuration())

def _as_float(value: Any) -> float | None:
    return float(value) if value is not None else None

def _normalize_public_symbol(symbol: str) -> str:
    clean = symbol.strip().upper()
    return SYMBOL_ALIASES.get(clean, clean)

def _instrument_type_for_symbol(instrument_type: Any, symbol: str) -> Any:
    if _normalize_public_symbol(symbol) in INDEX_SYMBOLS:
        return getattr(instrument_type, 'INDEX', instrument_type.EQUITY)
    return instrument_type.EQUITY

def _order_instrument(order_instrument: Any, instrument_type: Any, symbol: str) -> Any:
    normalized = _normalize_public_symbol(symbol)
    return order_instrument(symbol=normalized, type=_instrument_type_for_symbol(instrument_type, normalized))

def get_public_quotes(symbols: tuple[str, ...], _context=None) -> list[dict]:
    from public_api_sdk import InstrumentType, OrderInstrument
    client, account_id = (_context or _public_context)()
    instruments = [_order_instrument(OrderInstrument, InstrumentType, symbol) for symbol in symbols]
    quotes = client.get_quotes(instruments, account_id=account_id)
    retrieved_at=datetime.now(timezone.utc).isoformat()
    return [{'symbol': quote.instrument.symbol, 'last': _as_float(quote.last), 'bid': _as_float(quote.bid), 'ask': _as_float(quote.ask), 'previous_close': _as_float(quote.previous_close), 'change': _as_float(quote.one_day_change.change if quote.one_day_change else None), 'change_pct': _as_float(quote.one_day_change.percent_change if quote.one_day_change else None), 'volume': quote.volume,
        'updated_at': normalize_timestamp(quote.last_timestamp), 'retrieved_at': retrieved_at,
        'provider_timestamp_field':'lastTimestamp',
        'provider_timestamp':str(quote.last_timestamp) if quote.last_timestamp is not None else None,
        'provider_timestamp_representation':'Public SDK datetime; original HTTP spelling not retained',
        'source':'Public'} for quote in quotes]

def get_public_price_history(symbol: str, _context=None) -> pd.DataFrame:
    from public_api_sdk import BarAggregation, BarPeriod
    client, _ = (_context or _public_context)()
    response = client.get_bars(_normalize_public_symbol(symbol), BarPeriod.QUARTER, aggregation=BarAggregation.ONE_DAY)
    return pd.DataFrame([{'date': pd.to_datetime(bar.timestamp), 'open': float(bar.open), 'high': float(bar.high), 'low': float(bar.low), 'close': float(bar.close), 'volume': float(bar.volume)} for bar in response.regular_market.bars])

def get_public_option_expirations(symbol: str, _context=None) -> list[str]:
    from public_api_sdk import InstrumentType, OptionExpirationsRequest, OrderInstrument
    client, account_id = (_context or _public_context)()
    response = client.get_option_expirations(OptionExpirationsRequest(instrument=_order_instrument(OrderInstrument, InstrumentType, symbol)), account_id=account_id)
    return sorted((str(expiration)[:10] for expiration in response.expirations))

def _option_quote_row(quote: Any, option_type: str) -> dict | None:
    details = quote.option_details
    if details is None or details.strike_price is None:
        return None
    greeks = details.greeks
    bid = _as_float(quote.bid)
    ask = _as_float(quote.ask)
    mid = _as_float(details.mid_price)
    if mid is None and bid is not None and (ask is not None):
        mid = (bid + ask) / 2
    return {'contract': quote.instrument.symbol, 'type': option_type, 'strike': _as_float(details.strike_price), 'bid': bid, 'ask': ask, 'mid': mid, 'delta': _as_float(greeks.delta if greeks else None), 'gamma': _as_float(greeks.gamma if greeks else None), 'theta': _as_float(greeks.theta if greeks else None), 'vega': _as_float(greeks.vega if greeks else None), 'rho': _as_float(greeks.rho if greeks else None), 'bid_timestamp': getattr(quote, 'bid_timestamp', None), 'ask_timestamp': getattr(quote, 'ask_timestamp', None), 'iv': _as_float(greeks.implied_volatility if greeks else None), 'volume': quote.volume, 'open_interest': getattr(quote, 'open_interest', None)}

def get_public_option_chain(symbol: str, expiration: str, _context=None) -> dict:
    from public_api_sdk import InstrumentType, OptionChainRequest, OrderInstrument
    client, account_id = (_context or _public_context)()
    response = client.get_option_chain(OptionChainRequest(instrument=_order_instrument(OrderInstrument, InstrumentType, symbol), expiration_date=expiration), account_id=account_id)
    calls = [row for quote in response.calls if (row := _option_quote_row(quote, 'Call')) is not None]
    puts = [row for quote in response.puts if (row := _option_quote_row(quote, 'Put')) is not None]
    return {'symbol': getattr(response, 'base_symbol', _normalize_public_symbol(symbol)), 'expiration': expiration, 'calls': calls, 'puts': puts}

def get_public_research_bars(symbol: str, period: str='FIVE_YEARS', option: bool=False, _context=None) -> pd.DataFrame:
    """Observed Public daily OHLC, with explicit long-history mapping and audit."""
    from public_api_sdk import InstrumentType
    from modules.public_history import fetch_research_bars, research_request
    from modules.history_diagnostics import HistoryError, history_diagnostics
    kind = InstrumentType.OPTION if option else _instrument_type_for_symbol(InstrumentType, symbol)
    as_of = pd.Timestamp.now(tz='America/New_York').date()
    research_request(symbol, period, kind.value, as_of)
    try:
        client, _ = (_context or _public_context)()
    except PublicProviderError:
        raise
    except Exception:
        raise HistoryError('Public history access is unavailable; check Public configuration in Settings.', history_diagnostics(symbol, period)) from None
    return fetch_research_bars(client, symbol, period, kind.value, as_of)
