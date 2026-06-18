from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd


SYMBOLS = ["SPY", "QQQ", "IWM", "DIA", "TLT", "GLD", "NVDA", "MSFT", "AAPL"]


def get_market_pulse() -> list[dict]:
    return [
        {"symbol": "SPY", "signal": "Constructive trend", "score": 78, "change": 0.42},
        {"symbol": "QQQ", "signal": "Leadership expanding", "score": 82, "change": 0.65},
        {"symbol": "IWM", "signal": "Rotation watch", "score": 57, "change": -0.12},
        {"symbol": "TLT", "signal": "Rates pressure easing", "score": 61, "change": 0.24},
        {"symbol": "GLD", "signal": "Defensive bid", "score": 66, "change": 0.31},
    ]


def get_rotation_table() -> pd.DataFrame:
    rows = [
        ("Technology", "XLK", 88, "Leading", 1.8),
        ("Communication", "XLC", 74, "Improving", 1.1),
        ("Financials", "XLF", 68, "Improving", 0.7),
        ("Industrials", "XLI", 62, "Neutral", 0.2),
        ("Utilities", "XLU", 41, "Lagging", -0.9),
        ("Energy", "XLE", 47, "Lagging", -0.5),
    ]
    return pd.DataFrame(rows, columns=["Group", "Symbol", "Score", "Phase", "Rel Strength"])


def get_scanner_results() -> pd.DataFrame:
    rows = [
        ("NVDA", "Momentum continuation", 91, 2.7, "High"),
        ("MSFT", "Quality pullback", 79, 0.8, "Medium"),
        ("AMZN", "Base breakout watch", 76, 1.2, "Medium"),
        ("AMD", "High beta rebound", 72, 3.1, "High"),
        ("COST", "Defensive strength", 69, 0.4, "Low"),
    ]
    return pd.DataFrame(rows, columns=["Symbol", "Setup", "Score", "ATR %", "Risk"])


def get_mock_price_history(symbol: str = "SPY", periods: int = 90) -> pd.DataFrame:
    rng = np.random.default_rng(abs(hash(symbol)) % 2**32)
    start = date.today() - timedelta(days=periods)
    dates = pd.date_range(start=start, periods=periods, freq="D")
    returns = rng.normal(loc=0.0008, scale=0.012, size=periods)
    prices = 100 * (1 + returns).cumprod()
    return pd.DataFrame({"date": dates, "close": prices})
