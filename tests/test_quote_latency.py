from datetime import datetime, timezone, timedelta
import json
import csv
import pytest
from modules.quote_freshness import freshness
from modules.quote_latency import observation, summarize, percentile, write_artifacts, frozen, interpretation
from scripts.quote_latency import sample

BASE=datetime(2026,9,28,14,tzinfo=timezone.utc)


def row(lag=10,index=0,symbol='QQQ',cache=False,stamp=None):
    retrieval=BASE+timedelta(seconds=60*index)
    quote=dict(last=745,bid=744.99,ask=745.01,updated_at=stamp or (retrieval-timedelta(seconds=lag)).isoformat())
    return observation(symbol,dict(quote=quote,retrieved_at=retrieval.isoformat(),
        freshness=freshness(quote,retrieval+timedelta(seconds=2),retrieval.isoformat()),cache=dict(hit=cache)),retrieval+timedelta(seconds=2))


def test_lag_timezone_cache_separation():
    r=row(stamp='2026-09-28T09:59:50-04:00')
    assert r['quote_as_of']=='2026-09-28T13:59:50+00:00'
    assert r['observation_lag_seconds']==10 and r['cache_age_seconds']==2
    assert r['source']=='Public' and r['cache_hit'] is False


def test_summary_statistics_buckets_multiple_symbols():
    values=[0,29,30,119,120,599,600,1199,1200,3599,3600,7200]
    rows=[row(lag,index) for index,lag in enumerate(values)]+[row(7,symbol='SPY',cache=True)]
    report=summarize(rows)['symbols'];q=report['QQQ']
    assert q['observations']==12 and q['provider_retrievals']==12 and q['cache_hits']==0
    assert q['minimum_lag']==0 and q['maximum_lag']==7200 and q['median_lag']==599.5
    assert q['mean_lag']==pytest.approx(sum(values)/12)
    assert q['p95_lag']==pytest.approx(5220)
    assert all(b['count']==2 and b['percentage']==pytest.approx(100/6) for b in q['latency_buckets'].values())
    assert report['SPY']['cache_hits']==1 and report['SPY']['provider_retrievals']==0
    assert percentile([], .95) is None and percentile([3],.95)==3


def test_frozen_timestamps_require_advancing_retrieval_not_price():
    rows=[row(10,i,stamp='2026-09-28T13:59:50Z') for i in range(4)]
    assert frozen(rows)['longest_frozen_timestamp_sequence']==4
    assert frozen(rows)['longest_frozen_timestamp_seconds']==180
    rows[1]['cache_hit']=True
    assert frozen(rows)['longest_frozen_timestamp_sequence']==3
    moving=[row(10,i) for i in range(4)]
    assert len({r['last'] for r in moving})==1
    assert frozen(moving)['longest_frozen_timestamp_sequence']==1
    assert frozen(moving)['unchanged_price_pairs']==3


@pytest.mark.parametrize('lags,expected',[
 ([10]*11,'Effectively real-time'),([900]*11,'Predictably delayed'),
 ([7200]*11,'Stale provider'),([10,1000]*6,'Unstable market-data')])
def test_interpretation_requires_repeated_regular_provider_observations(lags,expected):
    rows=[row(v,i) for i,v in enumerate(lags)]
    assert interpretation(rows).startswith(expected)
    assert interpretation(rows[:5]).startswith('Insufficient')
    for r in rows:r['market_state']='closed'
    assert interpretation(rows).startswith('Insufficient')


def test_serialization_allowlist_and_sampler(tmp_path):
    now=BASE
    quote=dict(last=745,bid=744,ask=745,updated_at=now.isoformat(),account_id='NEVER-EXPORT',access_token='NEVER-EXPORT')
    bundle=dict(quote=quote,retrieved_at=now.isoformat(),freshness=freshness(quote,now),cache=dict(hit=False),authorization='NEVER-EXPORT')
    class Timer:
        value=0
        def monotonic(self):return self.value
        def sleep(self,seconds):self.value+=seconds
    timer=Timer();calls=[]
    def fetch(symbol):
        calls.append(symbol)
        if symbol=='BAD':raise RuntimeError('NEVER-EXPORT')
        return bundle
    rows=sample(fetch,['QQQ','SPY','BAD'],120,60,tmp_path,monotonic=timer.monotonic,sleep=timer.sleep,clock=lambda:now)
    assert len(rows)==9 and len(calls)==9 and timer.value==120
    text=(tmp_path/'observations.csv').read_text()+(tmp_path/'summary.json').read_text()
    assert 'NEVER-EXPORT' not in text
    assert len(list(csv.DictReader((tmp_path/'observations.csv').open())))==9
    assert json.loads((tmp_path/'summary.json').read_text())['symbols']['BAD']['successful_observations']==0
