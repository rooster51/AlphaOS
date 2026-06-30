from __future__ import annotations

import pandas as pd

from modules.public_data import (
    can_access_public_portfolio,
    get_public_portfolio,
    get_public_price_history,
    get_public_quotes,
    has_public_config,
)


MARKET_SYMBOLS = ["SPY", "QQQ", "IWM", "DIA", "TLT", "GLD", "NVDA", "MSFT", "AAPL"]

SECTOR_ETFS = {
    "Technology": "XLK",
    "Communication": "XLC",
    "Consumer Discretionary": "XLY",
    "Financials": "XLF",
    "Industrials": "XLI",
    "Health Care": "XLV",
    "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Materials": "XLB",
}

SCANNER_SYMBOLS = (
    "AAPL",
    "AMD",
    "AMZN",
    "COST",
    "GOOGL",
    "META",
    "MSFT",
    "NVDA",
    "TSLA",
)


def _empty_history() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["date", "open", "high", "low", "close", "volume"]
    )


def _clamp_score(value: float) -> int:
    return int(round(max(0, min(100, value))))


def _history_metrics(history: pd.DataFrame) -> dict | None:
    if history.empty or len(history) < 6:
        return None

    frame = history.sort_values("date").copy()
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["high", "low", "close"])
    if len(frame) < 6:
        return None

    close = frame["close"]
    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    lookback_20 = min(20, len(frame) - 1)
    return_5d = ((close.iloc[-1] / close.iloc[-6]) - 1) * 100
    return_20d = ((close.iloc[-1] / close.iloc[-(lookback_20 + 1)]) - 1) * 100
    sma_20 = close.tail(20).mean()
    atr_14 = true_range.tail(14).mean()
    average_volume = frame["volume"].tail(20).mean()
    volume_ratio = (
        frame["volume"].iloc[-1] / average_volume
        if average_volume and not pd.isna(average_volume)
        else None
    )
    prior_20d_high = frame["high"].iloc[:-1].tail(20).max()

    return {
        "last": float(close.iloc[-1]),
        "return_5d": float(return_5d),
        "return_20d": float(return_20d),
        "sma_20": float(sma_20),
        "atr_pct": float((atr_14 / close.iloc[-1]) * 100),
        "volume_ratio": float(volume_ratio) if volume_ratio is not None else None,
        "prior_20d_high": float(prior_20d_high),
    }


def _trend_score(metrics: dict) -> int:
    above_average = 10 if metrics["last"] >= metrics["sma_20"] else -10
    return _clamp_score(
        50
        + above_average
        + (metrics["return_5d"] * 2)
        + metrics["return_20d"]
    )


def _trend_signal(score: int) -> str:
    if score >= 70:
        return "Strong uptrend"
    if score >= 58:
        return "Constructive"
    if score <= 30:
        return "Strong downtrend"
    if score <= 42:
        return "Weakening"
    return "Neutral"


def market_pulse() -> tuple[list[dict], str]:
    if not has_public_config():
        return [], "Public.com not configured"

    try:
        symbols = tuple(MARKET_SYMBOLS[:5])
        quotes = {item["symbol"]: item for item in get_public_quotes(symbols)}
        rows = []
        for symbol in symbols:
            metrics = _history_metrics(get_public_price_history(symbol))
            if metrics is None:
                continue
            quote = quotes.get(symbol, {})
            last = quote.get("last") or metrics["last"]
            score = _trend_score({**metrics, "last": last})
            rows.append(
                {
                    "symbol": symbol,
                    "last": last,
                    "change": quote.get("change_pct"),
                    "volume": quote.get("volume"),
                    "signal": _trend_signal(score),
                    "score": score,
                    "5D %": round(metrics["return_5d"], 2),
                    "20D %": round(metrics["return_20d"], 2),
                }
            )
        return rows, "Public.com live + historical"
    except Exception:
        return [], "Public.com unavailable"


def price_history(symbol: str) -> tuple[pd.DataFrame, str]:
    if not has_public_config():
        return _empty_history(), "Public.com not configured"
    try:
        history = get_public_price_history(symbol)
        if not history.empty:
            return history, "Public.com historical"
    except Exception:
        pass
    return _empty_history(), "Public.com unavailable"


def symbol_analysis(symbol: str) -> tuple[dict | None, str]:
    symbol = symbol.strip().upper()
    if not symbol:
        return None, "Enter a symbol"
    if not has_public_config():
        return None, "Public.com not configured"

    try:
        history = get_public_price_history(symbol)
        metrics = _history_metrics(history)
        if metrics is None:
            return None, "Insufficient Public historical data"

        quotes = get_public_quotes((symbol,))
        quote = quotes[0] if quotes else {}
        last = quote.get("last") or metrics["last"]
        metrics = {**metrics, "last": last}
        score = _trend_score(metrics)
        outlook = "Bullish" if score >= 58 else "Bearish" if score <= 42 else "Neutral"
        volatility = (
            "High"
            if metrics["atr_pct"] >= 3.5
            else "Low"
            if metrics["atr_pct"] <= 1.5
            else "Normal"
        )
        return (
            {
                "symbol": symbol,
                "last": last,
                "change_pct": quote.get("change_pct"),
                "return_5d": round(metrics["return_5d"], 2),
                "return_20d": round(metrics["return_20d"], 2),
                "atr_pct": round(metrics["atr_pct"], 2),
                "volume_ratio": (
                    round(metrics["volume_ratio"], 2)
                    if metrics["volume_ratio"] is not None
                    else None
                ),
                "trend_score": score,
                "outlook": outlook,
                "volatility": volatility,
            },
            "Public.com live + historical",
        )
    except Exception:
        return None, "Public.com unavailable"


