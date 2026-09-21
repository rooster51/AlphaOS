"""Trailing daily features only. Never import forward outcomes here."""
import numpy as np
import pandas as pd

VERSION = 'market-state-v1'
RAW = ['date', 'symbol', 'open', 'high', 'low', 'close']
CONVENTIONS = {
    'availability': 'Features for T are known only after the completed regular session close T, not at its open. No backfill or forward-fill.',
    'returns': 'return_Hd = close[T]/close[T-H]-1; decimal fraction, first available on observation H+1; H=1,2,3,5,10,20.',
    'ema': 'EMA N: alpha=2/(N+1), recursive adjust=False, seed=first observed close; masked until N closes. N=9,21,50,200. Seed depends on supplied history start.',
    'ema_distance': 'distance_ema_N_pct = close/EMA_N-1 (decimal fraction). distance_ema_N_atr = (close-EMA_N)/ATR14; N=21,50; unavailable when ATR=0.',
    'rsi': 'RSI14 uses Wilder average gains/losses: seed arithmetic mean of first 14 close changes, then (13*prior+current)/14. First available at observation 15. Gain-only=100, loss-only=0, both zero=50.',
    'true_range': 'TR=max(high-low,abs(high-prior close),abs(low-prior close)); first observation uses high-low.',
    'atr': 'ATR14=trailing arithmetic mean of 14 TR values, consistent with existing AlphaOS daily ATR (not Wilder ATR). First available at observation 14. atr_pct=ATR14/close, decimal.',
    'realized_volatility': 'Sample standard deviation (ddof=1) of trailing N log(close/prior close) returns times sqrt(252); N=10,20,60. First available at observation N+1, annualized decimal.',
    'range': '20-observation rolling high uses HIGH and low uses LOW, including T; first available at observation 20. range_position_20=(close-low20)/(high20-low20); NaN for zero range. distance_high_20_pct=close/high20-1; distance_low_20_pct=close/low20-1; decimal fractions.',
    'structure': 'bullish iff close>EMA9>EMA21>EMA50; bearish iff close<EMA9<EMA21<EMA50; otherwise mixed. Missing until observation 50. Descriptive ordering only, not a signal.',
    'sessions': 'Horizons count supplied daily observations, never calendar days. Calendar completeness must be verified before treating observations as consecutive exchange sessions.',
    'adjustment': 'Public OHLC split/dividend adjustment is unverified. Corporate-action discontinuities can distort indicators and returns. No total-return claim or point-in-time revision guarantee.',
}


def validate_ohlc(history, completed_before, expected_sessions=None):
    """Strict order/row validation; exclude dates >= explicit completion cutoff.

    Optional authoritative expected_sessions rejects missing/extra sessions in
    the observed span. Without it, report weekday gaps without inventing bars.
    Daily provider timestamps are interpreted by UTC calendar date.
    """
    if not isinstance(history, pd.DataFrame) or history.empty or not set(RAW).issubset(history):
        raise ValueError('Supply nonempty date, symbol, open, high, low, close history.')
    frame = history[RAW].copy().reset_index(drop=True)
    if pd.api.types.is_numeric_dtype(frame['date']):
        raise ValueError('Dates must be explicit daily dates or timestamps, not numeric epochs.')
    days = pd.to_datetime(frame['date'], errors='coerce', utc=True, format='mixed').dt.tz_convert(None).dt.normalize()
    if days.isna().any() or days.duplicated().any() or not days.is_monotonic_increasing:
        raise ValueError('Dates must be valid, unique and in strictly increasing chronological order.')
    frame['date'] = days
    symbols = frame['symbol']
    if symbols.isna().any() or not symbols.map(lambda s: isinstance(s,str) and bool(s.strip())).all() or symbols.nunique() != 1:
        raise ValueError('Supply exactly one nonmissing symbol per dataset.')
    frame['symbol'] = symbols.str.strip().str.upper()
    for col in RAW[2:]:
        frame[col] = pd.to_numeric(frame[col],errors='coerce')
    values = frame[RAW[2:]].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError('OHLC must be numeric, finite, positive and complete; missing prices are not filled.')
    if ((frame.high < frame[['open','close','low']].max(axis=1)) |
            (frame.low > frame[['open','close','high']].min(axis=1))).any():
        raise ValueError('Invalid OHLC bounds: high must contain open/close/low and low must contain open/close/high.')
    cutoff = pd.Timestamp(completed_before)
    if pd.isna(cutoff):
        raise ValueError('Supply an explicit completed-session cutoff date.')
    if cutoff.tzinfo:
        cutoff = cutoff.tz_localize(None)
    cutoff = cutoff.normalize()
    excluded = int((frame.date >= cutoff).sum())
    frame = frame[frame.date < cutoff].reset_index(drop=True)
    if frame.empty:
        raise ValueError('No completed sessions before the cutoff.')
    if (frame.date.dt.dayofweek >= 5).any():
        raise ValueError('Weekend daily bars are not supported for SPY/QQQ regular sessions.')
    observed = pd.DatetimeIndex(frame.date)
    potential = pd.bdate_range(observed[0],observed[-1]).difference(observed)
    calendar_verified = expected_sessions is not None
    if calendar_verified:
        expected = pd.DatetimeIndex(pd.to_datetime(expected_sessions,utc=True)).tz_convert(None).normalize()
        expected = expected[(expected >= observed[0]) & (expected <= observed[-1])]
        if len(expected.difference(observed)) or len(observed.difference(expected)):
            raise ValueError('History does not match the supplied exchange sessions; missing or unexpected observations.')
    warnings = []
    if not calendar_verified:
        warnings.append('Exchange calendar not verified. Missing weekdays may be holidays or missing provider bars; horizons count observed bars. Review the gap audit before research use.')
    gaps = frame.date.diff().dt.days
    if (gaps > 7).any():
        warnings.append('At least one gap exceeds seven calendar days: history may be sparse or incomplete.')
    return frame, dict(excluded_uncompleted=excluded,completed_before=str(cutoff.date()),
        calendar_verified=calendar_verified,possible_missing_weekdays=[str(d.date()) for d in potential],
        max_calendar_gap_days=int(gaps.max()) if len(frame)>1 else 0,warnings=warnings)


