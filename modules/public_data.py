from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st


def has_public_config() -> bool:
    return bool(st.secrets.get("PUBLIC_API_SECRET"))


@st.cache_resource
def _public_context() -> tuple[Any, str]:
    from public_api_sdk import ApiKeyAuthConfig, PublicApiClient

    client = PublicApiClient(
        ApiKeyAuthConfig(
            api_secret_key=st.secrets["PUBLIC_API_SECRET"],
            validity_minutes=60,
        )
    )
    accounts = client.get_accounts().accounts
    if not accounts:
        raise RuntimeError("No Public brokerage account is available for this key.")

    preferred = st.secrets.get("PUBLIC_ACCOUNT_NUMBER")
    account_id = preferred or accounts[0].account_id
    return client, account_id


def _as_float(value: Any) -> float | None:
    return float(value) if value is not None else None


@st.cache_data(ttl=30, show_spinner=False)
def get_public_quotes(symbols: tuple[str, ...]) -> list[dict]:
    from public_api_sdk import InstrumentType, OrderInstrument

    client, account_id = _public_context()
    instruments = [
        OrderInstrument(symbol=symbol.upper(), type=InstrumentType.EQUITY)
        for symbol in symbols
    ]
    quotes = client.get_quotes(instruments, account_id=account_id)
    return [
        {
            "symbol": quote.instrument.symbol,
            "last": _as_float(quote.last),
            "bid": _as_float(quote.bid),
            "ask": _as_float(quote.ask),
            "previous_close": _as_float(quote.previous_close),
            "change": _as_float(
                quote.one_day_change.change if quote.one_day_change else None
            ),
            "change_pct": _as_float(
                quote.one_day_change.percent_change if quote.one_day_change else None
            ),
            "volume": quote.volume,
            "updated_at": quote.last_timestamp,
        }
        for quote in quotes
    ]


@st.cache_data(ttl=300, show_spinner=False)
def get_public_price_history(symbol: str) -> pd.DataFrame:
    from public_api_sdk import BarAggregation, BarPeriod

    client, _ = _public_context()
    response = client.get_bars(
        symbol.upper(),
        BarPeriod.QUARTER,
        aggregation=BarAggregation.ONE_DAY,
    )
    return pd.DataFrame(
        [
            {
                "date": pd.to_datetime(bar.timestamp),
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": float(bar.volume),
            }
            for bar in response.regular_market.bars
        ]
    )


@st.cache_data(ttl=30, show_spinner=False)
def get_public_portfolio() -> dict:
    client, account_id = _public_context()
    portfolio = client.get_portfolio(account_id=account_id)
    positions = []

    for position in portfolio.positions:
        quantity = float(position.quantity)
        cost_basis = position.cost_basis
        price = position.last_price
        positions.append(
            {
                "symbol": position.instrument.symbol,
                "side": "Long" if quantity >= 0 else "Short",
                "quantity": abs(quantity),
                "entry_price": _as_float(cost_basis.unit_cost if cost_basis else None),
                "last_price": _as_float(price.last_price if price else None),
                "unrealized_pnl": _as_float(
                    cost_basis.gain_value if cost_basis else None
                ),
                "current_value": _as_float(position.current_value),
                "strategy": "Public portfolio",
            }
        )

    return {
        "account_id": account_id,
        "account_type": portfolio.account_type.value,
        "positions": positions,
        "equity": sum(float(item.value) for item in portfolio.equity),
        "buying_power": float(portfolio.buying_power.buying_power),
    }


def test_public_connection() -> tuple[bool, str]:
    if not has_public_config():
        return False, "PUBLIC_API_SECRET is not configured."
    try:
        _, account_id = _public_context()
        return True, f"Connected to Public account ending in {account_id[-4:]}."
    except Exception:
        return False, "Public authentication failed. Check or regenerate the secret key."

