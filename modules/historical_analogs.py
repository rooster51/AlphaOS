"""Deterministic historical similarity; outcomes never determine membership."""
import json
import numpy as np
import pandas as pd

from modules.market_outcomes import HORIZONS

NUMERIC_FEATURES = ('return_5d','rsi_14','distance_ema_21_atr','realized_vol_20d','range_position_20')
DEFAULT_TOLERANCES = dict(zip(NUMERIC_FEATURES,(.02,10.,.75,.05,.20)))
STRUCTURES = ('bullish','bearish','mixed')
VERSION = 'historical-analogs-v1'


def sample_warning(n):
    if n < 30:
        return 'Very small historical sample. Results are highly uncertain.'
    if n < 100:
        return 'Small historical sample. Interpret cautiously.'
    if n < 250:
        return 'Moderate historical sample.'
    return 'Larger historical sample, but historical frequency is not a guarantee of future outcomes.'


def _dated(frame, required):
    if not isinstance(frame,pd.DataFrame) or frame.empty or not frame.columns.is_unique or not set(required).issubset(frame.columns):
        raise ValueError('Supply a nonempty Phase 2 frame with all required columns and unique column names.')
    frame=frame.copy().reset_index(drop=True)
    if pd.api.types.is_numeric_dtype(frame.date):
        raise ValueError('Dates must be explicit session dates.')
    frame['date']=pd.to_datetime(frame.date,utc=True,errors='coerce',format='mixed').dt.tz_convert(None).dt.normalize()
    if frame.date.isna().any() or frame.date.duplicated().any() or not frame.date.is_monotonic_increasing:
        raise ValueError('Session dates must be valid, unique and chronological.')
    if frame.symbol.isna().any() or frame.symbol.nunique()!=1 or frame.symbol.iloc[0] not in ('SPY','QQQ'):
        raise ValueError('Use a single SPY or QQQ dataset.')
    return frame


