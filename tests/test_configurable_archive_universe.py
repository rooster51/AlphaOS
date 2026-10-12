"""Multi-symbol policy and existing reader/evaluator; no live credentials."""
import gzip
import hashlib
import json
from unittest.mock import Mock
import pytest

from modules.intraday_canary_universe import collection_symbols, enabled_archive_symbols
from modules.intraday_archive import collect_symbol, load_config
from modules.supabase_archive import read_latest_option_snapshot, ArchiveUnavailable
from modules.intraday_quoted_round_trip import reconstruct_quoted_round_trip, EvidenceRejected
from tests.test_archive_read_path import ReadOnlyClient
from tests.test_intraday_quoted_round_trip import snapshot
from tests.test_intraday_execution import setup, NOW
from scripts import run_intraday_snapshot as runner


def database(symbol, closing=False):
    value=json.loads(json.dumps(snapshot(exit=closing)).replace('SPY',symbol))
    db=ReadOnlyClient(); db.payload=value['payload']
    db.row=dict(value['metadata'],id='fixture',slot_time=None,
        archive_path=f'options/symbol={symbol}/date=2026-10-09/fixture.json.gz')
    seal(db)
    return db


def seal(db):
    db.raw=gzip.compress(json.dumps(db.payload).encode(),mtime=0)
    db.row['archive_sha256']=hashlib.sha256(db.raw).hexdigest()


@pytest.mark.parametrize('symbol',['NVDA','IWM'])
def test_explicit_read_enablement_to_existing_evaluator(symbol):
    db=database(symbol); closing=database(symbol,True)
    with pytest.raises(ValueError):read_latest_option_snapshot(db,symbol,'2026-10-09T14:05:00Z',max_age_seconds=120)
    assert not db.calls
    entry=read_latest_option_snapshot(db,symbol,'2026-10-09T14:05:00Z',max_age_seconds=120,additional_symbols=[symbol])
    exit=read_latest_option_snapshot(closing,symbol,'2026-10-09T14:10:00Z',max_age_seconds=120,additional_symbols=[symbol])
    r=reconstruct_quoted_round_trip(entry,exit,[dict(contract=symbol+'261009C00750000',side='long',quantity=1)],
        entry_as_of='2026-10-09T14:05:00Z',exit_as_of='2026-10-09T14:10:00Z',fee_per_contract_per_side=.65)
    assert r['hypothetical_pnl_usd']==23.70
    assert r['status']=='descriptive_quoted_round_trip_only'
    assert ('eq','symbol',symbol) in db.calls


@pytest.mark.parametrize('defect,reason',[('missing','archive_missing'),('stale','archive_stale_or_future'),
    ('checksum','archive_checksum_mismatch'),('identity','archive_invalid'),('late','archive_not_yet_available'),('storage','archive_unreadable')])
def test_safe_read_failures(defect,reason):
    db=database('NVDA')
    if defect=='missing':db.row=None
    elif defect=='stale':db.row['observed_at']='2026-10-09T13:00:00Z'
    elif defect=='checksum':db.raw+=b'bad'
    elif defect=='identity':db.row['symbol']='IWM'
    elif defect=='late':db.row['created_at']='2026-10-09T14:06:00Z'
    else:db.download=Mock(side_effect=RuntimeError('SECRET_SENTINEL'))
    with pytest.raises(ArchiveUnavailable) as caught:
        read_latest_option_snapshot(db,'NVDA','2026-10-09T14:05:00Z',max_age_seconds=120,additional_symbols=['NVDA'])
    assert caught.value.reason==reason
    assert 'SECRET_SENTINEL' not in str(caught.value)


