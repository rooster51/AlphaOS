from datetime import datetime
from functools import partial
import gzip
import hashlib
import json
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal
import pytest

from alphaos_api.research2 import ArchiveResearchService, StructureRequest
from modules.supabase_archive import read_latest_option_snapshot
from tests.test_archive_read_path import ReadOnlyClient
from tests.test_research2_api import boundary, post
from tests.test_mcp_api import login, call


@pytest.fixture
def trusted():
    schedule=mcal.get_calendar('NYSE').schedule(start_date='2021-01-01',end_date='2026-10-08')
    i=np.arange(len(schedule)); close=100+2*np.sin(i/10)+.2*np.cos(i/3)
    bars=pd.DataFrame(dict(date=schedule.index,symbol='QQQ',open=close,
        close=close,high=close+1,low=close-1,volume=1000))
    storage=ReadOnlyClient()
    storage.payload.update(session='2026-10-08',observed_at='2026-10-08T19:56:00+00:00',
        slot_time='2026-10-08T19:55:00+00:00',collection_finished_at='2026-10-08T19:57:00+00:00')
    storage.row.update(session_date='2026-10-08',observed_at=storage.payload['observed_at'],
        slot_time=storage.payload['slot_time'],created_at='2026-10-08T19:57:01+00:00',
        archive_path='options/symbol=QQQ/date=2026-10-08/fixture.json.gz')
    storage.raw=gzip.compress(json.dumps(storage.payload).encode())
    storage.row['archive_sha256']=hashlib.sha256(storage.raw).hexdigest()
    loader=Mock(return_value=bars)
    service=ArchiveResearchService(read_snapshot=partial(read_latest_option_snapshot,storage,max_age_seconds=600),
        history_loader=loader,clock=lambda:datetime.fromisoformat('2026-10-09T15:00:00+00:00'))
    return service,float(close[-1]),storage,loader


def request(spot,legs=None,credit=-2,**kwargs):
    return StructureRequest(symbol='QQQ',expiration='2026-10-09',as_of='2026-10-08',spot=spot,
        credit=credit,fees=1,legs=legs or [dict(type='Call',strike=100,qty=1)],**kwargs)


def test_real_reader_history_selector_adapter_and_evaluator(trusted):
    service,spot,storage,loader=trusted
    data=service.structure(request(spot))['research']['historical_economics']
    assert data['economics_coverage']=='historical_expiration',data['missing_evidence']
    assert data['sample_size']>=30
    assert data['historical_economics']['expected_value_dollars'] is not None
    assert data['eligible_for_consideration'] is False
    assert data['provenance']['archive_age_at_cutoff_seconds']==240
    assert data['provenance']['archive_age_at_request_seconds']>600
    assert data['provenance']['verification']=='server_verified_archive_reader'
    assert data['evidence']['quote_age_seconds'] is None
    assert data['execution_evidence']['status']=='unavailable'
    json.dumps(data,allow_nan=False)


@pytest.mark.parametrize('defect,reason',[
    ('checksum','verified_archive_unavailable'),('stale','verified_archive_unavailable'),
    ('history','historical_evidence_validation_failed'),('spot','scenario_spot_differs_from_completed_close'),
    ('intraday','as_of_session_not_complete'),('small','historical_evidence_validation_failed'),
])
def test_fail_closed_preserves_deterministic_output(trusted,defect,reason):
    service,spot,storage,loader=trusted
    if defect=='checksum':storage.row['archive_sha256']='bad'
    if defect=='stale':storage.row['observed_at']='2026-10-08T19:00:00Z'
    if defect=='history':loader.side_effect=RuntimeError('sensitive diagnostic')
    if defect=='spot':spot+=1
    if defect=='intraday':service.clock=lambda:datetime.fromisoformat('2026-10-08T19:00:00Z')
    if defect=='small':loader.return_value=loader.return_value.iloc[-10:]
    response=service.structure(request(spot))
    result=response['research']['historical_economics']
    assert reason in result['missing_evidence']
    assert result['historical_economics']['expected_value_dollars'] is None
    assert result['deterministic_expiration']['max_loss']==201
    assert 'sensitive' not in json.dumps(response)


def test_research_structure_rest_mcp_exact_parity(boundary,trusted,monkeypatch):
    client,_,service,_=boundary
    wired,spot,_,_=trusted
    monkeypatch.setattr(service,'read_snapshot',wired.read_snapshot)
    monkeypatch.setattr(service,'history_loader',wired.history_loader)
    monkeypatch.setattr(service,'clock',wired.clock)
    body=request(spot).model_dump(mode='json')
    rest=post(client,'structure',body)
    assert rest.status_code==200
    assert rest.json()['research']['historical_economics']['economics_coverage']=='historical_expiration'
    _,tokens=login(client)
    mcp=call(client,tokens['access_token'],'research_structure',{'structure':body})
    assert mcp['structuredContent']==rest.json()


def test_common_fingerprint_independent_of_structure(trusted):
    service,spot,_,_=trusted
    a=service.structure(request(spot))['research']['historical_economics']
    b=service.structure(request(spot,[dict(type='Put',strike=100,qty=1)]))['research']['historical_economics']
    assert a['evidence']['fingerprint']==b['evidence']['fingerprint']


def test_supported_families_share_integration_and_capital_status(trusted):
    service,spot,_,_=trusted
    cases=[([('Call',100,1)],-2),([('Put',100,1)],-2),
        ([('Call',100,1),('Call',105,-1)],-2),([('Put',95,-1),('Put',100,1)],-2),
        ([('Put',95,1),('Put',100,-1)],2),([('Call',100,-1),('Call',105,1)],2),
        ([('Call',95,1),('Call',100,-2),('Call',105,1)],-1),
        ([('Call',95,1),('Call',100,-2),('Call',110,1)],1),
        ([('Put',90,1),('Put',100,-2),('Put',105,1)],1),
        ([('Put',90,1),('Put',95,-1),('Call',105,-1),('Call',110,1)],2)]
    fingerprints=set()
    for legs,credit in cases:
        r=service.structure(request(spot,[dict(type=t,strike=k,qty=q) for t,k,q in legs],credit))
        e=r['research']['historical_economics']
        assert e['economics_coverage']=='historical_expiration'
        assert not e['eligible_for_consideration']
        assert e['capital_eligibility']['status']=='not_assessed'
        fingerprints.add(e['evidence']['fingerprint'])
    assert len(fingerprints)==1


def test_weekend_is_not_counted_as_expiration_session(trusted):
    service,spot,_,_=trusted
    r=request(spot).model_copy(update={'expiration':datetime(2026,10,12).date()})
    result=service.structure(r)['research']['historical_economics']
    assert result['evidence']['horizon_sessions']==2


@pytest.mark.parametrize('date_value', ['2026-10-10','2026-12-25'])
def test_non_session_expiration_rejected_without_fabrication(trusted,date_value):
    service,spot,_,loader=trusted
    r=request(spot).model_copy(update={'expiration':datetime.fromisoformat(date_value).date()})
    result=service.structure(r)['research']['historical_economics']
    assert 'expiration_not_exchange_session' in result['missing_evidence']
    loader.assert_not_called()