def match_analogs(features, target_date=None, method='tolerance', horizon=3,
                  numerical_features=NUMERIC_FEATURES, tolerances=None, exact_structure=True, neighbors=100):
    """Return feature-only matches. Eligibility depends on dates, never labels.

    The full Phase 2 row sequence must be retained, including warm-up rows, so
    i+H refers to the actual H-th subsequent observed bar.
    """
    numerical_features=tuple(numerical_features)
    if not numerical_features or len(set(numerical_features))!=len(numerical_features) or not set(numerical_features).issubset(NUMERIC_FEATURES):
        raise ValueError('Similarity features must be a nonempty unique subset of the five documented numerical features; future outcomes are forbidden.')
    if method not in ('tolerance','nearest') or horizon not in HORIZONS or neighbors not in (25,50,100,200):
        raise ValueError('Select tolerance/nearest, a 1/2/3/5/10-session horizon and 25/50/100/200 neighbors.')
    if not isinstance(exact_structure,bool):
        raise ValueError('Exact EMA structure must be true or false.')
    limits=DEFAULT_TOLERANCES.copy()
    if tolerances is not None:
        if not set(tolerances).issubset(NUMERIC_FEATURES):
            raise ValueError('Unknown tolerance feature.')
        limits.update(tolerances)
    try:
        limits={k:float(limits[k]) for k in numerical_features}
    except (TypeError,ValueError):
        raise ValueError('Tolerances must be finite, nonnegative numbers.') from None
    if any(not np.isfinite(v) or v<0 for v in limits.values()):
        raise ValueError('Tolerances must be finite, nonnegative numbers.')
    frame=_dated(features,['date','symbol','close','ema_structure',*numerical_features])
    for col in ['close',*numerical_features]:
        frame[col]=pd.to_numeric(frame[col],errors='coerce')
    try:
        target_day=frame.date.iloc[-1] if target_date is None else pd.Timestamp(target_date)
        if target_day.tzinfo:
            target_day=target_day.tz_convert('UTC').tz_localize(None)
        target_day=target_day.normalize()
    except (TypeError,ValueError):
        raise ValueError('Target must be a date in the dataset.') from None
    index=frame.index[frame.date==target_day]
    if len(index)!=1:
        raise ValueError('Target must be a completed session present in the dataset.')
    target_index=int(index[0])
    target=frame.loc[target_index]
    if not np.isfinite(target[list(numerical_features)].to_numpy(dtype=float)).all() or not np.isfinite(target.close) or target.close<=0:
        raise ValueError('Target lacks complete finite matching features; select a date after the indicator warm-up.')
    if exact_structure and (pd.isna(target.ema_structure) or target.ema_structure not in STRUCTURES):
        raise ValueError('Target EMA structure is unavailable; select a date after warm-up.')
    prior=frame.iloc[:target_index].copy()
    matured=prior[prior.index+horizon<=target_index]
    complete=np.isfinite(matured[list(numerical_features)].to_numpy(dtype=float)).all(axis=1)
    complete &= np.isfinite(matured.close)&(matured.close>0)
    if exact_structure:
        complete &= matured.ema_structure.isin(STRUCTURES)
    candidates=matured.loc[complete].copy()
    audit=dict(prior_dates=len(prior),as_of_matured_dates=len(matured),eligible_dates=len(candidates),
               missing_feature_dates=len(matured)-len(candidates))
    funnel=[dict(filter='Strictly before target',remaining=len(prior),removed=0),
            dict(filter=f'{horizon}-session outcome matured by target',remaining=len(matured),removed=len(prior)-len(matured)),
            dict(filter='Complete matching features',remaining=len(candidates),removed=len(matured)-len(candidates))]
    checks={}
    if exact_structure:
        checks['EMA structure match']=candidates.ema_structure.eq(target.ema_structure)
    if method=='tolerance':
        for col in numerical_features:
            checks[col]=(candidates[col]-target[col]).abs() <= limits[col]+1e-12
    independent=[dict(feature=k,passed=int(v.sum()),eligible=len(candidates),eliminated=len(candidates)-int(v.sum())) for k,v in checks.items()]
    keep=pd.Series(True,index=candidates.index)
    for label,mask in checks.items():
        before=int(keep.sum())
        keep &= mask
        funnel.append(dict(filter=label,remaining=int(keep.sum()),removed=before-int(keep.sum())))
    matched=candidates.loc[keep,['date','symbol','close',*numerical_features,'ema_structure']].copy()
    scaler=[]
    notes=[]
    if method=='nearest':
        # Fit once on matured, complete prior candidates BEFORE category filtering.
        means=candidates[list(numerical_features)].mean()
        stds=candidates[list(numerical_features)].std(ddof=0)
        active=[]
        for col in numerical_features:
            use=bool(np.isfinite(stds[col]) and stds[col]>1e-12)
            scaler.append(dict(feature=col,mean=float(means[col]) if np.isfinite(means[col]) else None,
                scale=float(stds[col]) if np.isfinite(stds[col]) else None,used=use,fit_n=len(candidates)))
            if use:
                active.append(col)
        if active:
            z_candidates=(matched[active]-means[active])/stds[active]
            z_target=(target[active].astype(float)-means[active])/stds[active]
            matched['similarity_distance']=np.sqrt(((z_candidates-z_target)**2).sum(axis=1))
        else:
            matched['similarity_distance']=0.
        ignored=[c for c in numerical_features if c not in active]
        if ignored:
            notes.append('Unavailable or near-zero-variance features omitted from distance: '+', '.join(ignored)+'. If all are omitted, distances tie at zero; this is not evidence of meaningful similarity.')
        before=len(matched)
        matched=matched.sort_values(['similarity_distance','date'],kind='stable').head(neighbors)
        funnel.append(dict(filter=f'Closest {neighbors} (date ascending breaks ties)',remaining=len(matched),removed=before-len(matched)))
    else:
        for col in numerical_features:
            matched[f'difference_{col}']=matched[col]-target[col]
    matched=matched.reset_index(drop=True)
    return dict(target=target[['date','symbol','close',*numerical_features,'ema_structure']].copy(),
        matches=matched,funnel=pd.DataFrame(funnel),independent_passes=pd.DataFrame(independent,columns=['feature','passed','eligible','eliminated']),
        scaler=pd.DataFrame(scaler,columns=['feature','mean','scale','used','fit_n']),audit=audit,notes=notes,
        config=dict(version=VERSION,target_date=str(target_day.date()),symbol=target.symbol,method=method,horizon=horizon,
                    numerical_features=list(numerical_features),tolerances=limits,exact_structure=exact_structure,neighbors=neighbors),
        # Full date sequence retained internally, not exported as matching features.
        session_dates=frame.date.copy(),target_index=target_index)


