from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd
import requests
import streamlit as st


BASE_URL = "https://api.marketdata.app/v1"


def has_marketdata_config() -> bool:
    return bool(_api_key())


def _api_key() -> str | None:
    return st.secrets.get("MARKETDATA_API_KEY") or st.secrets.get("MARKET_DATA_API_KEY")


def _headers() -> dict[str, str]:
    key = _api_key()
    if not key:
        raise RuntimeError("MARKETDATA_API_KEY is not configured in Streamlit secrets.")
    return {"Authorization": f"Bearer {key}"}


def _empty_bars() -> pd.DataFrame:
    return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])


def _bars_from_response(payload: dict[str, Any]) -> pd.DataFrame:
    if payload.get("s") not in {"ok", None}:
        message = payload.get("errmsg") or payload.get("s") or "Unknown MarketData.app response."
        raise RuntimeError(str(message))

    timestamps = payload.get("t") or []
    opens = payload.get("o") or []
    highs = payload.get("h") or []
    lows = payload.get("l") or []
    closes = payload.get("c") or []
    volumes = payload.get("v") or [None] * len(timestamps)
    if not timestamps:
        return _empty_bars()

    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        }
    )
    frame["timestamp"] = (
        pd.to_datetime(frame["timestamp"], unit="s", utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["timestamp", "open", "high", "low", "close"])


@st.cache_data(ttl=300, show_spinner=False)
def get_marketdata_intraday_bars(
    symbol: str,
    resolution: str = "30",
    lookback_days: int = 30,
    to_value: str = "now",
) -> pd.DataFrame:
    if lookback_days < 1:
        raise ValueError("lookback_days must be at least 1.")
    if lookback_days > 365:
        raise ValueError("MarketData.app intraday candle requests are limited to 365 days per request.")

    from_value = (date.today() - timedelta(days=lookback_days)).isoformat()
    url = f"{BASE_URL}/stocks/candles/{resolution}/{symbol.upper().strip()}/"
    response = requests.get(
        url,
        headers=_headers(),
        params={
            "from": from_value,
            "to": to_value,
            "extended": "false",
        },
        timeout=20,
    )
    if response.status_code == 204:
        return _empty_bars()
    if response.status_code not in {200, 203}:
        raise RuntimeError(f"MarketData.app returned HTTP {response.status_code}: {response.text[:300]}")
    return _bars_from_response(response.json())
