"""Shared Quant Lab research-session helpers.

Keeps the submitted OHLC dataset available across Streamlit research pages without
forcing each page to retrieve the same market history independently.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

SESSION_KEY = "quant_research_session"


@dataclass(frozen=True)
class ResearchSessionSummary:
    symbol: str
    period: str
    first_date: date | None
    last_date: date | None
    observations: int


def normalize_history(history: pd.DataFrame) -> pd.DataFrame:
    """Return a defensive, chronologically sorted copy of submitted OHLC history."""
    if not isinstance(history, pd.DataFrame) or history.empty:
        raise ValueError("Supply nonempty date, symbol, open, high, low, close history.")
    required = {"date", "symbol", "open", "high", "low", "close"}
    missing = required.difference(history.columns)
    if missing:
        raise ValueError(f"Research history is missing required columns: {', '.join(sorted(missing))}.")
    frame = history.copy(deep=True)
    frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.date
    frame = frame.sort_values("date", kind="stable").reset_index(drop=True)
    return frame


def save_research_session(state: Any, *, history: pd.DataFrame, symbol: str, period: str, metadata: dict | None = None) -> ResearchSessionSummary:
    """Persist the submitted dataset in Streamlit-compatible session state."""
    frame = normalize_history(history)
    symbol = str(symbol).strip().upper()
    state[SESSION_KEY] = {
        "history": frame,
        "symbol": symbol,
        "period": str(period),
        "metadata": dict(metadata or {}),
    }
    return summarize_research_session(state)


def get_research_session(state: Any) -> dict | None:
    value = state.get(SESSION_KEY)
    if not isinstance(value, dict):
        return None
    history = value.get("history")
    if not isinstance(history, pd.DataFrame) or history.empty:
        return None
    return value


def summarize_research_session(state: Any) -> ResearchSessionSummary:
    value = get_research_session(state)
    if value is None:
        raise ValueError("No active Quant Lab research dataset is available.")
    frame = value["history"]
    return ResearchSessionSummary(
        symbol=str(value.get("symbol", "")).upper(),
        period=str(value.get("period", "")),
        first_date=frame["date"].iloc[0],
        last_date=frame["date"].iloc[-1],
        observations=len(frame),
    )


def clear_research_session(state: Any) -> None:
    state.pop(SESSION_KEY, None)