def attach_outcomes(result, outcomes):
    required=[f'future_{kind}_{h}s' for h in HORIZONS for kind in ('return','high_excursion','low_excursion')]
    labels=_dated(outcomes,['date','symbol',*required])
    if labels.symbol.iloc[0]!=result['config']['symbol']:
        raise ValueError('Features and outcomes must describe the same symbol.')
    # Alignment is by date, never positional label row order. Missing labels stay NaN.
    selected=result['matches'].copy()
    selected=selected.merge(labels[['date','symbol',*required]],on=['date','symbol'],how='left',validate='one_to_one',sort=False)
    positions=pd.Series(np.arange(len(result['session_dates'])),index=result['session_dates'])
    candidate_positions=selected.date.map(positions)
    for h in HORIZONS:
        known=candidate_positions+h<=result['target_index']
        selected[f'outcome_known_by_target_{h}s']=known
        for kind in ('return','high_excursion','low_excursion'):
            col=f'future_{kind}_{h}s'
            selected[col]=pd.to_numeric(selected[col],errors='coerce').replace([np.inf,-np.inf],np.nan).where(known)
    return selected


def summarize_outcomes(analogs):
    rows=[]
    for h in HORIZONS:
        ret=analogs[f'future_return_{h}s'].dropna()
        high=analogs[f'future_high_excursion_{h}s'].dropna()
        low=analogs[f'future_low_excursion_{h}s'].dropna()
        row=dict(horizon=h,n=len(ret),positive_frequency=(ret>0).mean(),negative_frequency=(ret<0).mean(),
            mean_return=ret.mean(),median_return=ret.median(),
            n_high_excursion=len(high),n_low_excursion=len(low),median_high_excursion=high.median(),
            median_low_excursion=low.median(),p10_low_excursion=low.quantile(.1),p90_high_excursion=high.quantile(.9))
        row.update({f'p{p}_return':ret.quantile(p/100,interpolation='linear') for p in (10,25,75,90)})
        rows.append(row)
    return pd.DataFrame(rows)


def analog_research(features, outcomes, **config):
    result=match_analogs(features,**config)
    result['analogs']=attach_outcomes(result,outcomes)
    result['summary']=summarize_outcomes(result['analogs'])
    return result


def sensitivity_analysis(features, outcomes, target_date=None, horizon=3, exact_structure=True):
    rows=[]
    for name,multiplier in (('TIGHT',.75),('DEFAULT',1.),('WIDE',1.5)):
        result=analog_research(features,outcomes,target_date=target_date,horizon=horizon,exact_structure=exact_structure,
            method='tolerance',tolerances={k:v*multiplier for k,v in DEFAULT_TOLERANCES.items()})
        for row in result['summary'].to_dict('records'):
            rows.append(dict(preset=name,multiplier=multiplier,sample_n=len(result['analogs']),horizon=row['horizon'],
                n_valid=row['n'],median_return=row['median_return'],positive_frequency=row['positive_frequency']))
    return pd.DataFrame(rows)


def export_analogs(result, source_metadata=None):
    frame=result['analogs'].copy()
    metadata=dict(config=result['config'],audit=result['audit'],scaler=result['scaler'].to_dict('records'),
        notes=result['notes'],source=source_metadata or {},
        interpretation='Descriptive historical frequencies, not calibrated forecast probabilities. Overlapping outcomes are dependent.',
        availability='Candidates strictly before target; selected horizon matures by target. Each attached horizon independently masked if unknown as of target.',
        units='Returns/excursions are signed decimal fractions. Distance is standardized Euclidean; not a probability.')
    frame['research_metadata_json']=json.dumps(metadata,sort_keys=True,allow_nan=False)
    return frame.to_csv(index=False)
