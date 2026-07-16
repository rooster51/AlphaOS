from __future__ import annotations

from datetime import date, timedelta

import pandas as pd


DEFAULT_GUARDRAILS = {
    "max_trades_per_day": 3,
    "max_daily_loss_pct": 2.0,
    "cooldown_after_losses": 2,
    "cooldown_minutes": 60,
    "min_backtest_win_rate": 50.0,
    "max_reversal_warnings": 1,
    "require_pretrade_checklist": True,
}


def normalize_guardrails(settings: dict | None) -> dict:
    settings = settings or {}
    guardrails = dict(DEFAULT_GUARDRAILS)
    for key in guardrails:
        if settings.get(key) is not None:
            guardrails[key] = settings[key]
    guardrails["max_trades_per_day"] = int(guardrails["max_trades_per_day"] or 0)
    guardrails["cooldown_after_losses"] = int(guardrails["cooldown_after_losses"] or 0)
    guardrails["cooldown_minutes"] = int(guardrails["cooldown_minutes"] or 0)
    guardrails["max_daily_loss_pct"] = float(guardrails["max_daily_loss_pct"] or 0.0)
    guardrails["min_backtest_win_rate"] = float(
        guardrails["min_backtest_win_rate"] or 0.0
    )
    guardrails["max_reversal_warnings"] = int(
        guardrails["max_reversal_warnings"] or 0
    )
    guardrails["require_pretrade_checklist"] = bool(
        guardrails["require_pretrade_checklist"]
    )
    return guardrails


def _trades_frame(trades: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(trades)
    if frame.empty:
        return pd.DataFrame()
    for column in ("entry_date", "exit_date"):
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], errors="coerce").dt.date
    if "pnl" not in frame.columns:
        frame["pnl"] = 0.0
    frame["pnl"] = pd.to_numeric(frame["pnl"], errors="coerce").fillna(0.0)
    return frame


def discipline_status(
    trades: list[dict],
    settings: dict | None,
    reversal_checks: list[dict] | None = None,
    backtest: dict | None = None,
) -> dict:
    guardrails = normalize_guardrails(settings)
    frame = _trades_frame(trades)
    today = date.today()
    account_size = float((settings or {}).get("default_account_size") or 0.0)
    daily_loss_limit = account_size * (guardrails["max_daily_loss_pct"] / 100)

    trades_today = 0
    realized_today = 0.0
    consecutive_losses = 0
    last_loss_date = None
    if not frame.empty:
        if "entry_date" in frame.columns:
            trades_today = int((frame["entry_date"] == today).sum())
        if "exit_date" in frame.columns:
            closed_today = frame[frame["exit_date"] == today]
            realized_today = float(closed_today["pnl"].sum())

        closed = (
            frame[frame["status"] == "Closed"].copy()
            if "status" in frame.columns
            else pd.DataFrame()
        )
        if "exit_date" in closed.columns and not closed.empty:
            closed = closed.dropna(subset=["exit_date"]).sort_values("exit_date")
            for _, row in closed.iloc[::-1].iterrows():
                if float(row.get("pnl") or 0.0) < 0:
                    consecutive_losses += 1
                    if last_loss_date is None:
                        last_loss_date = row.get("exit_date")
                else:
                    break

    warnings = []
    blockers = []

    if guardrails["max_trades_per_day"] and trades_today >= guardrails["max_trades_per_day"]:
        blockers.append(
            f"Max trades reached: {trades_today}/{guardrails['max_trades_per_day']} trades entered today."
        )

    if daily_loss_limit and realized_today <= -daily_loss_limit:
        blockers.append(
            f"Daily loss limit hit: ${realized_today:,.2f} realized today versus ${daily_loss_limit:,.2f} limit."
        )
    elif daily_loss_limit and realized_today <= -(daily_loss_limit * 0.5):
        warnings.append(
            f"Daily loss warning: ${realized_today:,.2f} realized today, more than half of your daily limit."
        )

    if (
        guardrails["cooldown_after_losses"]
        and consecutive_losses >= guardrails["cooldown_after_losses"]
    ):
        blockers.append(
            f"Cooldown triggered after {consecutive_losses} consecutive closed losses."
        )

    if last_loss_date and last_loss_date >= today - timedelta(days=1):
        warnings.append("Recent loss detected. Use smaller size or wait for a cleaner setup.")

    reversal_warning_count = sum(
        1 for check in reversal_checks or [] if check.get("status") == "Warning"
    )
    if reversal_warning_count > guardrails["max_reversal_warnings"]:
        blockers.append(
            f"Reversal risk too high: {reversal_warning_count} warnings versus {guardrails['max_reversal_warnings']} allowed."
        )

    if backtest and backtest.get("trades", 0) > 0:
        win_rate = float(backtest.get("win_rate") or 0.0)
        if win_rate < guardrails["min_backtest_win_rate"]:
            blockers.append(
                f"Backtest win rate below rule: {win_rate:.1f}% versus {guardrails['min_backtest_win_rate']:.1f}% minimum."
            )

    status = "Blocked" if blockers else "Caution" if warnings else "Clear"
    return {
        "status": status,
        "blockers": blockers,
        "warnings": warnings,
        "trades_today": trades_today,
        "realized_today": round(realized_today, 2),
        "daily_loss_limit": round(daily_loss_limit, 2),
        "consecutive_losses": consecutive_losses,
        "guardrails": guardrails,
    }
