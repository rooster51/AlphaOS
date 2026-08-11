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

    lookback_5 = min(5, len(frame) - 1)
    lookback_20 = min(20, len(frame) - 1)
    lookback_60 = min(60, len(frame) - 1)
    lookback_120 = min(120, len(frame) - 1)
    return_5d = ((close.iloc[-1] / close.iloc[-(lookback_5 + 1)]) - 1) * 100
    return_20d = ((close.iloc[-1] / close.iloc[-(lookback_20 + 1)]) - 1) * 100
    return_60d = ((close.iloc[-1] / close.iloc[-(lookback_60 + 1)]) - 1) * 100
    return_120d = ((close.iloc[-1] / close.iloc[-(lookback_120 + 1)]) - 1) * 100
    sma_20 = close.tail(20).mean()
    sma_50 = close.tail(min(50, len(close))).mean()
    sma_200 = close.tail(min(200, len(close))).mean()
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
        "return_60d": float(return_60d),
        "return_120d": float(return_120d),
        "sma_20": float(sma_20),
        "sma_50": float(sma_50),
        "sma_200": float(sma_200),
        "atr_pct": float((atr_14 / close.iloc[-1]) * 100),
        "volume_ratio": float(volume_ratio) if volume_ratio is not None else None,
        "prior_20d_high": float(prior_20d_high),
    }


def _normalized_horizon(horizon: str | None) -> str:
    value = (horizon or "Swing (2-8 weeks)").upper()
    if "DAY" in value:
        return "day"
    if "INTERMEDIATE" in value or "MONTHLY" in value or "POSITION" in value:
        return "intermediate"
    if "LONG" in value or "LEAPS" in value:
        return "long"
    return "swing"


def _trend_score(metrics: dict, horizon: str | None = None) -> int:
    normalized = _normalized_horizon(horizon)
    if normalized == "intermediate":
        above_average = 10 if metrics["last"] >= metrics["sma_50"] else -10
        return _clamp_score(
            50
            + above_average
            + (metrics["return_20d"] * 1.25)
            + (metrics["return_60d"] * 0.75)
        )
    if normalized == "long":
        above_average = 10 if metrics["last"] >= metrics["sma_200"] else -10
        return _clamp_score(
            50
            + above_average
            + (metrics["return_60d"] * 0.8)
            + (metrics["return_120d"] * 0.5)
        )
    above_average = 10 if metrics["last"] >= metrics["sma_20"] else -10
    return _clamp_score(
        50
        + above_average
        + (metrics["return_5d"] * 2)
        + metrics["return_20d"]
    )


