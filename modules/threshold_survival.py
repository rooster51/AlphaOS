"""Underlying threshold frequencies only; no option pricing or execution model."""
import json
from math import isfinite, sqrt
import numpy as np
import pandas as pd

from modules.market_outcomes import HORIZONS
from modules.options_payoff import validate_trade

VERSION = 'threshold-survival-v1'
DEFAULT_DISTANCES = (.005,.01,.015,.02,.025,.03)
EPSILON = 1e-12  # Decimal-return tolerance for numerical equality, not an economic band.


def normalize_threshold(target_spot, mode, threshold_price=None, threshold_return=None, allow_opposite=False):
    if not isinstance(allow_opposite,bool):
        raise ValueError('Opposite-side acknowledgement must be an explicit boolean.')
    if mode not in ('put','call'):
        raise ValueError('Choose put (ABOVE threshold) or call (BELOW threshold).')
    if (threshold_price is None)==(threshold_return is None):
        raise ValueError('Supply exactly one threshold price or decimal percentage distance.')
    try:
        spot=float(target_spot)
        if not isfinite(spot) or spot<=0:
            raise ValueError
        distance=float(threshold_return) if threshold_price is None else float(threshold_price)/spot-1
        price=spot*(1+distance)
        if not isfinite(distance) or not isfinite(price) or price<=0:
            raise ValueError
    except (TypeError,ValueError,OverflowError):
        raise ValueError('Use a finite positive target spot/threshold price and a distance greater than -100%.') from None
    opposite=(mode=='put' and distance>EPSILON) or (mode=='call' and distance < -EPSILON)
    if opposite and not allow_opposite:
        raise ValueError('Put-style thresholds normally lie at/below target spot; call-style thresholds at/above it. Explicitly acknowledge an opposite-side threshold to continue.')
    return dict(target_spot=spot,mode=mode,threshold_price=price,threshold_return=distance,opposite_side=opposite)


def wilson_interval(successes,n):
    """95% Wilson score interval; nominal binomial assumptions, not a forecast."""
    if n<0 or successes<0 or successes>n or int(n)!=n or int(successes)!=successes:
        raise ValueError('Wilson counts must be whole numbers with 0 <= successes <= N.')
    if n==0:
        return (None,None)
    z=1.959963984540054
    p=successes/n
    denominator=1+z*z/n
    center=(p+z*z/(2*n))/denominator
    half=z*sqrt(p*(1-p)/n+z*z/(4*n*n))/denominator
    return max(0.,center-half),min(1.,center+half)


def _frequency(count,n):
    return count/n if n else None


def _prepare_sample(analog_result,horizon):
    """Recheck dates/maturity even if supplied Phase 3 flags are wrong or stale."""
    if horizon not in HORIZONS:
        raise ValueError('Use a 1, 2, 3, 5 or 10 observed-session horizon.')
    try:
        frame=analog_result['analogs'].copy().reset_index(drop=True)
        dates=pd.DatetimeIndex(pd.to_datetime(analog_result['session_dates'],utc=True,errors='raise')).tz_convert(None).normalize()
        target=pd.Timestamp(analog_result['target']['date'])
        if target.tzinfo:
            target=target.tz_convert('UTC').tz_localize(None)
        target=target.normalize()
        if dates.hasnans or dates.has_duplicates or not dates.is_monotonic_increasing or target not in dates:
            raise ValueError
        if not frame.columns.is_unique or not {'date','close','symbol'}.issubset(frame):
            raise ValueError
        frame['date']=pd.to_datetime(frame.date,utc=True,errors='raise').dt.tz_convert(None).dt.normalize()
        if frame.date.isna().any() or frame.date.duplicated().any() or not frame.date.isin(dates).all():
            raise ValueError
        if not frame.symbol.eq(analog_result['target']['symbol']).all():
            raise ValueError
        frame['close']=pd.to_numeric(frame.close,errors='coerce')
        if not np.isfinite(frame.close).all() or (frame.close<=0).any():
            raise ValueError
    except (KeyError,TypeError,ValueError,AttributeError):
        raise ValueError('Supply a valid Phase 3 analog sample, target and complete chronological session-date sequence.') from None
    positions=pd.Series(np.arange(len(dates)),index=dates)
    frame['session_position']=frame.date.map(positions).astype(int)
    for h in HORIZONS:
        known=(frame.date<target)&(frame.session_position+h<=dates.get_loc(target))
        flag=f'outcome_known_by_target_{h}s'
        if flag in frame:
            known &= frame[flag].eq(True).fillna(False)
        frame[flag]=known
        if h==horizon:
            frame['as_of_eligible']=known
        for kind in ('return','high_excursion','low_excursion'):
            col=f'future_{kind}_{h}s'
            values=pd.to_numeric(frame[col],errors='coerce') if col in frame else pd.Series(np.nan,index=frame.index)
            frame[col]=values.where(known & np.isfinite(values) & (values>=-1))
    return frame,target


