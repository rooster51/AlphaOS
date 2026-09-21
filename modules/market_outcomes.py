"""Future labels only: never use these columns as live predictors."""
import pandas as pd
from modules.market_state import validate_ohlc

HORIZONS = (1,2,3,5,10)
OUTCOME_CONVENTIONS = {
    'forward_returns': 'future_return_Hs=close[T+H]/close[T]-1, decimal; H=1,2,3,5,10 supplied sessions.',
    'excursions': 'future_high_excursion_Hs=max(high[T+1:T+H])/close[T]-1; future_low_excursion_Hs=min(low[T+1:T+H])/close[T]-1. Both endpoints included; signal-day high/low excluded. Exact signed formulas, no clipping: a gap entirely above spot can yield positive low excursion; entirely below can yield negative high excursion.',
    'label_availability': 'Each label requires H completed future observations and is known only after close T+H. Last H rows are NaN for all labels of that horizon. These columns are research-only future information, never features.',
}


def forward_outcomes(history, completed_before, expected_sessions=None):
    frame,_ = validate_ohlc(history,completed_before,expected_sessions)
    result = frame[['date','symbol']].copy()
    for h in HORIZONS:
        result[f'future_return_{h}s'] = frame.close.shift(-h)/frame.close-1
        # Trailing window evaluated at T+H covers exactly T+1 through T+H.
        result[f'future_high_excursion_{h}s'] = frame.high.rolling(h,min_periods=h).max().shift(-h)/frame.close-1
        result[f'future_low_excursion_{h}s'] = frame.low.rolling(h,min_periods=h).min().shift(-h)/frame.close-1
    return result
