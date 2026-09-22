"""Distribution-conditioned expiration economics using today's payoff structure.

This module does not reconstruct historical option quotes. It applies the saved
trade's exact expiration payoff to underlying terminal returns observed in a
Phase 3 historical-analog sample.
"""
from math import isfinite

import numpy as np
import pandas as pd

from modules.market_outcomes import HORIZONS
from modules.options_payoff import trade_analysis, validate_trade
from modules.premium_engine import payoff
from modules.threshold_survival import non_overlapping_subset

VERSION = "option-scenario-ev-v1"


def _finite_number(value, label, minimum=None):
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{label} must be a finite number.") from None
    if not isfinite(value) or (minimum is not None and value < minimum):
        raise ValueError(f"{label} must be a finite number" + (f" >= {minimum}." if minimum is not None else "."))
    return value


def _prepare_analogs(analog_result, horizon):
    if horizon not in HORIZONS:
        raise ValueError("Use a 1, 2, 3, 5 or 10 observed-session horizon.")
    try:
        frame = analog_result["analogs"].copy().reset_index(drop=True)
        target = analog_result["target"]
        symbol = str(target["symbol"])
        target_spot = float(target["close"])
        target_date = pd.Timestamp(target["date"])
        if target_date.tzinfo:
            target_date = target_date.tz_convert('UTC').tz_localize(None)
        target_date = target_date.normalize()
        frame['date'] = pd.to_datetime(frame['date'], utc=True, errors='raise').dt.tz_convert(None).dt.normalize()
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError("Supply a valid Phase 3 analog result with target and attached outcomes.") from None
    if symbol not in ("SPY", "QQQ") or not isfinite(target_spot) or target_spot <= 0:
        raise ValueError("Phase 3 target symbol/spot is invalid.")
    if frame.date.isna().any() or frame.date.duplicated().any() or (frame.date >= target_date).any():
        raise ValueError("Analog dates must be unique, valid sessions strictly before the target date.")
    if 'symbol' in frame and not frame.symbol.eq(symbol).all():
        raise ValueError("Every analog observation must match the target symbol.")
    col = f"future_return_{horizon}s"
    if col not in frame:
        raise ValueError(f"Phase 3 analogs must include {col}.")
    frame[col] = pd.to_numeric(frame[col], errors="coerce").replace([np.inf, -np.inf], np.nan)
    known = frame[col].notna() & (frame[col] >= -1)
    flag = f"outcome_known_by_target_{horizon}s"
    if flag in frame:
        known &= frame[flag].eq(True).fillna(False)
    frame = frame.loc[known].copy()
    return frame, symbol, target_spot, col


def _summary(pnl, max_loss):
    pnl = pd.Series(pnl, dtype=float).replace([np.inf, -np.inf], np.nan).dropna()
    n = len(pnl)
    if not n:
        return dict(n=0, expected_payoff=None, median_payoff=None, positive_frequency=None,
                    negative_frequency=None, zero_frequency=None, p10_payoff=None, p25_payoff=None,
                    p75_payoff=None, p90_payoff=None, worst_payoff=None, best_payoff=None,
                    expected_payoff_on_max_risk=None, average_winner=None, average_loser=None,
                    profit_factor=None)
    winners = pnl[pnl > 1e-10]
    losers = pnl[pnl < -1e-10]
    gross_profit = float(winners.sum())
    gross_loss = float(-losers.sum())
    mean = float(pnl.mean())
    finite_risk = isinstance(max_loss, (int, float)) and isfinite(max_loss) and max_loss > 0
    return dict(n=n, expected_payoff=mean, median_payoff=float(pnl.median()),
        positive_frequency=float((pnl > 1e-10).mean()), negative_frequency=float((pnl < -1e-10).mean()),
        zero_frequency=float((pnl.abs() <= 1e-10).mean()),
        p10_payoff=float(pnl.quantile(.10, interpolation="linear")), p25_payoff=float(pnl.quantile(.25, interpolation="linear")),
        p75_payoff=float(pnl.quantile(.75, interpolation="linear")), p90_payoff=float(pnl.quantile(.90, interpolation="linear")),
        worst_payoff=float(pnl.min()), best_payoff=float(pnl.max()),
        expected_payoff_on_max_risk=mean / max_loss if finite_risk else None,
        average_winner=float(winners.mean()) if len(winners) else None,
        average_loser=float(losers.mean()) if len(losers) else None,
        profit_factor=(gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else None)))


