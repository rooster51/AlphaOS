"""Point-in-time price-structure research for SPY/QQQ.

Detects nearby support/resistance candidates from completed daily OHLC only. Levels
are descriptive research features, not predictions or trade recommendations.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

VERSION = "price-structure-v1"


def _prepare(history, completed_before=None):
    from modules.market_state import validate_ohlc
    if completed_before is None:
        completed_before = pd.Timestamp.now(tz='America/New_York').date()
    f, _ = validate_ohlc(history, completed_before)
    if len(f)<60 or f.symbol.iloc[0] not in ('SPY','QQQ'):
        raise ValueError('Price structure requires at least 60 valid completed SPY/QQQ bars.')
    return f


def _atr(frame: pd.DataFrame, n=14) -> pd.Series:
    prev=frame.close.shift(1)
    tr=pd.concat([(frame.high-frame.low).abs(),(frame.high-prev).abs(),(frame.low-prev).abs()],axis=1).max(axis=1)
    return tr.rolling(n,min_periods=n).mean()


def _pivots(frame: pd.DataFrame, window=3):
    highs=[]; lows=[]
    for i in range(window,len(frame)-window):
        hi=frame.high.iloc[i]; lo=frame.low.iloc[i]
        if hi>=frame.high.iloc[i-window:i+window+1].max(): highs.append((i,float(hi),"swing_high"))
        if lo<=frame.low.iloc[i-window:i+window+1].min(): lows.append((i,float(lo),"swing_low"))
    return highs,lows


def _cluster(candidates, tolerance):
    if not candidates: return []
    candidates=sorted(candidates,key=lambda x:x[1])
    groups=[]
    for item in candidates:
        if not groups or abs(item[1]-np.mean([x[1] for x in groups[-1]]))>tolerance:
            groups.append([item])
        else: groups[-1].append(item)
    return groups


def price_structure(history: pd.DataFrame, lookback=252, pivot_window=3, cluster_atr=.20, completed_before=None, anchor_spot=None):
    if isinstance(lookback,bool) or int(lookback)!=lookback or lookback<60:
        raise ValueError('Lookback must be an integer of at least 60 sessions.')
    if isinstance(pivot_window,bool) or int(pivot_window)!=pivot_window or pivot_window<1 or 2*pivot_window>=lookback:
        raise ValueError('Invalid pivot confirmation window.')
    if not np.isfinite(cluster_atr) or cluster_atr<=0:
        raise ValueError('Clustering distance must be positive and finite.')
    f=_prepare(history, completed_before)
    f=f.tail(min(int(lookback),len(f))).reset_index(drop=True)
    atr=_atr(f)
    current_atr=float(atr.iloc[-1]) if pd.notna(atr.iloc[-1]) else float((f.high-f.low).tail(14).mean())
    research_close=float(f.close.iloc[-1])
    spot=research_close if anchor_spot is None else float(anchor_spot)
    if not np.isfinite(spot) or spot<=0 or not np.isfinite(current_atr) or current_atr<=0:
        raise ValueError('Positive finite spot and nonzero ATR are required.')
    symbol=str(f.symbol.iloc[-1]); as_of=f.date.iloc[-1]
    highs,lows=_pivots(f,pivot_window)
    # Add rolling extremes as independent structural observations.
    for n in (20,50,100,252):
        if len(f)>=n:
            w=f.tail(n)
            highs.append((int(w.high.idxmax()),float(w.high.max()),f"{n}d_high"))
            lows.append((int(w.low.idxmin()),float(w.low.min()),f"{n}d_low"))
    tolerance=max(current_atr*cluster_atr,research_close*.001)
    rows=[]
    for side,cands in (("resistance",highs),("support",lows)):
        for group in _cluster(cands,tolerance):
            level=float(np.mean([x[1] for x in group]))
            if side=="resistance" and level<=spot: continue
            if side=="support" and level>=spot: continue
            touches=len(set(x[0] for x in group)); last=max(x[0] for x in group); age=len(f)-1-last
            distance=level/spot-1
            rows.append(dict(side=side,level=level,zone_low=level-tolerance/2,zone_high=level+tolerance/2,
                             distance_pct=distance,distance_atr=(level-spot)/current_atr,
                             observations=touches,last_observed_sessions_ago=age,
                             sources=", ".join(sorted(set(x[2] for x in group)))))
    levels=pd.DataFrame(rows)
    if not levels.empty:
        levels["abs_distance_atr"]=levels.distance_atr.abs()
        levels=levels.sort_values(["side","abs_distance_atr","last_observed_sessions_ago"]).reset_index(drop=True)
    return {"config":{"version":VERSION,"symbol":symbol,"as_of":str(as_of.date()),"lookback":len(f),
                      "pivot_window":pivot_window,"cluster_atr":cluster_atr},
            "spot":spot,"research_close":research_close,"atr":current_atr,"levels":levels}


def nearest_levels(result, per_side=3):
    levels=result["levels"]
    if levels.empty: return levels.copy()
    return pd.concat([levels[levels.side==s].nsmallest(per_side,"abs_distance_atr") for s in ("support","resistance")],ignore_index=True)
