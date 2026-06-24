from __future__ import annotations

import pandas as pd

from modules.mock_market import get_market_pulse, get_mock_price_history
from modules.public_data import (
    can_access_public_portfolio,
    get_public_portfolio,
    get_public_price_history,
    get_public_quotes,
    has_public_config,
)


def market_pulse() -> tuple[list[dict], str]:
    placeholders = get_market_pulse()
    if not has_public_config():
        return placeholders, "Mock fallback"

    try:
        symbols = tuple(item["symbol"] for item in placeholders)
        quotes = {item["symbol"]: item for item in get_public_quotes(symbols)}
        rows = []
        for placeholder in placeholders:
            quote = quotes.get(placeholder["symbol"], {})
            rows.append(
                {
                    **placeholder,
                    "last": quote.get("last"),
                    "change": quote.get("change_pct"),
                    "volume": quote.get("volume"),
                }
            )
        return rows, "Public.com Live"
    except Exception:
        return placeholders, "Mock fallback"


def price_history(symbol: str) -> tuple[pd.DataFrame, str]:
    if has_public_config():
        try:
            history = get_public_price_history(symbol)
            if not history.empty:
                return history, "Public.com Live"
        except Exception:
            pass
    return get_mock_price_history(symbol), "Mock fallback"


def brokerage_positions(user: dict | None) -> tuple[list[dict], dict, str]:
    if has_public_config() and can_access_public_portfolio(user):
        try:
            portfolio = get_public_portfolio()
            return portfolio["positions"], portfolio, "Public.com Live"
        except Exception:
            pass
    return [], {}, "Unavailable"

