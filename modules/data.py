from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

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
    if "id" not in trade:
        trade["id"] = str(uuid4())
    supabase = get_supabase()
    if supabase and user_id and user_id != "demo-user":
        trade["user_id"] = user_id
        supabase.table("trades").insert(trade).execute()
        return
    _session_table("trades", DEMO_TRADES).insert(0, trade)


def update_trade(
    trade_id: str | None,
    updates: dict,
    user_id: str | None = None,
    session_index: int | None = None,
) -> None:
    supabase = get_supabase()
    if supabase and user_id and user_id != "demo-user" and trade_id:
        (
            supabase.table("trades")
            .update(updates)
            .eq("id", trade_id)
            .eq("user_id", user_id)
            .execute()
        )
        return

    trades = _session_table("trades", DEMO_TRADES)
    if trade_id:
        for index, trade in enumerate(trades):
            if str(trade.get("id")) == str(trade_id):
                trades[index] = {**trade, **updates}
                return
    if session_index is not None and 0 <= session_index < len(trades):
        trades[session_index] = {**trades[session_index], **updates}


def save_daily_pnl_snapshot(
    user_id: str | None,
    equity: float,
    unrealized_pnl: float,
) -> bool:
    row = {
        "snapshot_date": str(date.today()),
        "realized_pnl": 0.0,
        "unrealized_pnl": round(float(unrealized_pnl), 2),
        "equity": round(float(equity), 2),
    }
    supabase = get_supabase()
    if supabase and user_id and user_id != "demo-user":
        try:
            row["user_id"] = user_id
            (
                supabase.table("daily_pnl_snapshots")
                .upsert(row, on_conflict="user_id,snapshot_date")
                .execute()
            )
            return True
        except Exception:
            return False

    snapshots = _session_table("pnl_snapshots", [])
    snapshots[:] = [
        item
        for item in snapshots
        if item.get("snapshot_date") != row["snapshot_date"]
    ]
    snapshots.append(row)
    return True


def get_daily_pnl_snapshots(user_id: str | None = None) -> list[dict]:
    supabase = get_supabase()
    if supabase and user_id and user_id != "demo-user":
        try:
            return (
                supabase.table("daily_pnl_snapshots")
                .select("*")
                .eq("user_id", user_id)
                .order("snapshot_date")
                .execute()
                .data
            )
        except Exception:
            return []
    return _session_table("pnl_snapshots", [])


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