def _day_trend_score(metrics: dict, quote: dict, market_change_pct: float | None = None) -> int:
    quote_change = quote.get("change_pct")
    quote_change = float(quote_change) if quote_change is not None else 0.0
    market_change = float(market_change_pct) if market_change_pct is not None else 0.0
    volume_ratio = metrics.get("volume_ratio")
    volume_bonus = 0.0
    if volume_ratio is not None:
        volume_bonus = min(8.0, max(-4.0, (float(volume_ratio) - 1.0) * 8.0))
    above_average = 4 if metrics["last"] >= metrics["sma_20"] else -4
    return _clamp_score(
        50
        + (quote_change * 12)
        + (market_change * 8)
        + (metrics["return_5d"] * 0.75)
        + above_average
        + volume_bonus
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


def _outlook_from_score(score: int) -> str:
    if score >= 56:
        return "Bullish"
    if score <= 44:
        return "Bearish"
    return "Neutral"


def _timeframe_label(horizon: str | None) -> str:
    normalized = _normalized_horizon(horizon)
    if normalized == "day":
        return "Day trend: live quote, SPY/QQQ alignment, 5-day context, volume, and 20-day location"
    if normalized == "intermediate":
        return "Intermediate trend: 20-day and 60-day returns with 50-day moving-average location"
    if normalized == "long":
        return "Long-term trend: 60-day and 120-day returns with 200-day moving-average location"
    return "Swing trend: 5-day and 20-day returns with 20-day moving-average location"


def _market_change(quotes: dict[str, dict]) -> float | None:
    values = [
        float(quotes[symbol]["change_pct"])
        for symbol in ("SPY", "QQQ")
        if symbol in quotes and quotes[symbol].get("change_pct") is not None
    ]
    if not values:
        return None
    return sum(values) / len(values)


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
            day_score = _day_trend_score({**metrics, "last": last}, quote)
            rows.append(
                {
                    "symbol": symbol,
                    "last": last,
                    "change": quote.get("change_pct"),
                    "volume": quote.get("volume"),
                    "day_bias": _outlook_from_score(day_score),
                    "signal": _trend_signal(score),
                    "score": score,
                    "5D %": round(metrics["return_5d"], 2),
                    "20D %": round(metrics["return_20d"], 2),
                }
            )
        return rows, "Public.com live + historical"
    except Exception:
        return [], "Public.com unavailable"


def dashboard_pulse() -> tuple[list[dict], str]:
    if not has_public_config():
        return [], "Public.com not configured"

    symbols = tuple(MARKET_SYMBOLS[:4])
    try:
        rows = []
        for quote in get_public_quotes(symbols):
            change_pct = quote.get("change_pct")
            signal = (
                "Positive"
                if change_pct is not None and change_pct > 0
                else "Negative"
                if change_pct is not None and change_pct < 0
                else "Flat"
            )
            score = (
                _clamp_score(50 + (float(change_pct) * 5))
                if change_pct is not None
                else 50
            )
            rows.append(
                {
                    "symbol": quote["symbol"],
                    "last": quote.get("last"),
                    "change": change_pct,
                    "signal": signal,
                    "score": score,
                }
            )
        return rows, "Public.com live quotes"
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


def symbol_analysis(symbol: str, horizon: str | None = None) -> tuple[dict | None, str]:
    symbol = symbol.strip().upper()
    if not symbol:
        return None, "Enter a symbol"
    if not has_public_config():
        return None, "Public.com not configured"

    try:
        quote_symbols = tuple(dict.fromkeys((symbol, "SPY", "QQQ")))
        quote_rows = get_public_quotes(quote_symbols)
        quote_map = {row["symbol"]: row for row in quote_rows}
        quote = quote_map.get(symbol, quote_rows[0] if quote_rows else {})
        market_change = _market_change(quote_map)
        try:
            history = get_public_price_history(symbol)
            metrics = _history_metrics(history)
        except Exception:
            metrics = None
        if metrics is None and quote.get("last") is None:
            return None, "Insufficient Public historical data"

        if metrics is None:
            last = quote["last"]
            metrics = {
                "last": last,
                "return_5d": 0.0,
                "return_20d": 0.0,
                "return_60d": 0.0,
                "return_120d": 0.0,
                "atr_pct": 0.0,
                "volume_ratio": None,
                "sma_20": last,
                "sma_50": last,
                "sma_200": last,
                "prior_20d_high": last,
            }
            score = 50
            day_score = _day_trend_score(metrics, quote, market_change)
            outlook = _outlook_from_score(day_score) if _normalized_horizon(horizon) == "day" else "Neutral"
            volatility = "Normal"
            return (
                {
                    "symbol": symbol,
                    "last": last,
                    "change_pct": quote.get("change_pct"),
                    "return_5d": 0.0,
                    "return_20d": 0.0,
                    "return_60d": 0.0,
                    "return_120d": 0.0,
                    "atr_pct": 0.0,
                    "volume_ratio": None,
                    "trend_score": score,
                    "day_score": day_score,
                    "day_bias": _outlook_from_score(day_score),
                    "market_change_pct": market_change,
                    "outlook": outlook,
                    "timeframe_model": _timeframe_label(horizon),
                    "volatility": volatility,
                },
                "Public.com live quote",
            )

        last = quote.get("last") or metrics["last"]
        metrics = {**metrics, "last": last}
        score = _trend_score(metrics, horizon)
        swing_score = _trend_score(metrics, "Swing (2-8 weeks)")
        swing_outlook = _outlook_from_score(swing_score)
        day_score = _day_trend_score(metrics, quote, market_change)
        day_outlook = _outlook_from_score(day_score)
        outlook = day_outlook if _normalized_horizon(horizon) == "day" else _outlook_from_score(score)
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
                "return_60d": round(metrics["return_60d"], 2),
                "return_120d": round(metrics["return_120d"], 2),
                "atr_pct": round(metrics["atr_pct"], 2),
                "volume_ratio": (
                    round(metrics["volume_ratio"], 2)
                    if metrics["volume_ratio"] is not None
                    else None
                ),
                "trend_score": score,
                "day_score": day_score,
                "day_bias": day_outlook,
                "swing_outlook": swing_outlook,
                "market_change_pct": (
                    round(market_change, 2) if market_change is not None else None
                ),
                "outlook": outlook,
                "timeframe_model": _timeframe_label(horizon),
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
