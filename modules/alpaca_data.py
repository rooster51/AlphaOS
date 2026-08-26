from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd
import streamlit as st


BASE_URL = "https://data.alpaca.markets/v2"
SUPPORTED_SYMBOLS = {"SPY", "QQQ", "DIA", "IWM"}
PROXY_SYMBOLS = {"SPX": "SPY", "XSP": "SPY"}


def has_alpaca_config() -> bool:
    return bool(st.secrets.get("ALPACA_API_KEY_ID") and st.secrets.get("ALPACA_API_SECRET_KEY"))


def _headers() -> dict[str, str]:
    if not has_alpaca_config():
        raise RuntimeError("ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY are not configured in Streamlit secrets.")
    return {
        "APCA-API-KEY-ID": st.secrets["ALPACA_API_KEY_ID"],
        "APCA-API-SECRET-KEY": st.secrets["ALPACA_API_SECRET_KEY"],
    }


def _normalize_symbol(symbol: str, use_spy_proxy: bool) -> tuple[str, str]:
    requested = symbol.upper().strip()
    if requested in SUPPORTED_SYMBOLS:
        return requested, requested
    if use_spy_proxy and requested in PROXY_SYMBOLS:
        return PROXY_SYMBOLS[requested], f"{requested} via {PROXY_SYMBOLS[requested]} proxy"
    raise RuntimeError(
        f"Alpaca free stock bars support ETFs like SPY, QQQ, DIA, and IWM. "
        f"Use the SPY proxy option for {requested} or upload a CSV."
    )


def _empty_bars() -> pd.DataFrame:
    return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])


def _bars_from_payload(payload: dict[str, Any], symbol: str) -> pd.DataFrame:
    bars = payload.get("bars", {}).get(symbol, [])
    if not bars:
        return _empty_bars()
    frame = pd.DataFrame(
        [
            {
                "timestamp": row.get("t"),
                "open": row.get("o"),
                "high": row.get("h"),
                "low": row.get("l"),
                "close": row.get("c"),
                "volume": row.get("v"),
            }
            for row in bars
        ]
    )
    frame["timestamp"] = (
        pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["timestamp", "open", "high", "low", "close"])


@st.cache_data(ttl=300, show_spinner=False)
def get_alpaca_intraday_bars(
    symbol: str,
    lookback_days: int = 30,
    timeframe: str = "30Min",
    feed: str = "iex",
    use_spy_proxy: bool = True,
) -> tuple[pd.DataFrame, str]:
    if lookback_days < 1:
        raise ValueError("lookback_days must be at least 1.")

    alpaca_symbol, label = _normalize_symbol(symbol, use_spy_proxy)
    end = datetime.now(timezone.utc) - timedelta(minutes=20 if feed == "sip" else 0)
    start = end - timedelta(days=lookback_days)
    query = urlencode(
        {
            "symbols": alpaca_symbol,
            "timeframe": timeframe,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "adjustment": "raw",
            "feed": feed,
            "limit": 10000,
        }
    )
    request = Request(f"{BASE_URL}/stocks/bars?{query}", headers=_headers())
    try:
        with urlopen(request, timeout=20) as response:
            payload = response.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Alpaca returned HTTP {exc.code}: {body[:300]}") from exc

    return _bars_from_payload(json.loads(payload), alpaca_symbol), label
