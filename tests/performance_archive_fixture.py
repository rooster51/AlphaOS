"""Dense synthetic archive observations; never production market evidence."""
from copy import deepcopy
import pandas as pd
from tests.test_archive_read_path import ReadOnlyClient
from tests.test_research2_api import repack

AS_OF = '2030-01-02T18:18:00+00:00'
LATE_AS_OF = '2030-01-02T20:33:00+00:00'

EXPIRATIONS = ['2030-01-02', '2030-01-03', '2030-01-04', '2030-01-18', '2031-01-17']

def dense_storage(symbol, *, late=False, production_scale=False):
    storage = ReadOnlyClient()
    source = deepcopy(storage.payload); source['symbol'] = symbol
    source.update(observed_at='2030-01-02T18:15:00+00:00', slot_time='2030-01-02T18:10:00+00:00', collection_finished_at='2030-01-02T18:16:00+00:00')
    if late:
        source.update(observed_at='2030-01-02T20:30:00+00:00', slot_time='2030-01-02T20:25:00+00:00', collection_finished_at='2030-01-02T20:32:00+00:00')
    expirations = (['2030-01-02','2030-01-03','2030-01-04','2030-01-07','2030-01-08',
                    '2030-01-09','2030-01-10','2030-01-11','2030-01-18','2031-01-17']
                   if production_scale else EXPIRATIONS.copy())
    source['options'].update(symbol=symbol, requested_expirations=expirations)
    rows=[]
    for expiry in expirations:
        for kind in ('call','put'):
            for i in range(141 if production_scale else 81):
                strike = (465 if production_scale else 480)+i*.5
                mid = 20 + (500-strike if kind=='call' else strike-500)*.4
                rows.append(dict(contract=f'{symbol}-{expiry}-{kind}-{strike}', symbol=symbol,
                    expiration=expiry, type=kind, strike=strike, bid=mid-.02, ask=mid+.02,
                    delta=.5 if kind=='call' else -.5, volume=100, open_interest=1000,
                    bid_timestamp=source['observed_at'], ask_timestamp=source['observed_at'],
                    observed_at=source['observed_at'], rejection_reasons=[], quality_warnings=[]))
    source['options']['valid_contracts']=rows
    storage.payload=source
    storage.row.update(symbol=symbol, observed_at=source['observed_at'], slot_time=source['slot_time'], created_at='2030-01-02T20:32:30+00:00' if late else '2030-01-02T18:17:00+00:00', archive_path=f'options/symbol={symbol}/date=2030-01-02/dense.json.gz')
    repack(storage)
    return storage

def dense_history(symbol):
    dates=pd.bdate_range(end='2030-01-01',periods=1260)
    close=pd.Series(range(len(dates)),dtype=float)*.05+400
    return pd.DataFrame(dict(date=dates,symbol=symbol,open=close,close=close,high=close+1,low=close-1))
