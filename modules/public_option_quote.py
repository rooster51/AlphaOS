"""Pure SDK option-row formatting shared by headless and legacy UI providers.

This is not quote validation or archive normalization. Preserve observed values,
missing fields and conversion failures; callers retain their own quality gates.
No authentication, SDK imports, caching, clocks or network access belong here.
"""
from typing import Any


def option_quote_row(quote: Any, option_type: str, *, as_float) -> dict | None:
    details = quote.option_details
    if details is None or details.strike_price is None:
        return None
    greeks = details.greeks
    bid = as_float(quote.bid)
    ask = as_float(quote.ask)
    mid = as_float(details.mid_price)
    if mid is None and bid is not None and ask is not None:
        mid = (bid + ask) / 2
    return {
        "contract": quote.instrument.symbol,
        "type": option_type,
        "strike": as_float(details.strike_price),
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "delta": as_float(greeks.delta if greeks else None),
        "gamma": as_float(greeks.gamma if greeks else None),
        "theta": as_float(greeks.theta if greeks else None),
        "vega": as_float(greeks.vega if greeks else None),
        "rho": as_float(greeks.rho if greeks else None),
        "bid_timestamp": getattr(quote, "bid_timestamp", None),
        "ask_timestamp": getattr(quote, "ask_timestamp", None),
        "iv": as_float(greeks.implied_volatility if greeks else None),
        "volume": quote.volume,
        "open_interest": getattr(quote, "open_interest", None),
    }
