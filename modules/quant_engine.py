"""Daily-return research with explicit timing, costs and chronological validation."""
from __future__ import annotations

import numpy as np
import pandas as pd


def validate_prices(frame):
    frame = frame.copy()
    if "date" not in frame:
        raise ValueError("CSV needs a date column and one adjusted-close column per asset.")
    dates = pd.to_datetime(frame.pop("date"), errors="coerce", utc=True)
    if dates.isna().any() or dates.dt.normalize().duplicated().any():
        raise ValueError("Dates must be valid and unique, with one row per trading day.")
    frame.index = pd.DatetimeIndex(dates).tz_convert(None).normalize()
    frame = frame.apply(pd.to_numeric, errors="coerce").sort_index()
    if frame.shape[1] < 1 or len(frame) < 80:
        raise ValueError("Supply at least 80 daily observations and one asset.")
    if not np.isfinite(frame.to_numpy()).all() or (frame <= 0).any().any():
        raise ValueError("Prices must be positive and finite. Align asset histories before uploading; missing prices are not filled.")
    if len(frame) > 10000 or frame.shape[1] > 30:
        raise ValueError("Research limit: 10,000 dates and 30 assets per upload.")
    return frame


def demo_prices():
    rng = np.random.default_rng(51)
    dates = pd.bdate_range("2020-01-02", periods=1500)
    market = rng.normal(.00025, .01, len(dates))
    market[600:660] -= .003
    data = {}
    for name, beta, noise in [("Equity", 1, .004), ("Growth", 1.2, .008), ("Bonds", -.15, .004), ("Gold", .1, .008)]:
        returns = beta * market + rng.normal(.00005, noise, len(dates))
        data[name] = 100 * np.cumprod(1 + returns)
    return pd.DataFrame(data, index=dates)


def metrics(returns, rf=0.0):
    r = pd.Series(returns).dropna().astype(float)
    if len(r) < 2 or not np.isfinite(r).all() or (r <= -1).any():
        raise ValueError("Metrics require two or more finite returns greater than -100%.")
    wealth = (1 + r).cumprod()
    dd = wealth / wealth.cummax().clip(lower=1) - 1
    excess = r - ((1 + rf)**(1/252) - 1)
    vol = r.std(ddof=1) * np.sqrt(252)
    downside = np.sqrt(np.mean(np.minimum(excess, 0)**2)) * np.sqrt(252)
    cagr = wealth.iloc[-1]**(252/len(r)) - 1
    losses = -r.to_numpy()
    var = float(np.quantile(losses, .95))
    es = float(losses[losses >= var].mean())
    return {"CAGR": cagr, "Annual volatility": vol,
            "Sharpe": excess.mean()*252/vol if vol > 1e-12 else np.nan,
            "Sortino": excess.mean()*252/downside if downside > 1e-12 else np.nan,
            "Max drawdown": dd.min(), "Calmar": cagr/abs(dd.min()) if dd.min() < 0 else np.nan,
            "Daily VaR 95%": var, "Daily ES 95%": es,
            "Positive days": (r > 0).mean(), "Total return": wealth.iloc[-1]-1,
            "Skew": r.skew(), "Excess kurtosis": r.kurt()}


def weights(prices, method="Momentum", lookback=60):
    returns = prices.pct_change(fill_method=None)
    if method == "Equal weight":
        target = pd.DataFrame(1/prices.shape[1], index=prices.index, columns=prices.columns)
    elif method == "Inverse volatility":
        inverse = 1 / returns.rolling(lookback).std().replace(0, np.nan)
        target = inverse.div(inverse.sum(axis=1), axis=0).fillna(0)
    else:
        signal = (prices / prices.shift(lookback) - 1) > 0
        # Fixed sleeves: assets without a positive signal remain in cash.
        target = signal.astype(float) / prices.shape[1]
    # Signals known at close t-2 determine holdings over close t-1 -> close t.
    # A full extra bar avoids assuming a fill at the signal's closing price.
    return target.shift(2).fillna(0)


