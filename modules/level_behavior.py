"""Quantify historical behavior around support/resistance-equivalent thresholds.

Uses analog forward terminal returns and excursions. Results are empirical sample
frequencies, not forecast probabilities.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

VERSION="level-behavior-v1"


def level_behavior(analog_result, *, horizon:int, anchor_spot:float, level:float, side:str):
    if horizon not in (1,2,3,5,10): raise ValueError("Use a 1, 2, 3, 5 or 10 session horizon.")
    if side not in ("support","resistance"): raise ValueError("Side must be support or resistance.")
    if not np.isfinite(anchor_spot) or anchor_spot<=0 or not np.isfinite(level) or level<=0:
        raise ValueError("Anchor spot and level must be positive finite numbers.")
    frame=analog_result.get("analogs")
    if not isinstance(frame,pd.DataFrame): raise ValueError("Supply a valid analog result.")
    ret=f"future_return_{horizon}s"; up=f"max_up_excursion_{horizon}s"; down=f"max_down_excursion_{horizon}s"
    if any(c not in frame for c in (ret,up,down)): raise ValueError("Analog result is missing forward return/excursion fields.")
    x=frame[["date",ret,up,down]].copy()
    for c in (ret,up,down): x[c]=pd.to_numeric(x[c],errors="coerce")
    x=x.replace([np.inf,-np.inf],np.nan).dropna()
    threshold_return=level/anchor_spot-1
    if side=="resistance":
        x["touched"]=x[up]>=threshold_return
        x["terminal_beyond"]=x[ret]>=threshold_return
        x["touched_rejected"]=x.touched & ~x.terminal_beyond
        x["broke_and_held"]=x.touched & x.terminal_beyond
        x["post_level_excursion"]=np.where(x.touched,x[up]-threshold_return,np.nan)
    else:
        x["touched"]=x[down]<=threshold_return
        x["terminal_beyond"]=x[ret]<=threshold_return
        x["touched_rejected"]=x.touched & ~x.terminal_beyond
        x["broke_and_held"]=x.touched & x.terminal_beyond
        x["post_level_excursion"]=np.where(x.touched,threshold_return-x[down],np.nan)
    n=len(x); touched=int(x.touched.sum()) if n else 0
    def freq(mask,denom): return float(mask.sum()/denom) if denom else None
    post=x.loc[x.touched,"post_level_excursion"].dropna()
    summary={"n":n,"threshold_return":float(threshold_return),
             "touch_frequency":freq(x.touched,n),"terminal_beyond_frequency":freq(x.terminal_beyond,n),
             "touch_rejection_frequency_all":freq(x.touched_rejected,n),
             "break_hold_frequency_all":freq(x.broke_and_held,n),
             "rejection_given_touch":freq(x.touched_rejected,touched),
             "break_hold_given_touch":freq(x.broke_and_held,touched),
             "median_post_level_excursion":float(post.median()) if len(post) else None,
             "p75_post_level_excursion":float(post.quantile(.75)) if len(post) else None,
             "p90_post_level_excursion":float(post.quantile(.90)) if len(post) else None}
    return {"config":{"version":VERSION,"horizon":horizon,"side":side,"anchor_spot":float(anchor_spot),"level":float(level)},
            "summary":summary,"observations":x}