@pytest.mark.parametrize('defect',['partial','missing_quote','stale_quote','future_quote','terms'])
def test_enabled_symbol_still_requires_trustworthy_evidence(defect):
    db=database('IWM'); closing=database('IWM',True)
    row=db.payload['options']['valid_contracts'][0]
    if defect=='partial':db.payload['options']['status']=db.row['quality_status']='partial'
    elif defect=='missing_quote':row['bid_timestamp']=None
    elif defect=='stale_quote':row['bid_timestamp']='2026-10-09T13:45:00Z'
    elif defect=='future_quote':row['ask_timestamp']='2026-10-09T14:06:00Z'
    else:row['strike']=751
    seal(db)
    entry=read_latest_option_snapshot(db,'IWM','2026-10-09T14:05:00Z',max_age_seconds=120,additional_symbols=['IWM'])
    exit=read_latest_option_snapshot(closing,'IWM','2026-10-09T14:10:00Z',max_age_seconds=120,additional_symbols=['IWM'])
    with pytest.raises(EvidenceRejected):reconstruct_quoted_round_trip(entry,exit,[dict(contract='IWM261009C00750000',side='long',quantity=1)],
        entry_as_of='2026-10-09T14:05:00Z',exit_as_of='2026-10-09T14:10:00Z')


@pytest.mark.parametrize('additional',['NVDA,NVDA','NVDA,','SPY','MSFT','nvda'])
def test_ambiguous_or_unreviewed_collection_rejected(additional):
    with pytest.raises(ValueError):collection_symbols(load_config(),additional=additional)


def test_explicit_pair_collection_core_first_and_duplicate_isolation(monkeypatch):
    setup(monkeypatch);monkeypatch.delenv('ALPHAOS_INTRADAY_CANARY',raising=False)
    monkeypatch.setenv('ALPHAOS_INTRADAY_ADDITIONAL_SYMBOLS','NVDA,IWM')
    called=[]
    monkeypatch.setattr(runner,'find_slot_snapshot',lambda d,p,s,t:dict(quality_status='complete') if s=='NVDA' else None)
    monkeypatch.setattr(runner,'collect_symbol',lambda p,s,c:called.append(s) or dict(observed_at=NOW.isoformat()))
    monkeypatch.setattr(runner,'persist_option_snapshot',lambda d,p,c:dict(p,quality_status='complete'))
    assert runner.main(clock=lambda:NOW)==0
    assert called==['SPY','QQQ','IWM']


def test_conflicting_flags_fail_before_auth(monkeypatch):
    monkeypatch.setenv('ALPHAOS_INTRADAY_CANARY','NVDA')
    monkeypatch.setenv('ALPHAOS_INTRADAY_ADDITIONAL_SYMBOLS','IWM')
    auth=Mock();monkeypatch.setattr(runner.DailyPublicProvider,'from_environment',auth)
    assert runner.main(clock=lambda:NOW)==1
    auth.assert_not_called()


@pytest.mark.parametrize('symbol',['NVDA','IWM'])
def test_two_symbol_opt_in_uses_original_constructor(symbol):
    class Provider:
        name='Public'
        def now(self):return NOW
        def underlying(self,s):return dict(instrument=dict(symbol=s,type='EQUITY'),outcome='SUCCESS',last=100,lastTimestamp=NOW.isoformat())
        def expirations(self,s):return ['2026-10-09']
        def chain(self,s,e):return dict(calls=[dict(instrument=dict(symbol=s+'261009C00100000',type='OPTION'),
            optionDetails=dict(strikePrice=100),outcome='SUCCESS',bid=2,ask=2.1,
            bidTimestamp=NOW.isoformat(),askTimestamp=NOW.isoformat())],puts=[])
    r=collect_symbol(Provider(),symbol,dict(load_config(),additional_symbols='NVDA,IWM'))
    assert r['options']['status']=='complete'
    assert r['options']['valid_contracts'][0]['symbol']==symbol


def test_defaults_and_capability_listing_do_not_enable_optional_symbols():
    assert enabled_archive_symbols()==['SPY','QQQ']
    assert collection_symbols(load_config())==['SPY','QQQ']
    assert collection_symbols(load_config(),'NVDA')==['SPY','QQQ','NVDA']
    assert collection_symbols(load_config(),additional='NVDA,IWM')==['SPY','QQQ','NVDA','IWM']
