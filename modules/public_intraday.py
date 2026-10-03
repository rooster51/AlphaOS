"""Intraday Public OHLCV adapter.

Uses Public's documented historic-data DAY route with explicit aggregation.
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
    path = f"/userapigateway/historicdata/EQUITY/{symbol}/DAY/{aggregation}"
    try:
        provider.client.auth_manager.refresh_token_if_needed()
        raw = provider.client.api_client.get(path)
    except Exception:
        raise RuntimeError("Public intraday history retrieval failed.") from None
    if not isinstance(raw, dict) or raw.get("symbol") != symbol:
        raise RuntimeError("Unexpected Public intraday history response.")
    regular = raw.get("regularMarket")
    bars = regular.get("bars") if isinstance(regular, dict) else None
    if not isinstance(bars, list):
        raise RuntimeError("Public intraday response has no regular-market bars.")

    retrieved = datetime.now(timezone.utc).isoformat()
    normalized = []
    for bar in bars:
        if not isinstance(bar, dict):
            continue
        ts = bar.get("timestamp")
        required = ("open", "high", "low", "close", "volume")
        if not ts or any(bar.get(k) is None for k in required):
            continue
        normalized.append({
            "schema_version": "intraday-bar-v1",
            "provider": "Public",
            "symbol": symbol,
            "aggregation": aggregation,
            "timestamp": ts,
            "open": float(bar["open"]),
            "high": float(bar["high"]),
            "low": float(bar["low"]),
            "close": float(bar["close"]),
            "volume": float(bar["volume"]),
            "retrieved_at": retrieved,
        })
    return normalized