def _summarize(frame):
    terminal=frame['terminal_status']
    touched=frame['touched_or_breached']
    tn=int(terminal.notna().sum())
    xn=int(touched.notna().sum())
    survived=int(terminal.eq('survived').sum())
    breached=int(terminal.eq('breached').sum())
    equal=int(terminal.eq('equal').sum())
    touch=int(touched.fillna(False).sum())
    paired=terminal.notna()&touched.notna()
    joint_n=int(paired.sum())
    joint_touch=int((paired&touched.fillna(False)).sum())
    recovery=int(frame['breached_intraperiod_but_terminally_survived'].fillna(False).sum())
    slo,shi=wilson_interval(survived,tn)
    tlo,thi=wilson_interval(touch,xn)
    return dict(sample_n=len(frame),as_of_eligible_n=int(frame.as_of_eligible.sum()),
        terminal_valid_n=tn,survived_n=survived,terminal_breached_n=breached,equality_n=equal,
        survival_frequency=_frequency(survived,tn),terminal_breach_frequency=_frequency(breached,tn),
        equality_frequency=_frequency(equal,tn),survival_wilson_low=slo,survival_wilson_high=shi,
        touch_valid_n=xn,touch_n=touch,no_touch_n=xn-touch,touch_frequency=_frequency(touch,xn),
        no_touch_frequency=_frequency(xn-touch,xn),touch_wilson_low=tlo,touch_wilson_high=thi,
        paired_valid_n=joint_n,paired_touch_n=joint_touch,recovery_n=recovery,
        recovery_frequency_all=_frequency(recovery,joint_n),recovery_frequency_touched=_frequency(recovery,joint_touch))


def non_overlapping_subset(evaluated,horizon):
    """Greedy earliest-first selection of paired-valid, disjoint future windows.

    At signal index i the outcome window is [i+1,i+H]. A next signal j is
    accepted when j>=i+H, so the future windows have no common observed bar.
    """
    if horizon not in HORIZONS:
        raise ValueError('Unsupported horizon.')
    eligible=evaluated[evaluated.terminal_status.notna()&evaluated.touched_or_breached.notna()&evaluated.as_of_eligible]
    indices=[]
    next_position=-1
    for index,row in eligible.sort_values('session_position',kind='stable').iterrows():
        if row.session_position>=next_position:
            indices.append(index)
            next_position=int(row.session_position)+horizon
    return evaluated.loc[indices].copy()


