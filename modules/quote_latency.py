"""Internal read-only sampling helpers. Only allowlisted market metadata leaves the sampler."""
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from modules.quote_freshness import normalize_timestamp

BUCKETS = [('under_30s', 0, 30), ('30_120s', 30, 120), ('2_10m', 120, 600),
           ('10_20m', 600, 1200), ('20_60m', 1200, 3600), ('over_60m', 3600, math.inf)]


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def observation(symbol, bundle, observed_at=None):
    q, f = bundle['quote'], bundle['freshness']
    quote_time = normalize_timestamp(f.get('quote_as_of'))
    retrieval = normalize_timestamp(bundle.get('retrieved_at'))
    lag = (datetime.fromisoformat(retrieval)-datetime.fromisoformat(quote_time)).total_seconds() if retrieval and quote_time else None
    quality = f.get('quote_quality', {})
    status = f.get('data_status')
    state = f.get('market_state')
    return dict(symbol=symbol, observed_at=normalize_timestamp(observed_at or datetime.now(timezone.utc)),
        last=number(q.get('last')), bid=number(q.get('bid')), ask=number(q.get('ask')),
        provider_timestamp_field='lastTimestamp',
        provider_timestamp=str(q['provider_timestamp']) if normalize_timestamp(q.get('provider_timestamp')) else None,
        provider_timestamp_representation='Public SDK datetime; original HTTP spelling unavailable',
        quote_as_of=quote_time, retrieved_at=retrieval, observation_lag_seconds=lag,
        market_state=state if state in ('regular_open','extended_hours','closed','unknown') else 'unknown',
        data_status=status if status in ('fresh','delayed','stale','latest_available','unknown') else 'unknown',
        usable_for_live_research=f.get('usable_for_live_research') is True,
        usable_for_execution_analysis=f.get('usable_for_execution_analysis') is True,
        bid_ask_quality='acceptable' if quality.get('bid_ask_valid') is True else 'suspect',
        bid_ask_spread=number(quality.get('bid_ask_spread')), bid_ask_spread_pct=number(quality.get('bid_ask_spread_pct')),
        source='Public', cache_hit=bundle.get('cache',{}).get('hit'),
        cache_age_seconds=number(f.get('cache_age_seconds')), request_ok=True,
        reference_quote_as_of=None, reference_price=None, reference_source=None)


def percentile(values, fraction):
    """Linear interpolation, index (n-1)*fraction, matching common NumPy defaults."""
    ordered = sorted(values)
    if not ordered:
        return None
    index = (len(ordered)-1)*fraction
    lower, upper = math.floor(index), math.ceil(index)
    return ordered[lower]+(ordered[upper]-ordered[lower])*(index-lower)


def frozen(rows):
    """Count provider retrievals with advancing retrieval times and an unchanged timestamp."""
    longest = run = 0
    previous_stamp = previous_retrieval = None
    start = None
    longest_seconds = 0.
    same_price = 0
    previous_price = None
    for row in rows:
        if row.get('cache_hit') is not False or not row.get('request_ok'):
            continue
        stamp, retrieval = row.get('quote_as_of'), row.get('retrieved_at')
        if not stamp or not retrieval:
            run = 0
            previous_stamp = previous_retrieval = None
            continue
        advancing = previous_retrieval is not None and retrieval > previous_retrieval
        if advancing and stamp == previous_stamp:
            run += 1
        else:
            run, start = 1, retrieval
        if advancing and row.get('last') == previous_price:
            same_price += 1
        duration = (datetime.fromisoformat(retrieval)-datetime.fromisoformat(start)).total_seconds()
        longest = max(longest, run)
        longest_seconds = max(longest_seconds, duration)
        previous_stamp, previous_retrieval, previous_price = stamp, retrieval, row.get('last')
    return dict(longest_frozen_timestamp_sequence=longest, longest_frozen_timestamp_seconds=longest_seconds,
        unchanged_price_pairs=same_price)


def interpretation(rows):
    active = [r for r in rows if r.get('market_state')=='regular_open' and r.get('cache_hit') is False
              and r.get('request_ok') and r.get('observation_lag_seconds') is not None and r['observation_lag_seconds']>=0]
    if len(active)<10:
        return 'Insufficient repeated regular-session provider retrievals; no latency conclusion.'
    span = (datetime.fromisoformat(active[-1]['retrieved_at'])-datetime.fromisoformat(active[0]['retrieved_at'])).total_seconds()
    if span<300:
        return 'Insufficient regular-session sampling duration; no latency conclusion.'
    lags = [r['observation_lag_seconds'] for r in active]
    p05, p95 = percentile(lags,.05), percentile(lags,.95)
    if median(lags)<=30 and p95<=120:
        return 'Effectively real-time observation behavior during this test; entitlement unverified.'
    if 600<=p05 and p95<=1200 and p95-p05<=180:
        return 'Predictably delayed observation behavior near 15 minutes during this test; entitlement unverified.'
    if p95-p05>300 and p05<=120:
        return 'Unstable market-data freshness during this test.'
    if median(lags)>120:
        return 'Stale provider observations during this test.'
    return 'Mixed observation latency during this test; review the recorded series.'


def summarize(rows):
    result = {}
    for symbol in sorted({r['symbol'] for r in rows}):
        subset = [r for r in rows if r['symbol']==symbol]
        lags = [r['observation_lag_seconds'] for r in subset if r.get('observation_lag_seconds') is not None]
        buckets = {name:dict(count=sum(low<=v<high for v in lags),
            percentage=100*sum(low<=v<high for v in lags)/len(lags) if lags else None) for name,low,high in BUCKETS}
        result[symbol] = dict(observations=len(subset), successful_observations=sum(r.get('request_ok',False) for r in subset),
            lag_samples=len(lags), minimum_lag=min(lags) if lags else None, median_lag=median(lags) if lags else None,
            mean_lag=mean(lags) if lags else None, maximum_lag=max(lags) if lags else None, p95_lag=percentile(lags,.95),
            latency_buckets=buckets, future_timestamp_count=sum(v<0 for v in lags),
            unique_quote_timestamps=len({r['quote_as_of'] for r in subset if r.get('quote_as_of')}),
            cache_hits=sum(r.get('cache_hit') is True for r in subset),
            provider_retrievals=sum(r.get('cache_hit') is False and r.get('request_ok',False) for r in subset),
            cache_status_unknown=sum(r.get('cache_hit') is None for r in subset),
            regular_session_provider_retrievals=sum(r.get('cache_hit') is False and r.get('market_state')=='regular_open' for r in subset),
            **frozen(subset), interpretation=interpretation(subset))
    return dict(symbols=result, caveat='Empirical observation lag, not provider entitlement or independent exchange latency. Closed-session samples do not establish feed delay.')


def write_artifacts(rows, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with (directory/'observations.csv').open('w',newline='',encoding='utf-8') as stream:
        writer = csv.DictWriter(stream,fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    (directory/'summary.json').write_text(json.dumps(summarize(rows),indent=2,allow_nan=False),encoding='utf-8')
