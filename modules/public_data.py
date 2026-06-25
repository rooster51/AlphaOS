from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st


def has_public_config() -> bool:
    return bool(st.secrets.get("PUBLIC_API_SECRET"))


def can_access_public_portfolio(user: dict | None) -> bool:
    owner_email = st.secrets.get("PUBLIC_OWNER_EMAIL")
    user_email = user.get("email") if user else None
    return bool(
        owner_email
        and user_email
        and owner_email.strip().casefold() == user_email.strip().casefold()
    )


def _select_account(accounts: list[Any], preferred: str | None) -> Any:
    if preferred:
        preferred = preferred.strip()
        match = next(
            (
                account
                for account in accounts
                if str(getattr(account, "account_id", "")).strip() == preferred
                or str(getattr(account, "account_number", "")).strip() == preferred
            ),
            None,
        )
        if match is None:
            raise RuntimeError("PUBLIC_ACCOUNT_NUMBER is not available for this key.")
        return match

    scored = sorted(
        accounts,
        key=_account_selection_score,
        reverse=True,
    )
    return scored[0]


def _account_field(account: Any, field: str) -> str:
    value = getattr(account, field, "")
    value = getattr(value, "value", value)
    return str(value or "")


def _account_search_text(account: Any) -> str:
    fields = (
        "account_type",
        "account_sub_type",
        "account_name",
        "nickname",
        "name",
        "display_name",
    )
    return " ".join(_account_field(account, field) for field in fields).casefold()


def _account_selection_score(account: Any) -> int:
    text = _account_search_text(account)
    score = 0
    if "broker" in text:
        score += 50
    if "individual" in text or "cash" in text or "margin" in text:
        score += 20
    if "ira" in text or "retirement" in text or "roth" in text or "traditional" in text:
        score -= 100
    return score


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

    account = _select_account(accounts, st.secrets.get("PUBLIC_ACCOUNT_NUMBER"))
    return client, account.account_id


def _mask_account_id(account_id: str) -> str:
    account_id = str(account_id)
    return f"...{account_id[-4:]}" if len(account_id) > 4 else account_id


@st.cache_data(ttl=60, show_spinner=False)
def get_public_account_summaries() -> list[dict]:
    from public_api_sdk import ApiKeyAuthConfig, PublicApiClient

    client = PublicApiClient(
        ApiKeyAuthConfig(
            api_secret_key=st.secrets["PUBLIC_API_SECRET"],
            validity_minutes=60,
        )
    )
    accounts = client.get_accounts().accounts
    selected = _select_account(accounts, st.secrets.get("PUBLIC_ACCOUNT_NUMBER"))
    selected_id = str(getattr(selected, "account_id", ""))
    rows = []
    for account in accounts:
        account_id = str(getattr(account, "account_id", ""))
        rows.append(
            {
                "selected": account_id == selected_id,
                "account_id": account_id,
                "ending": _mask_account_id(account_id),
                "account_type": _account_field(account, "account_type"),
                "account_sub_type": _account_field(account, "account_sub_type"),
                "name": _account_field(account, "account_name")
                or _account_field(account, "nickname")
                or _account_field(account, "name"),
            }
        )
    return rows


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
