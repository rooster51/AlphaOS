from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st
from modules.public_provider import configuration, _as_float, _normalize_public_symbol, _instrument_type_for_symbol, _order_instrument, _option_quote_row


INDEX_SYMBOLS = {"SPX", "NDX", "RUT", "DJX", "VIX"}
SYMBOL_ALIASES = {
    "^SPX": "SPX",
    "$SPX": "SPX",
    "SPX.X": "SPX",
    "^NDX": "NDX",
    "$NDX": "NDX",
    "^RUT": "RUT",
    "$RUT": "RUT",
    "^VIX": "VIX",
    "$VIX": "VIX",
}


def has_public_config() -> bool:
    from modules.public_provider import configuration
    return bool(configuration(st.secrets)[0])


def can_access_public_portfolio(user: dict | None) -> bool:
    owner_email = st.secrets.get("PUBLIC_OWNER_EMAIL")
    user_email = user.get("email") if user else None
    return bool(
        owner_email
        and user_email
        and owner_email.strip().casefold() == user_email.strip().casefold()
    )


from modules.public_session import _select_account, _account_field, _account_search_text, _account_selection_score


@st.cache_resource
def _public_context() -> tuple[Any, str]:
    from modules.public_provider import authenticated_context, configuration
    return authenticated_context(*configuration(st.secrets))



def _mask_account_id(account_id: str) -> str:
    account_id = str(account_id)
    return f"...{account_id[-4:]}" if len(account_id) > 4 else account_id


@st.cache_data(ttl=60, show_spinner=False)
def get_public_account_summaries() -> list[dict]:
    from public_api_sdk import ApiKeyAuthConfig, PublicApiClient

    client = PublicApiClient(
        ApiKeyAuthConfig(
            api_secret_key=configuration(st.secrets)[0],
            validity_minutes=60,
        )
    )
    accounts = client.get_accounts().accounts
    selected = _select_account(accounts, configuration(st.secrets)[1])
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










@st.cache_data(ttl=30, show_spinner=False)
def get_public_quotes(symbols: tuple[str, ...]) -> list[dict]:
    from modules.public_provider import get_public_quotes as shared
    return shared(symbols, _context=_public_context)


@st.cache_data(ttl=300, show_spinner=False)
def get_public_price_history(symbol: str) -> pd.DataFrame:
    from modules.public_provider import get_public_price_history as shared
    return shared(symbol, _context=_public_context)


@st.cache_data(ttl=300, show_spinner=False)
def get_public_option_expirations(symbol: str) -> list[str]:
    from modules.public_provider import get_public_option_expirations as shared
    return shared(symbol, _context=_public_context)




@st.cache_data(ttl=30, show_spinner=False)
def get_public_option_chain(symbol: str, expiration: str) -> dict:
    from modules.public_provider import get_public_option_chain as shared
    return shared(symbol, expiration, _context=_public_context)


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


@st.cache_data(ttl=300, show_spinner=False)
def get_public_research_bars(symbol: str, period: str = "FIVE_YEARS", option: bool = False) -> pd.DataFrame:
    from modules.public_provider import get_public_research_bars as shared
    return shared(symbol, period, option, _context=_public_context)
