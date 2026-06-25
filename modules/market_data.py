from __future__ import annotations

import pandas as pd

from modules.mock_market import get_market_pulse, get_mock_price_history
from modules.mock_market import get_rotation_table, get_scanner_results
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


def rotation_table() -> tuple[pd.DataFrame, str]:
    rotation = get_rotation_table()
    if not has_public_config():
        return rotation, "Mock fallback"

    try:
        symbols = tuple(rotation["Symbol"].str.upper())
        quotes = {item["symbol"]: item for item in get_public_quotes(symbols)}
        rows = []
        for row in rotation.to_dict("records"):
            quote = quotes.get(row["Symbol"], {})
            change = quote.get("change_pct")
            if change is not None:
                row["Rel Strength"] = round(float(change), 2)
                row["Score"] = max(0, min(100, int(50 + (float(change) * 10))))
                row["Phase"] = (
                    "Leading"
                    if change >= 1
                    else "Improving"
                    if change >= 0
                    else "Lagging"
                )
            row["Last"] = quote.get("last")
            rows.append(row)
        return pd.DataFrame(rows), "Public.com Live"
    except Exception:
        return rotation, "Mock fallback"


def scanner_results() -> tuple[pd.DataFrame, str]:
    results = get_scanner_results()
    if not has_public_config():
        return results, "Mock fallback"

    try:
        symbols = tuple(results["Symbol"].str.upper())
        quotes = {item["symbol"]: item for item in get_public_quotes(symbols)}
        rows = []
        for row in results.to_dict("records"):
            quote = quotes.get(row["Symbol"], {})
            change = quote.get("change_pct")
            if change is not None:
                row["Change %"] = round(float(change), 2)
                row["Last"] = quote.get("last")
                row["Score"] = max(0, min(100, int(row["Score"] + float(change))))
            rows.append(row)
        return pd.DataFrame(rows), "Public.com Live"
    except Exception:
        return results, "Mock fallback"
