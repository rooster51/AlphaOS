"""Intraday Public OHLCV adapter.

Uses the Public SDK's historic-bars interface with DAY/ONE_MINUTE.
No resampling, forward-fill, or synthetic bars.
"""
from __future__ import annotations

from datetime import datetime, timezone

SUPPORTED_AGGREGATIONS = {
    "ONE_MINUTE", "FIVE_MINUTES", "TEN_MINUTES", "FIFTEEN_MINUTES",
    "THIRTY_MINUTES", "ONE_HOUR",
}


def fetch_intraday_bars(provider, symbol, aggregation="ONE_MINUTE"):
    if aggregation not in SUPPORTED_AGGREGATIONS:
        raise ValueError("Unsupported intraday aggregation.")

    try:
        from public_api_sdk import BarAggregation, BarPeriod
        aggregation_value = getattr(BarAggregation, aggregation)
        response = provider.client.get_bars(
            symbol,
            BarPeriod.DAY,
            aggregation=aggregation_value,
        )
    except Exception:
        raise RuntimeError("Public intraday history retrieval failed.") from None

    response_symbol = getattr(response, "symbol", symbol)
    if response_symbol != symbol:
        raise RuntimeError("Unexpected Public intraday history response.")

    regular = getattr(response, "regular_market", None)
    bars = getattr(regular, "bars", None)
    if bars is None:
        raise RuntimeError("Public intraday response has no regular-market bars.")

    retrieved = datetime.now(timezone.utc).isoformat()
    normalized = []
    for bar in bars:
        ts = getattr(bar, "timestamp", None)
        values = {
            "open": getattr(bar, "open", None),
            "high": getattr(bar, "high", None),
            "low": getattr(bar, "low", None),
            "close": getattr(bar, "close", None),
            "volume": getattr(bar, "volume", None),
        }
        if not ts or any(value is None for value in values.values()):
            continue
        normalized.append({
            "schema_version": "intraday-bar-v1",
            "provider": "Public",
            "symbol": symbol,
            "aggregation": aggregation,
            "timestamp": str(ts),
            "open": float(values["open"]),
            "high": float(values["high"]),
            "low": float(values["low"]),
            "close": float(values["close"]),
            "volume": float(values["volume"]),
            "retrieved_at": retrieved,
        })

    if not normalized:
        raise RuntimeError("Public returned no complete regular-market intraday bars.")
    return normalized
