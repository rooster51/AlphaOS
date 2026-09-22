"""Historical forward terminal and excursion distributions for analog samples."""
from __future__ import annotations
import numpy as np
import pandas as pd

VERSION="forward-distribution-v1"


def summarize_forward_distribution(analog_result, horizon:int, anchor_spot:float):
    if horizon not in (1,2,3,5,10): raise ValueError("Use a 1, 2, 3, 5 or 10 session horizon.")
    if not np.isfinite(anchor_spot) or anchor_spot<=0: raise ValueError("Anchor spot must be positive and finite.")
    frame=analog_result.get("analogs")
    if not isinstance(frame,pd.DataFrame): raise ValueError("Supply a valid analog result.")
    ret=f"future_return_{horizon}s"; up=f"max_up_excursion_{horizon}s"; down=f"max_down_excursion_{horizon}s"
    missing=[c for c in (ret,up,down) if c not in frame]
    if missing: raise ValueError("Analog result is missing forward return/excursion fields.")
    x=frame[["date",ret,up,down]].copy()
    for c in (ret,up,down): x[c]=pd.to_numeric(x[c],errors="coerce")
    x=x.replace([np.inf,-np.inf],np.nan).dropna()
    if x.empty: return {"config":{"version":VERSION,"horizon":horizon},"n":0,"summary":{},"observations":x}
    x["terminal_spot"]=anchor_spot*(1+x[ret])
    x["upside_spot"]=anchor_spot*(1+x[up])
    x["downside_spot"]=anchor_spot*(1+x[down])
    def q(series):
        return {f"p{p}":float(series.quantile(p/100)) for p in (10,25,50,75,90)}
    summary={"terminal_return":q(x[ret]),"terminal_spot":q(x.terminal_spot),
             "max_up_excursion":q(x[up]),"upside_spot":q(x.upside_spot),
             "max_down_excursion":q(x[down]),"downside_spot":q(x.downside_spot)}
    return {"config":{"version":VERSION,"horizon":horizon,"anchor_spot":float(anchor_spot)},
            "n":len(x),"summary":summary,"observations":x}