def threshold_research(analog_result,mode='put',horizon=3,threshold_price=None,threshold_return=None,allow_opposite=False):
    try:
        spot=analog_result['target']['close']
    except (KeyError,TypeError):
        raise ValueError('Phase 3 target spot is required.') from None
    config=normalize_threshold(spot,mode,threshold_price,threshold_return,allow_opposite)
    frame,target_date=_prepare_sample(analog_result,horizon)
    distance=config['threshold_return']
    returns=frame[f'future_return_{horizon}s']
    excursion=frame[f"future_{'low' if mode=='put' else 'high'}_excursion_{horizon}s"]
    frame['equivalent_historical_threshold']=frame.close*(1+distance)
    frame['terminal_underlying']=frame.close*(1+returns)
    frame['terminal_status']=pd.Series(pd.NA,index=frame.index,dtype='string')
    valid=returns.notna()
    difference=returns-distance
    equal=valid&(difference.abs()<=EPSILON)
    survived=valid&((difference>EPSILON) if mode=='put' else (difference < -EPSILON))
    frame.loc[valid,'terminal_status']='breached'
    frame.loc[equal,'terminal_status']='equal'
    frame.loc[survived,'terminal_status']='survived'
    touched=(excursion<=distance+EPSILON) if mode=='put' else (excursion>=distance-EPSILON)
    frame['touched_or_breached']=touched.astype('boolean').where(excursion.notna(),pd.NA)
    paired=valid&excursion.notna()
    frame['breached_intraperiod_but_terminally_survived']=(touched&survived).astype('boolean').where(paired,pd.NA)
    subset=non_overlapping_subset(frame,horizon)
    config.update(version=VERSION,horizon=horizon,target_date=str(target_date.date()),symbol=analog_result['target']['symbol'],
                  analog_selection_horizon=analog_result.get('config',{}).get('horizon'))
    quantiles=returns.dropna().quantile([.1,.25,.5,.75,.9],interpolation='linear')
    return dict(config=config,observations=frame,summary=_summarize(frame),
        non_overlapping_observations=subset,non_overlapping_summary=_summarize(subset),
        distribution_percentiles={str(p):float(value) if np.isfinite(value) else None for p,value in quantiles.items()})


def distance_grid(analog_result,mode='put',horizons=HORIZONS,distances=DEFAULT_DISTANCES):
    horizons=tuple(horizons)
    if not horizons or len(set(horizons))!=len(horizons) or not set(horizons).issubset(HORIZONS):
        raise ValueError('Grid horizons must be a nonempty unique subset of 1, 2, 3, 5, 10.')
    try:
        distances=tuple(float(d) for d in distances)
    except (TypeError,ValueError):
        raise ValueError('Grid distances must be positive decimal magnitudes.') from None
    if not distances or len(distances)>30 or any(not isfinite(d) or d<=0 or d>=1 for d in distances):
        raise ValueError('Supply 1–30 positive grid magnitudes less than 100%.')
    rows=[]
    for magnitude in sorted(set(distances)):
        distance=-magnitude if mode=='put' else magnitude
        for horizon in horizons:
            r=threshold_research(analog_result,mode,horizon,threshold_return=distance)
            rows.append(dict(threshold_return=distance,threshold_price=r['config']['threshold_price'],horizon=horizon,**r['summary']))
    return pd.DataFrame(rows)


def horizon_matrix(grid,field):
    if field not in ('survival_frequency','touch_frequency','terminal_valid_n','touch_valid_n'):
        raise ValueError('Unsupported matrix field.')
    return grid.pivot(index='threshold_return',columns='horizon',values=field).reindex(columns=HORIZONS)


def extract_short_strikes(trade,symbol):
    """Extract each short leg without using premium, Greeks or a model POP."""
    validated=validate_trade(trade)
    if validated['symbol']!=symbol:
        raise ValueError('Trade symbol must match the target market-state symbol.')
    return [dict(leg_index=i,type=leg['type'],mode='put' if leg['type']=='Put' else 'call',
                 strike=leg['strike'],contracts=abs(leg['qty']))
            for i,leg in enumerate(validated['legs']) if leg['qty']<0]


def selected_trade_threshold(analog_result,trade,leg_index):
    # Today's saved trade is not evidence of a strike available at a historical T.
    if analog_result.get('target_mode')!='LATEST COMPLETED SESSION':
        raise ValueError('Saved-trade shortcuts are disabled for historical targets. Enter an explicit hypothetical threshold instead.')
    choices=extract_short_strikes(trade,analog_result['target']['symbol'])
    choice=next((leg for leg in choices if leg['leg_index']==leg_index),None)
    if choice is None:
        raise ValueError('Choose a valid short option leg.')
    return dict(mode=choice['mode'],threshold_price=choice['strike'])


def export_threshold_observations(result,analog_config=None):
    frame=result['observations'].copy()
    frame['threshold_research_metadata']=json.dumps(dict(config=result['config'],analog_config=analog_config or {},
        equality_decimal_tolerance=EPSILON,interpretation='Historical threshold frequencies; not option POP, forecasts or profitability.',
        denominators='Terminal: finite matured return. Touch: finite matured relevant excursion. Recovery: paired valid observations; conditional recovery: touched within paired observations.'),allow_nan=False,sort_keys=True)
    return frame.to_csv(index=False)
