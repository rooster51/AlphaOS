"""Quantify historical behavior around support/resistance-equivalent thresholds.

Uses analog forward terminal returns and excursions. Results are empirical sample
frequencies, not forecast probabilities.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from modules.phase6_sample import prepared_outcomes

VERSION="level-behavior-v2"
EPSILON = 1e-12  # Decimal-return representation tolerance, not a price band.


def level_behavior(analog_result, *, horizon:int, anchor_spot:float, level:float, side:str):
    if horizon not in (1,2,3,5,10): raise ValueError("Use a 1, 2, 3, 5 or 10 session horizon.")
    if side not in ("support","resistance"): raise ValueError("Side must be support or resistance.")
    if not np.isfinite(anchor_spot) or anchor_spot<=0 or not np.isfinite(level) or level<=0:
        raise ValueError("Anchor spot and level must be positive finite numbers.")
    x=prepared_outcomes(analog_result,horizon).dropna().copy()
    ret='terminal_return'; up='up_excursion'; down='down_excursion'
    threshold_return=level/anchor_spot-1
    x["terminal_equal"]=(x[ret]-threshold_return).abs()<=EPSILON
    if side=="resistance":
        x["touched"]=x[up]>=threshold_return-EPSILON
        x["terminal_beyond"]=x[ret]>threshold_return+EPSILON
        x["touched_rejected"]=x.touched & ~x.terminal_beyond & ~x.terminal_equal
        x["broke_and_held"]=x.touched & x.terminal_beyond
        x["post_level_excursion"]=np.where(x.touched,x[up]-threshold_return,np.nan)
    else:
        x["touched"]=x[down]<=threshold_return+EPSILON
        x["terminal_beyond"]=x[ret]<threshold_return-EPSILON
        x["touched_rejected"]=x.touched & ~x.terminal_beyond & ~x.terminal_equal
        x["broke_and_held"]=x.touched & x.terminal_beyond
        x["post_level_excursion"]=np.where(x.touched,threshold_return-x[down],np.nan)
    x["post_level_excursion"]=x["post_level_excursion"].clip(lower=0)
    n=len(x); touched=int(x.touched.sum()) if n else 0
    def freq(mask,denom): return float(mask.sum()/denom) if denom else None
    post=x.loc[x.touched,"post_level_excursion"].dropna()
    summary={"n":n,"threshold_return":float(threshold_return),
             "terminal_equal_frequency":freq(x.terminal_equal,n),
             "equality_given_touch":freq(x.touched & x.terminal_equal,touched),
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
