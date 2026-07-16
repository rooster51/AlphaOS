from __future__ import annotations

import pandas as pd


def _prep_history(history: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame()
    frame = history.sort_values("date").copy()
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["high", "low", "close"])
    if len(frame) < 30:
        return pd.DataFrame()

    close = frame["close"]
    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - prev_close).abs(),
            (frame["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    frame["return_1d"] = close.pct_change()
    frame["return_5d"] = close.pct_change(5)
    frame["return_20d"] = close.pct_change(20)
    frame["sma_20"] = close.rolling(20).mean()
    frame["atr_14"] = true_range.rolling(14).mean()
    frame["atr_pct"] = frame["atr_14"] / close
    frame["avg_volume_20"] = frame["volume"].rolling(20).mean()
    frame["volume_ratio"] = frame["volume"] / frame["avg_volume_20"]
    return frame.dropna(
        subset=["return_5d", "return_20d", "sma_20", "atr_pct"]
    ).reset_index(drop=True)


def reversal_diagnostics(history: pd.DataFrame, outlook: str) -> list[dict]:
    frame = _prep_history(history)
    if frame.empty:
        return [
            {
                "check": "History",
                "status": "Unavailable",
                "detail": "Not enough historical bars to score reversal risk.",
            }
        ]

    latest = frame.iloc[-1]
    prior = frame.iloc[-2]
    checks: list[dict] = []

    direction = 1 if outlook == "Bullish" else -1 if outlook == "Bearish" else 0
    one_day_move = float(latest["return_1d"] or 0)
    atr_pct = float(latest["atr_pct"] or 0)
    extension = (
        abs(float(latest["close"] - latest["sma_20"])) / float(latest["close"])
        if latest["close"]
        else 0
    )
    volume_ratio = float(latest["volume_ratio"] or 0)

    if direction and one_day_move * direction > atr_pct * 1.25:
        checks.append(
            {
                "check": "Chase risk",
                "status": "Warning",
                "detail": "The signal is entering after a move larger than 1.25x ATR in the trade direction.",
            }
        )
    else:
        checks.append(
            {
                "check": "Chase risk",
                "status": "Pass",
                "detail": "The latest daily move is not unusually stretched versus ATR.",
            }
        )

    if extension > atr_pct * 2.5:
        checks.append(
            {
                "check": "Mean-reversion risk",
                "status": "Warning",
                "detail": "Price is extended from the 20-day average, increasing snapback risk.",
            }
        )
    else:
        checks.append(
            {
                "check": "Mean-reversion risk",
                "status": "Pass",
                "detail": "Price is not extremely extended from the 20-day average.",
            }
        )

    if direction and float(latest["return_5d"]) * direction < 0:
        checks.append(
            {
                "check": "Short-term alignment",
                "status": "Warning",
                "detail": "Five-day momentum conflicts with the suggested trade direction.",
            }
        )
    else:
        checks.append(
            {
                "check": "Short-term alignment",
                "status": "Pass",
                "detail": "Recent momentum does not conflict with the suggested direction.",
            }
        )

    if direction and volume_ratio < 0.8 and abs(one_day_move) > abs(float(prior["return_1d"] or 0)):
        checks.append(
            {
                "check": "Volume confirmation",
                "status": "Warning",
                "detail": "The move has weak volume confirmation versus the 20-day average.",
            }
        )
    else:
        checks.append(
            {
                "check": "Volume confirmation",
                "status": "Pass",
                "detail": "Volume confirmation is not a major warning on the latest bar.",
            }
        )

    return checks


def backtest_signal(
    history: pd.DataFrame,
    outlook: str,
    hold_days: int = 5,
    max_rows: int = 80,
) -> dict:
    frame = _prep_history(history)
    if frame.empty or len(frame) < hold_days + 25:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "average_return": 0.0,
            "profit_factor": 0.0,
            "max_loss": 0.0,
            "results": pd.DataFrame(),
        }

    direction = 1 if outlook == "Bullish" else -1 if outlook == "Bearish" else 0
    if direction == 0:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "average_return": 0.0,
            "profit_factor": 0.0,
            "max_loss": 0.0,
            "results": pd.DataFrame(),
        }

    rows = []
    usable = frame.iloc[:-hold_days].tail(max_rows)
    for idx, row in usable.iterrows():
        bullish_setup = (
            row["close"] >= row["sma_20"]
            and row["return_5d"] > 0
            and row["return_20d"] > 0
        )
        bearish_setup = (
            row["close"] <= row["sma_20"]
            and row["return_5d"] < 0
            and row["return_20d"] < 0
        )
        if (direction == 1 and not bullish_setup) or (
            direction == -1 and not bearish_setup
        ):
            continue

        entry_price = float(row["close"])
        exit_row = frame.iloc[idx + hold_days]
        exit_price = float(exit_row["close"])
        trade_return = ((exit_price / entry_price) - 1) * direction
        rows.append(
            {
                "Entry Date": row["date"],
                "Exit Date": exit_row["date"],
                "Entry": entry_price,
                "Exit": exit_price,
                "Return %": round(trade_return * 100, 2),
            }
        )

    results = pd.DataFrame(rows)
    if results.empty:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "average_return": 0.0,
            "profit_factor": 0.0,
            "max_loss": 0.0,
            "results": results,
        }

    returns = pd.to_numeric(results["Return %"], errors="coerce")
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    gross_profit = wins.sum()
    gross_loss = abs(losses.sum())
    return {
        "trades": int(len(results)),
        "win_rate": round(float((len(wins) / len(results)) * 100), 1),
        "average_return": round(float(returns.mean()), 2),
        "profit_factor": round(float(gross_profit / gross_loss), 2)
        if gross_loss
        else 0.0,
        "max_loss": round(float(returns.min()), 2),
        "results": results.sort_values("Entry Date", ascending=False),
    }
