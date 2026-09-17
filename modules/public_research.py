"""Validate actual Public daily observations without manufacturing missing history."""
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


def align_daily_histories(histories, as_of=None):
    as_of = as_of or datetime.now(ZoneInfo("America/New_York")).date()
    columns, audit = [], []
    for symbol, history in histories.items():
        if history.empty or not {"date", "close"}.issubset(history.columns):
            raise ValueError(f"{symbol}: Public returned no daily close history.")
        dates = pd.to_datetime(history['date'], utc=True, errors='coerce')
        if dates.isna().any():
            raise ValueError(f"{symbol}: invalid bar timestamps.")
        # Daily bars are labeled by their UTC calendar date; no intraday resampling.
        days = dates.dt.tz_convert(None).dt.normalize()
        values = pd.to_numeric(history['close'], errors='coerce')
        series = pd.Series(values.to_numpy(), index=pd.DatetimeIndex(days), name=symbol).sort_index()
        series = series[series.index.date < as_of]  # Conservatively exclude today's bar.
        if series.index.duplicated().any():
            raise ValueError(f"{symbol}: multiple bars per date; daily aggregation was not honored.")
        if series.empty or not np.isfinite(series).all() or (series <= 0).any():
            raise ValueError(f"{symbol}: missing, nonfinite, or nonpositive closes.")
        spacing = series.index.to_series().diff().dt.days.dropna()
        if not spacing.empty and (spacing.median() > 3 or spacing.max() > 7):
            raise ValueError(f"{symbol}: history is sparse or not daily; research was stopped.")
        columns.append(series)
        audit.append({"Symbol":symbol,"Provider bars":len(history),"Completed daily bars":len(series),
                      "First date":str(series.index[0].date()),"Last date":str(series.index[-1].date())})
    if not columns:
        raise ValueError("Select at least one research symbol.")
    outer = pd.concat(columns,axis=1)
    aligned = outer.dropna()
    if len(aligned) < 80:
        raise ValueError(f"Only {len(aligned)} common daily observations; at least 80 are needed.")
    for item in audit:
        item['Common observations'] = len(aligned)
        item['Excluded during alignment'] = item['Completed daily bars']-len(aligned)
    return aligned, audit


def load_public_research(symbols, period):
    from modules.public_data import get_public_research_bars, get_public_quotes
    histories = {}
    for symbol in symbols:
        try:
            histories[symbol] = get_public_research_bars(symbol, period)
        except Exception as exc:
            # Never expose credentials, headers, account IDs or raw server responses.
            raise ValueError(f"Public history unavailable for {symbol} ({type(exc).__name__}). Check API access in Settings or try another period.") from None
    prices, audit = align_daily_histories(histories)
    try:
        quotes = get_public_quotes(tuple(symbols))
        quotes = [{"Symbol":q['symbol'],"Last":q['last'],"Quote timestamp":str(q.get('updated_at') or 'Unavailable')} for q in quotes]
    except Exception:
        quotes = []
    metadata = {"provider":"Public", "period":period,"aggregation":"ONE_DAY", "symbols":list(symbols),
                "retrieved_at":datetime.now(ZoneInfo("America/New_York")).isoformat(),
                "adjustment":"Provider closes; split/dividend adjustment unverified. Not total-return data.",
                "audit":audit,"quotes":quotes}
    return prices, metadata
