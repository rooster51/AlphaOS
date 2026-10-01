"""Read-only capability gate: market summaries only; no credentials or account data output."""
import json
import os
import time
from collections import Counter
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import pandas as pd

NY=ZoneInfo('America/New_York')

def summarize(raw):
    out={'symbol':raw.get('symbol'),'period':raw.get('period'),'leading_fill':bool(raw.get('leadingFill')),'sessions':{}}
    for key,value in raw.items():
        if not isinstance(value,dict) or not isinstance(value.get('bars'),list):continue
        bars=value['bars'];times=pd.to_datetime([b.get('timestamp') for b in bars],utc=True,errors='coerce');valid=times[~times.isna()]
        local=valid.tz_convert(NY);counts=Counter(str(t.date()) for t in local)
        diffs=Counter(round((b-a).total_seconds()/60,3) for a,b in zip(valid,valid[1:]))
        out['sessions'][key]=dict(count=len(bars),expected=value.get('expectedBars'),first=str(valid.min()) if len(valid) else None,last=str(valid.max()) if len(valid) else None,
            date_count=len(counts),bars_per_date=dict(counts) if len(counts)<12 else dict(min=min(counts.values()),max=max(counts.values())),
            invalid_timestamps=int(times.isna().sum()),duplicates=int(valid.duplicated().sum()),ordered=valid.is_monotonic_increasing,
            common_interval_minutes=diffs.most_common(5),positive_volume=sum(float(b.get('volume') or 0)>0 for b in bars),
            zero_volume=sum(float(b.get('volume') or 0)==0 for b in bars),
            local_times=sorted({t.strftime('%H:%M') for t in local})[:8],last_local_times=sorted({t.strftime('%H:%M') for t in local})[-8:],
            sample=[{k:b.get(k) for k in ('timestamp','open','high','low','close','volume')} for b in bars[-2:]])
    return out

def main():
    from public_api_sdk import PublicApiClient,ApiKeyAuthConfig
    client=PublicApiClient(ApiKeyAuthConfig(api_secret_key=os.environ['PUBLIC_API_SECRET'].strip(),validity_minutes=30))
    print('AUDIT_START',datetime.now(timezone.utc).isoformat(),flush=True)
    for symbol,kind in [('SPY','EQUITY'),('QQQ','EQUITY'),('XSP','INDEX'),('SPX','INDEX')]:
        for aggregation in ('ONE_MINUTE','FIVE_MINUTES','FIFTEEN_MINUTES','THIRTY_MINUTES','ONE_HOUR'):
            for period in ('DAY','WEEK','MONTH','QUARTER','YEAR'):
                entry=dict(symbol=symbol,type=kind,aggregation=aggregation,period=period);start=time.perf_counter()
                try:
                    raw=client.api_client.get(f'/userapigateway/historicdata/{kind}/{symbol}/{period}/{aggregation}',params={'tradingSessionToggle':'ALL_SESSIONS'})
                    entry.update(status=200,result=summarize(raw))
                except Exception as exc:entry.update(status=getattr(exc,'status_code',None),error_class=type(exc).__name__)
                entry['seconds']=round(time.perf_counter()-start,3)
                print('BAR_AUDIT '+json.dumps(entry),flush=True)
                time.sleep(.2)
    print('AUDIT_END',datetime.now(timezone.utc).isoformat(),flush=True)

if __name__=='__main__':main()