def _wilder(series, n=14):
    out = pd.Series(np.nan,index=series.index,dtype=float)
    if len(series) > n:
        out.iloc[n] = series.iloc[1:n+1].mean()
        for i in range(n+1,len(series)):
            out.iloc[i] = (out.iloc[i-1]*(n-1)+series.iloc[i])/n
    return out


def market_state_features(history, completed_before, expected_sessions=None):
    frame, _ = validate_ohlc(history,completed_before,expected_sessions)
    close = frame.close
    for n in (1,2,3,5,10,20):
        frame[f'return_{n}d'] = close.pct_change(n,fill_method=None)
    for n in (9,21,50,200):
        frame[f'ema_{n}'] = close.ewm(span=n,adjust=False,min_periods=n).mean()
        frame[f'distance_ema_{n}_pct'] = close/frame[f'ema_{n}']-1
    prior = close.shift(1)
    frame['true_range'] = pd.concat([frame.high-frame.low,(frame.high-prior).abs(),(frame.low-prior).abs()],axis=1).max(axis=1)
    frame['atr_14'] = frame.true_range.rolling(14,min_periods=14).mean()
    frame['atr_pct'] = frame.atr_14/close
    for n in (21,50):
        frame[f'distance_ema_{n}_atr'] = (close-frame[f'ema_{n}'])/frame.atr_14.replace(0,np.nan)
    delta = close.diff()
    gains, losses = _wilder(delta.clip(lower=0)), _wilder(-delta.clip(upper=0))
    frame['rsi_14'] = 100-100/(1+gains/losses.replace(0,np.nan))
    frame.loc[(losses==0)&(gains>0),'rsi_14']=100.
    frame.loc[(losses==0)&(gains==0),'rsi_14']=50.
    logs = np.log(close/prior)
    for n in (10,20,60):
        frame[f'realized_vol_{n}d'] = logs.rolling(n,min_periods=n).std(ddof=1)*np.sqrt(252)
    frame['high_20'] = frame.high.rolling(20,min_periods=20).max()
    frame['low_20'] = frame.low.rolling(20,min_periods=20).min()
    frame['range_position_20'] = (close-frame.low_20)/(frame.high_20-frame.low_20).replace(0,np.nan)
    frame['distance_high_20_pct'] = close/frame.high_20-1
    frame['distance_low_20_pct'] = close/frame.low_20-1
    frame['ema_structure'] = pd.Series(pd.NA,index=frame.index,dtype='string')
    ready = frame.ema_50.notna()
    frame.loc[ready,'ema_structure']='mixed'
    frame.loc[ready & (close>frame.ema_9)&(frame.ema_9>frame.ema_21)&(frame.ema_21>frame.ema_50),'ema_structure']='bullish'
    frame.loc[ready & (close<frame.ema_9)&(frame.ema_9<frame.ema_21)&(frame.ema_21<frame.ema_50),'ema_structure']='bearish'
    return frame