def apply_costs(prices, held, cost_bps=5.0):
    r = prices.pct_change(fill_method=None).fillna(0)
    prior = held.shift(1).fillna(0)
    prior_r = r.shift(1).fillna(0)
    # Drift last period's target to the next rebalance, including residual cash.
    drift = prior * (1 + prior_r)
    drift = drift.div(1 + (prior * prior_r).sum(axis=1), axis=0)
    turnover = (held - drift).abs().sum(axis=1)
    gross = (held * r).sum(axis=1)
    return pd.DataFrame({"Gross": gross, "Cost": turnover * cost_bps/10000,
                         "Net": gross - turnover * cost_bps/10000,
                         "Turnover": turnover, "Exposure": held.sum(axis=1)})


def walk_forward(prices, train=252, test=63, cost_bps=5., rf=0.):
    candidates = {f"Momentum {n}": weights(prices, "Momentum", n) for n in (20, 60, 120)}
    start = train + 122
    if len(prices) < start + 20:
        raise ValueError(f"Walk-forward needs at least {start + 20} observations for this training window.")
    held = pd.DataFrame(0., index=prices.index, columns=prices.columns)
    folds = []
    for i in range(start, len(prices), test):
        end = min(i+test, len(prices))
        if end-i < 20:
            break
        scores = {}
        for name, w in candidates.items():
            # Each training window is scored independently, from cash.
            training_weights = w.iloc[i-train-1:i].copy()
            training_weights.iloc[0] = 0
            sample = apply_costs(prices.iloc[i-train-1:i], training_weights, cost_bps).iloc[1:]
            score = metrics(sample.Net, rf)["Sharpe"]
            scores[name] = score if np.isfinite(score) else -np.inf
        chosen = max(scores, key=scores.get)
        held.iloc[i:end] = candidates[chosen].iloc[i:end]
        folds.append({"Train start": prices.index[i-train], "Train end": prices.index[i-1],
                      "Test start": prices.index[i], "Test end": prices.index[end-1],
                      "Selected": chosen, "Train Sharpe": scores[chosen], "start": i, "end": end})
    ledger = apply_costs(prices, held, cost_bps)
    for fold in folds:
        m = metrics(ledger.Net.iloc[fold["start"]:fold["end"]], rf)
        fold.update({"Test return": m["Total return"], "Test Sharpe": m["Sharpe"], "Test max DD": m["Max drawdown"]})
    end = folds[-1]["end"]
    return ledger.iloc[start:end], pd.DataFrame(folds).drop(columns=["start", "end"]), held.iloc[start:end]


def bootstrap(returns, days=252, paths=1000, block=10, seed=51):
    r = np.asarray(returns, dtype=float)
    if len(r) < block or not np.isfinite(r).all() or (r <= -1).any():
        raise ValueError("Bootstrap requires valid returns and at least one full block.")
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, len(r)-block+1, size=(paths, int(np.ceil(days/block))))
    indices = (starts[..., None] + np.arange(block)).reshape(paths, -1)[:, :days]
    wealth = np.column_stack([np.ones(paths), np.cumprod(1+r[indices], axis=1)])
    dd = wealth / np.maximum.accumulate(wealth, axis=1) - 1
    return wealth, dd.min(axis=1)


def risk_contributions(returns, allocation):
    # Diagonal shrinkage provides a more stable covariance estimate.
    sample = returns.cov().to_numpy() * 252
    cov = .8*sample + .2*np.diag(np.diag(sample))
    w = np.asarray(allocation)
    vol = np.sqrt(w @ cov @ w)
    contribution = w * (cov @ w) / vol if vol > 1e-12 else np.zeros(len(w))
    return pd.DataFrame({"Weight": w, "Vol contribution": contribution,
                         "Risk share": contribution/vol if vol > 1e-12 else np.zeros(len(w))}, index=returns.columns)


def benchmark_regression(strategy, benchmark, rf=0.):
    data = pd.concat([strategy.rename("strategy"), benchmark.rename("benchmark")], axis=1).dropna()
    cash = (1+rf)**(1/252)-1
    x, y = data.benchmark.to_numpy()-cash, data.strategy.to_numpy()-cash
    if len(data) < 30 or x.std() < 1e-12:
        return {"Annualized alpha (OLS)": np.nan, "Beta": np.nan, "R squared": np.nan}
    design = np.column_stack([np.ones(len(x)), x])
    coef = np.linalg.lstsq(design, y, rcond=None)[0]
    residual = y - design @ coef
    return {"Annualized alpha (OLS)": coef[0]*252, "Beta": coef[1],
            "R squared": 1 - np.sum(residual**2)/np.sum((y-y.mean())**2) if y.std() > 1e-12 else np.nan}