def brokerage_positions(user: dict | None) -> tuple[list[dict], dict, str]:
    if has_public_config() and can_access_public_portfolio(user):
        try:
            portfolio = get_public_portfolio()
            return portfolio["positions"], portfolio, "Public.com Live"
        except Exception:
            pass
    return [], {}, "Unavailable"


def rotation_table() -> tuple[pd.DataFrame, str]:
    columns = [
        "Group",
        "Symbol",
        "Last",
        "5D %",
        "20D %",
        "Rel Strength vs SPY %",
        "Score",
        "Phase",
    ]
    if not has_public_config():
        return pd.DataFrame(columns=columns), "Public.com not configured"

    try:
        symbols = tuple(SECTOR_ETFS.values())
        quotes = {item["symbol"]: item for item in get_public_quotes(symbols)}
        benchmark = _history_metrics(get_public_price_history("SPY"))
        if benchmark is None:
            return pd.DataFrame(columns=columns), "Public.com unavailable"

        rows = []
        for group, symbol in SECTOR_ETFS.items():
            metrics = _history_metrics(get_public_price_history(symbol))
            if metrics is None:
                continue
            relative_strength = metrics["return_20d"] - benchmark["return_20d"]
            rows.append(
                {
                    "Group": group,
                    "Symbol": symbol,
                    "Last": quotes.get(symbol, {}).get("last") or metrics["last"],
                    "5D %": round(metrics["return_5d"], 2),
                    "20D %": round(metrics["return_20d"], 2),
                    "Rel Strength vs SPY %": round(relative_strength, 2),
                    "_composite": relative_strength + (metrics["return_5d"] * 0.5),
                }
            )

        frame = pd.DataFrame(rows)
        if frame.empty:
            return pd.DataFrame(columns=columns), "Public.com unavailable"
        frame["Score"] = (frame["_composite"].rank(pct=True) * 100).round().astype(int)
        frame["Phase"] = frame["Score"].map(
            lambda score: (
                "Leading"
                if score >= 75
                else "Improving"
                if score >= 50
                else "Weakening"
                if score >= 25
                else "Lagging"
            )
        )
        return (
            frame.drop(columns="_composite").sort_values("Score", ascending=False),
            "Public.com live + historical",
        )
    except Exception:
        return pd.DataFrame(columns=columns), "Public.com unavailable"


def _scanner_setup(metrics: dict) -> str:
    breakout_distance = (
        (metrics["last"] / metrics["prior_20d_high"]) - 1
    ) * 100
    if breakout_distance >= 0:
        return "20-day breakout"
    if metrics["return_20d"] > 0 and metrics["last"] >= metrics["sma_20"]:
        return "Uptrend continuation"
    if metrics["return_20d"] > 0 and metrics["last"] < metrics["sma_20"]:
        return "Pullback in uptrend"
    if metrics["return_5d"] > 0:
        return "Short-term rebound"
    return "Weak trend"


def scanner_results() -> tuple[pd.DataFrame, str]:
    columns = [
        "Symbol",
        "Last",
        "Change %",
        "Setup",
        "Score",
        "ATR %",
        "Volume Ratio",
        "Risk",
    ]
    if not has_public_config():
        return pd.DataFrame(columns=columns), "Public.com not configured"

    try:
        quotes = {
            item["symbol"]: item
            for item in get_public_quotes(tuple(SCANNER_SYMBOLS))
        }
        rows = []
        for symbol in SCANNER_SYMBOLS:
            metrics = _history_metrics(get_public_price_history(symbol))
            if metrics is None:
                continue
            quote = quotes.get(symbol, {})
            last = quote.get("last") or metrics["last"]
            score = _trend_score({**metrics, "last": last})
            volume_ratio = metrics["volume_ratio"]
            if volume_ratio is not None:
                score = _clamp_score(score + ((volume_ratio - 1) * 8))
            atr_pct = metrics["atr_pct"]
            risk = "High" if atr_pct >= 4 else "Medium" if atr_pct >= 2 else "Low"
            rows.append(
                {
                    "Symbol": symbol,
                    "Last": last,
                    "Change %": quote.get("change_pct"),
                    "Setup": _scanner_setup({**metrics, "last": last}),
                    "Score": score,
                    "ATR %": round(atr_pct, 2),
                    "Volume Ratio": (
                        round(volume_ratio, 2) if volume_ratio is not None else None
                    ),
                    "Risk": risk,
                }
            )
        frame = pd.DataFrame(rows, columns=columns)
        if frame.empty:
            return frame, "Public.com unavailable"
        return (
            frame.sort_values("Score", ascending=False),
            "Public.com live + historical",
        )
    except Exception:
        return pd.DataFrame(columns=columns), "Public.com unavailable"