def scenario_economics(analog_result, trade, horizon=3, units=1,
                       commission_per_contract=0.0, entry_slippage=0.0,
                       terminal_friction=0.0):
    """Apply today's exact expiration payoff to matured analog terminal returns."""
    validated = validate_trade(trade)
    if not isinstance(units, (int, float)) or not isfinite(units) or units < 1 or units != int(units):
        raise ValueError("Strategy units must be a positive whole number.")
    units = int(units)
    commission = _finite_number(commission_per_contract, "Commission per contract", 0)
    slippage = _finite_number(entry_slippage, "Entry slippage", 0)
    terminal_cost = _finite_number(terminal_friction, "Terminal friction", 0)
    analogs, symbol, target_spot, return_col = _prepare_analogs(analog_result, horizon)
    if validated["symbol"] != symbol:
        raise ValueError("Trade symbol must match the Phase 3 target symbol.")
    if abs(validated["spot"] / target_spot - 1) > 1e-6:
        raise ValueError("Trade spot must match the Phase 3 target spot. Refresh the research/trade snapshot together.")

    analysis = trade_analysis(validated, units)
    per_unit_contracts = sum(abs(int(leg["qty"])) for leg in validated["legs"])
    extra_friction = units * (commission * per_unit_contracts + slippage + terminal_cost)
    rows = []
    for _, row in analogs.iterrows():
        ret = float(row[return_col])
        terminal = target_spot * (1 + ret)
        gross = payoff(validated["legs"], validated["credit"], terminal,
                       validated["shares"], validated["stock_basis"], validated["fees"]) * units
        rows.append(dict(analog_date=pd.Timestamp(row["date"]), analog_forward_return=ret,
                         scenario_terminal_spot=terminal, gross_expiration_pnl=gross,
                         modeled_extra_friction=extra_friction, net_expiration_pnl=gross-extra_friction))
    observations = pd.DataFrame(rows, columns=["analog_date", "analog_forward_return", "scenario_terminal_spot",
        "gross_expiration_pnl", "modeled_extra_friction", "net_expiration_pnl"])

    nonoverlap = pd.DataFrame(columns=observations.columns)
    try:
        prepared = analog_result["analogs"].copy().reset_index(drop=True)
        dates = pd.DatetimeIndex(pd.to_datetime(analog_result["session_dates"], utc=True)).tz_convert(None).normalize()
        positions = pd.Series(np.arange(len(dates)), index=dates)
        prepared["date"] = pd.to_datetime(prepared.date, utc=True).dt.tz_convert(None).dt.normalize()
        prepared["session_position"] = prepared.date.map(positions)
        prepared["as_of_eligible"] = prepared[f"outcome_known_by_target_{horizon}s"].eq(True) if f"outcome_known_by_target_{horizon}s" in prepared else True
        prepared["terminal_status"] = prepared[return_col].notna().map({True:"valid", False:pd.NA}).astype("string")
        prepared["touched_or_breached"] = prepared[return_col].notna().astype("boolean")
        chosen = non_overlapping_subset(prepared, horizon)
        chosen_dates = set(pd.to_datetime(chosen.date).dt.normalize())
        nonoverlap = observations[observations.analog_date.dt.normalize().isin(chosen_dates)].copy()
    except (KeyError, TypeError, ValueError, AttributeError):
        pass

    return dict(config=dict(version=VERSION, symbol=symbol, horizon=horizon, units=units,
                    analog_method=analog_result.get("config", {}).get("method"),
                    analog_target_date=analog_result.get("config", {}).get("target_date"),
                    interpretation="Distribution-conditioned expiration payoff; not a historical options backtest or forecast probability."),
        trade=validated, trade_analysis=analysis,
        friction=dict(existing_trade_fees=validated["fees"]*units, commission_per_contract=commission,
                      entry_slippage=slippage, terminal_friction=terminal_cost, modeled_extra_friction=extra_friction),
        observations=observations,
        gross_summary=_summary(observations.gross_expiration_pnl if not observations.empty else [], analysis["max_loss"]),
        net_summary=_summary(observations.net_expiration_pnl if not observations.empty else [], analysis["max_loss"]),
        non_overlapping_observations=nonoverlap,
        non_overlapping_net_summary=_summary(nonoverlap.net_expiration_pnl if not nonoverlap.empty else [], analysis["max_loss"]))
