"""Observed forward distributions, independently counted and current-spot anchored."""
import numpy as np
from modules.phase6_sample import prepared_outcomes

VERSION = 'forward-distribution-v2'


def summarize_forward_distribution(analog_result, horizon, anchor_spot):
    if not np.isfinite(anchor_spot) or anchor_spot <= 0:
        raise ValueError('Anchor spot must be positive and finite.')
    x = prepared_outcomes(analog_result, horizon)
    summary = {}; counts = {}
    for source, label, price in [('terminal_return','terminal_return','terminal_spot'),
                                 ('up_excursion','max_up_excursion','upside_spot'),
                                 ('down_excursion','max_down_excursion','downside_spot')]:
        x[price] = anchor_spot * (1 + x[source])
        for name, values in [(label,x[source]), (price,x[price])]:
            values = values.replace([np.inf,-np.inf],np.nan).dropna()
            counts[name] = len(values)
            summary[name] = {f'p{p}':float(values.quantile(p/100)) if len(values) else None
                             for p in (10,25,50,75,90)}
    return dict(config=dict(version=VERSION,horizon=horizon,anchor_spot=float(anchor_spot)),
                n=counts['terminal_return'],counts=counts,summary=summary,observations=x)
