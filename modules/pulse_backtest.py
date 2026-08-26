from __future__ import annotations

from dataclasses import dataclass
from datetime import time

import pandas as pd


PULSE_SYMBOLS = ("SPX", "SPY", "QQQ", "XSP")
SETUP_START = time(9, 30)
SETUP_END = time(11, 30)


@dataclass(frozen=True)
class PulseConfig:
    close_location_threshold: float = 0.90
    max_hold_bars: int = 6
    enhanced_trend_filter: bool = False


def normalize_intraday_history(history: pd.DataFrame) -> pd.DataFrame:
    if history is None or history.empty:
        return pd.DataFrame()

    frame = history.copy()
    if "timestamp" not in frame.columns and "date" in frame.columns:
        frame = frame.rename(columns={"date": "timestamp"})

    required = {"timestamp", "open", "high", "low", "close"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    for column in ("open", "high", "low", "close"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "volume" in frame.columns:
        frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce")

    frame = frame.dropna(subset=["timestamp", "open", "high", "low", "close"])
    if frame.empty:
        return frame

    return frame.sort_values("timestamp").reset_index(drop=True)


def validate_intraday_history(history: pd.DataFrame) -> tuple[bool, str]:
    if history is None or history.empty:
        return False, "No historical bars were available."

    try:
        frame = normalize_intraday_history(history)
    except ValueError as exc:
        return False, str(exc)

    if len(frame) < 20:
        return False, "At least 20 intraday bars are required for a meaningful Pulse test."

    deltas = frame["timestamp"].diff().dropna().dt.total_seconds().div(60)
    intraday_deltas = deltas[(deltas > 0) & (deltas <= 90)]
    if intraday_deltas.empty:
        return False, "30-minute OHLC bars are required. The available data looks daily or sparse."

    median_minutes = float(intraday_deltas.median())
    if median_minutes < 20 or median_minutes > 45:
        return False, f"Expected roughly 30-minute bars, but median spacing was {median_minutes:.0f} minutes."

    per_day = frame.groupby(frame["timestamp"].dt.date).size()
    if per_day.median() < 4:
        return False, "The dataset does not contain enough bars per session for 9:30-11:30 Pulse detection."

    return True, "Valid 30-minute intraday history."


def _close_location(row: pd.Series) -> float | None:
    bar_range = float(row["high"] - row["low"])
    if bar_range <= 0:
        return None
    return float((row["close"] - row["low"]) / bar_range)


def detect_pulse_setups(history: pd.DataFrame, config: PulseConfig) -> pd.DataFrame:
    frame = normalize_intraday_history(history)
    rows = []
    for _, row in frame.iterrows():
        timestamp = row["timestamp"]
        bar_time = timestamp.time()
        if not (SETUP_START <= bar_time < SETUP_END):
            continue

        close_location = _close_location(row)
        if close_location is None:
            continue

        direction = None
        if row["close"] > row["open"] and close_location >= config.close_location_threshold:
            direction = "Bullish"
        elif row["close"] < row["open"] and close_location <= (1 - config.close_location_threshold):
            direction = "Bearish"
        if direction is None:
            continue

        rows.append(
            {
                "timestamp": timestamp,
                "session": timestamp.date(),
                "direction": direction,
                "pulse_high": float(row["high"]),
                "pulse_low": float(row["low"]),
                "pulse_size": float(row["high"] - row["low"]),
                "close_location": round(close_location, 3),
            }
        )
    return pd.DataFrame(rows)


def _enhanced_filter(frame: pd.DataFrame, setup: pd.Series) -> bool:
    prior = frame[frame["timestamp"] <= setup["timestamp"]].copy()
    if len(prior) < 21:
        return False
    prior["ema_9"] = prior["close"].ewm(span=9, adjust=False).mean()
    prior["ema_21"] = prior["close"].ewm(span=21, adjust=False).mean()
    latest = prior.iloc[-1]
    if setup["direction"] == "Bullish":
        return bool(latest["close"] > latest["ema_9"] > latest["ema_21"])
    return bool(latest["close"] < latest["ema_9"] < latest["ema_21"])


def _exit_trade(future: pd.DataFrame, setup: pd.Series, max_hold_bars: int) -> dict | None:
    if future.empty:
        return None

    direction = setup["direction"]
    entry = setup["pulse_high"] if direction == "Bullish" else setup["pulse_low"]
    stop = setup["pulse_low"] if direction == "Bullish" else setup["pulse_high"]
    risk = abs(entry - stop)
    if risk <= 0:
        return None

    target = entry + risk if direction == "Bullish" else entry - risk
    entered = False
    held = 0

    for _, bar in future.iterrows():
        if not entered:
            if direction == "Bullish" and bar["high"] >= entry:
                entered = True
            elif direction == "Bearish" and bar["low"] <= entry:
                entered = True
            else:
                continue

        held += 1
        if direction == "Bullish":
            stopped = bar["low"] <= stop
            targeted = bar["high"] >= target
        else:
            stopped = bar["high"] >= stop
            targeted = bar["low"] <= target

        if stopped:
            return {"entry": entry, "exit": stop, "r_multiple": -1.0, "exit_reason": "Stop", "bars_held": held}
        if targeted:
            return {"entry": entry, "exit": target, "r_multiple": 1.0, "exit_reason": "Target", "bars_held": held}
        if held >= max_hold_bars:
            close = float(bar["close"])
            r_multiple = ((close - entry) / risk) if direction == "Bullish" else ((entry - close) / risk)
            return {
                "entry": entry,
                "exit": close,
                "r_multiple": round(float(r_multiple), 3),
                "exit_reason": "Time",
                "bars_held": held,
            }
    return None


def _metrics(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {
            "Trades": 0,
            "Win Rate": 0.0,
            "Average Win R": 0.0,
            "Average Loss R": 0.0,
            "Profit Factor": 0.0,
            "Expectancy R": 0.0,
            "Max Drawdown R": 0.0,
        }

    wins = trades[trades["r_multiple"] > 0]["r_multiple"]
    losses = trades[trades["r_multiple"] < 0]["r_multiple"]
    gross_win = float(wins.sum())
    gross_loss = abs(float(losses.sum()))
    curve = trades["r_multiple"].cumsum()
    drawdown = curve - curve.cummax()
    return {
        "Trades": int(len(trades)),
        "Win Rate": round(float((trades["r_multiple"] > 0).mean() * 100), 2),
        "Average Win R": round(float(wins.mean()) if not wins.empty else 0.0, 2),
        "Average Loss R": round(float(losses.mean()) if not losses.empty else 0.0, 2),
        "Profit Factor": round(gross_win / gross_loss, 2) if gross_loss else round(gross_win, 2),
        "Expectancy R": round(float(trades["r_multiple"].mean()), 3),
        "Max Drawdown R": round(float(drawdown.min()), 2),
    }


def backtest_pulse_symbol(
    history: pd.DataFrame,
    symbol: str,
    config: PulseConfig | None = None,
) -> dict:
    config = config or PulseConfig()
    valid, message = validate_intraday_history(history)
    if not valid:
        return {
            "symbol": symbol,
            "status": "DATA_UNAVAILABLE",
            "reason": message,
            "summary": {"Symbol": symbol, "Status": "DATA_UNAVAILABLE", "Reason": message},
            "setups": pd.DataFrame(),
            "trades": pd.DataFrame(),
        }

    frame = normalize_intraday_history(history)
    setups = detect_pulse_setups(frame, config)
    trade_rows = []
    for _, setup in setups.iterrows():
        if config.enhanced_trend_filter and not _enhanced_filter(frame, setup):
            continue
        future = frame[
            (frame["timestamp"].dt.date == setup["session"])
            & (frame["timestamp"] > setup["timestamp"])
        ]
        result = _exit_trade(future, setup, config.max_hold_bars)
        if result is None:
            continue
        trade_rows.append(
            {
                "symbol": symbol,
                "setup_time": setup["timestamp"],
                "direction": setup["direction"],
                **result,
            }
        )

    trades = pd.DataFrame(trade_rows)
    metrics = _metrics(trades)
    return {
        "symbol": symbol,
        "status": "OK",
        "reason": "Backtest completed on 30-minute OHLC bars.",
        "summary": {"Symbol": symbol, "Status": "OK", **metrics},
        "setups": setups,
        "trades": trades,
    }


def compare_pulse_strategies(
    data_by_symbol: dict[str, pd.DataFrame],
    symbols: tuple[str, ...] = PULSE_SYMBOLS,
    threshold: float = 0.90,
) -> tuple[pd.DataFrame, dict[str, dict]]:
    diagnostics: dict[str, dict] = {}
    rows = []
    for symbol in symbols:
        history = data_by_symbol.get(symbol, pd.DataFrame())
        configs = {
            "Original Pulse": PulseConfig(close_location_threshold=threshold),
            "Enhanced Pulse": PulseConfig(
                close_location_threshold=threshold,
                enhanced_trend_filter=True,
            ),
        }
        for strategy_name, config in configs.items():
            result = backtest_pulse_symbol(history, symbol, config)
            result["summary"]["Strategy"] = strategy_name
            rows.append(result["summary"])
            diagnostics[f"{symbol}-{strategy_name}"] = result
    return pd.DataFrame(rows), diagnostics
