from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


def _to_dataframe(trades: Iterable[dict]) -> pd.DataFrame:
    df = pd.DataFrame(list(trades))
    if df.empty:
        return pd.DataFrame(columns=["exit_date", "pnl"])
    if "pnl" not in df.columns:
        df["pnl"] = pd.NA
    df["pnl"] = pd.to_numeric(df["pnl"], errors="coerce")
    if "exit_date" in df.columns:
        df["exit_date"] = pd.to_datetime(df["exit_date"], errors="coerce")
    return df


def compute_trade_metrics(trades: Iterable[dict]) -> dict:
    df = _to_dataframe(trades)
    closed = df[df["pnl"].notna()].copy()
    if closed.empty:
        return {
            "net_pnl": 0.0,
            "win_rate": 0.0,
            "average_win": 0.0,
            "average_loss": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
            "trade_count": 0,
        }

    wins = closed[closed["pnl"] > 0]
    losses = closed[closed["pnl"] < 0]
    gross_profit = wins["pnl"].sum()
    gross_loss = abs(losses["pnl"].sum())
    equity = closed.sort_values("exit_date", na_position="last")["pnl"].cumsum()
    drawdown = equity - equity.cummax()

    return {
        "net_pnl": round(float(closed["pnl"].sum()), 2),
        "win_rate": round(float((len(wins) / len(closed)) * 100), 1),
        "average_win": round(float(wins["pnl"].mean()) if not wins.empty else 0.0, 2),
        "average_loss": round(float(losses["pnl"].mean()) if not losses.empty else 0.0, 2),
        "profit_factor": round(float(gross_profit / gross_loss), 2) if gross_loss else 0.0,
        "max_drawdown": round(float(drawdown.min()), 2) if not drawdown.empty else 0.0,
        "trade_count": int(len(closed)),
    }


def pnl_by_period(trades: Iterable[dict], period: str) -> pd.DataFrame:
    df = _to_dataframe(trades)
    df = df.dropna(subset=["exit_date"])
    if df.empty:
        return pd.DataFrame(columns=["period", "pnl"])
    grouped = df.groupby(df["exit_date"].dt.to_period(period))["pnl"].sum().reset_index()
    grouped["period"] = grouped["exit_date"].astype(str)
    return grouped[["period", "pnl"]]
