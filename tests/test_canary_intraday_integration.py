"""Combined read-only fixture boundary; no production credentials or writes."""
import gzip
import hashlib
import json
from unittest.mock import Mock
import pytest
from modules.supabase_archive import read_latest_option_snapshot, ArchiveUnavailable
from modules.intraday_quoted_round_trip import reconstruct_quoted_round_trip, EvidenceRejected
from tests.test_archive_read_path import ReadOnlyClient
from tests.test_intraday_quoted_round_trip import snapshot, CONTRACT, compute
from tests.test_intraday_execution import setup, NOW
from scripts import run_intraday_snapshot as runner


def client(exit=False):
    value=snapshot(exit=exit)
    db=ReadOnlyClient()
    db.payload=value['payload']
    db.raw=gzip.compress(json.dumps(db.payload).encode(),mtime=0)
    db.row=dict(value['metadata'],id='exit' if exit else 'entry',slot_time=None,
        archive_path='options/symbol=SPY/date=2026-10-09/fixture.json.gz',
        archive_sha256=hashlib.sha256(db.raw).hexdigest())
    return db


def test_verified_reader_to_descriptive_evaluator():
    entry=read_latest_option_snapshot(client(),'SPY','2026-10-09T14:05:00Z',max_age_seconds=120)
    exit=read_latest_option_snapshot(client(True),'SPY','2026-10-09T14:10:00Z',max_age_seconds=120)
    r=reconstruct_quoted_round_trip(entry,exit,[dict(contract=CONTRACT,side='long',quantity=1)],
        entry_as_of='2026-10-09T14:05:00Z',exit_as_of='2026-10-09T14:10:00Z',fee_per_contract_per_side=.65)
    assert r['hypothetical_pnl_usd']==23.70
    assert r['status']=='descriptive_quoted_round_trip_only'
    assert 'not_pop_ev_or_trading_recommendation' in r['limitations']


@pytest.mark.parametrize('defect',['checksum','missing','stale'])
def test_reader_rejects_before_evaluation(defect):
    db=client()
    if defect=='checksum':db.row['archive_sha256']='0'*64
    if defect=='missing':db.row=None
    if defect=='stale':db.row['observed_at']='2026-10-09T13:00:00Z'
    with pytest.raises(ArchiveUnavailable):
        read_latest_option_snapshot(db,'SPY','2026-10-09T14:05:00Z',max_age_seconds=120)


@pytest.mark.parametrize('bucket',['valid_contracts','questionable_contracts','rejected_contracts'])
@pytest.mark.parametrize('value',[None,{},''])
def test_malformed_bucket_typed_rejection(bucket,value):
    entry=snapshot();entry['payload']['options'][bucket]=value
    with pytest.raises(EvidenceRejected,match='contract_buckets_missing_or_invalid'):compute(entry=entry)


@pytest.mark.parametrize('field',['quality_warnings','rejection_reasons'])
@pytest.mark.parametrize('value',[None,False,''])
def test_unknown_quality_is_not_clean_quality(field,value):
    entry=snapshot();entry['payload']['options']['valid_contracts'][0][field]=value
    with pytest.raises(EvidenceRejected,match='contract_quality_unusable'):compute(entry=entry)


@pytest.mark.parametrize('setting',[None,'','none'])
def test_default_collection_remains_core(monkeypatch,setting):
    setup(monkeypatch)
    if setting is None:monkeypatch.delenv('ALPHAOS_INTRADAY_CANARY',raising=False)
    else:monkeypatch.setenv('ALPHAOS_INTRADAY_CANARY',setting)
    collect=Mock(return_value=dict(observed_at=NOW.isoformat()))
    monkeypatch.setattr(runner,'collect_symbol',collect)
    monkeypatch.setattr(runner,'persist_option_snapshot',lambda d,p,c:dict(p,quality_status='complete'))
    assert runner.main(clock=lambda:NOW,sleep=lambda _:None)==0
    assert [c.args[1] for c in collect.call_args_list]==['SPY','QQQ']


@pytest.mark.parametrize('symbol',['NVDA','IWM'])
def test_collection_opt_in_does_not_expand_research_reader(symbol):
    with pytest.raises(ValueError):read_latest_option_snapshot(client(),symbol,'2026-10-09T14:05:00Z',max_age_seconds=120)
