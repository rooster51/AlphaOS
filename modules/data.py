from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from modules.supabase_client import get_supabase


DEMO_TRADES = [
    {
        "symbol": "NVDA",
        "side": "Long",
        "entry_date": str(date.today() - timedelta(days=18)),
        "exit_date": str(date.today() - timedelta(days=12)),
        "quantity": 10,
        "entry_price": 118.2,
        "exit_price": 124.8,
        "pnl": 66.0,
        "status": "Closed",
        "strategy": "Momentum",
        "notes": "Clean trend follow.",
    },
    {
        "symbol": "QQQ",
        "side": "Long",
        "entry_date": str(date.today() - timedelta(days=10)),
        "exit_date": str(date.today() - timedelta(days=5)),
        "quantity": 8,
        "entry_price": 455.0,
        "exit_price": 448.5,
        "pnl": -52.0,
        "status": "Closed",
        "strategy": "Pullback",
        "notes": "Stopped at invalidation.",
    },
]

DEMO_POSITIONS = [
    {
        "symbol": "SPY",
        "side": "Long",
        "quantity": 5,
        "entry_price": 542.5,
        "last_price": 546.2,
        "unrealized_pnl": 18.5,
        "strategy": "Core trend",
    }
]

DEMO_WATCHLIST = [
    {"symbol": "SPY", "notes": "Market baseline", "score": 78},
    {"symbol": "QQQ", "notes": "Growth leadership", "score": 82},
    {"symbol": "NVDA", "notes": "Momentum bellwether", "score": 91},
]

DEMO_SETTINGS = {
    "display_name": "Demo Trader",
    "default_account_size": 10000.0,
    "default_risk_pct": 1.0,
    "timezone": "America/New_York",
}


def _session_table(name: str, defaults: list[dict]) -> list[dict]:
    key = f"alphaos_{name}"
    if key not in st.session_state:
        st.session_state[key] = list(defaults)
    return st.session_state[key]


def get_account_snapshot(user_id: str | None = None) -> dict:
    supabase = get_supabase()
    if supabase and user_id and user_id != "demo-user":
        try:
            trades = (
                supabase.table("trades")
                .select("*")
                .eq("user_id", user_id)
                .order("entry_date", desc=True)
                .execute()
                .data
            )
            positions = [trade for trade in trades if trade.get("status") == "Open"]
            return {"trades": trades, "open_positions": positions}
        except Exception as exc:
            st.warning(f"Using demo data because Supabase read failed: {exc}")

    return {
        "trades": _session_table("trades", DEMO_TRADES),
        "open_positions": _session_table("positions", DEMO_POSITIONS),
    }


def get_watchlist(user_id: str | None = None) -> list[dict]:
    supabase = get_supabase()
    if supabase and user_id and user_id != "demo-user":
        try:
            return (
                supabase.table("watchlist")
                .select("*")
                .eq("user_id", user_id)
                .order("symbol")
                .execute()
                .data
            )
        except Exception as exc:
            st.warning(f"Using demo watchlist because Supabase read failed: {exc}")
    return _session_table("watchlist", DEMO_WATCHLIST)


def get_user_settings(user_id: str | None = None) -> dict:
    supabase = get_supabase()
    if supabase and user_id and user_id != "demo-user":
        try:
            rows = (
                supabase.table("user_settings")
                .select("*")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
                .data
            )
            if rows:
                return rows[0]
        except Exception as exc:
            st.warning(f"Using demo settings because Supabase read failed: {exc}")

    key = "alphaos_user_settings"
    if key not in st.session_state:
        st.session_state[key] = dict(DEMO_SETTINGS)
    return st.session_state[key]


def save_user_settings(settings: dict, user_id: str | None = None) -> None:
    supabase = get_supabase()
    if supabase and user_id and user_id != "demo-user":
        payload = dict(settings)
        payload["user_id"] = user_id
        supabase.table("user_settings").upsert(payload, on_conflict="user_id").execute()
        return
    st.session_state["alphaos_user_settings"] = dict(settings)


def add_trade(trade: dict, user_id: str | None = None) -> None:
    supabase = get_supabase()
    if supabase and user_id and user_id != "demo-user":
        trade["user_id"] = user_id
        supabase.table("trades").insert(trade).execute()
        return
    _session_table("trades", DEMO_TRADES).insert(0, trade)


def add_watchlist_symbol(symbol: str, notes: str, user_id: str | None = None) -> None:
    row = {"symbol": symbol.upper(), "notes": notes, "score": 50}
    supabase = get_supabase()
    if supabase and user_id and user_id != "demo-user":
        row["user_id"] = user_id
        supabase.table("watchlist").upsert(row).execute()
        return
    _session_table("watchlist", DEMO_WATCHLIST).append(row)


def trades_dataframe(trades: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(trades)
    if df.empty:
        return pd.DataFrame()
    return df
