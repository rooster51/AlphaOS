"""Real verified fixture reader; observation scope never implies research ran."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter

import pytest

from tests.test_research2_api import boundary, post
from tests.test_pipeline_performance import prepare_dense
from test_mcp_api import login, call


@pytest.mark.parametrize('mode',['current','historical'])
@pytest.mark.parametrize('expiry',['2030-01-02','2030-01-04','2030-01-18','2031-01-17'])
def test_observation_matches_full_archive_metadata_without_history_or_economics(boundary,mode,expiry):
    client,storages,service,_=prepare_dense(boundary)
    if mode=='historical': service.clock=lambda:datetime.fromisoformat('2030-01-03T23:00:00+00:00')
    original=service.history_loader
    calls=[]
    def forbidden(*args):
        calls.append(args)
        raise AssertionError('Observation must not initialize provider/history')
    service.history_loader=forbidden
    data={}
    for _ in range(2):
        def invoke(index):
            symbol=('SPY','QQQ')[index%2]; start=perf_counter()
            response=post(client,'observation',dict(symbol=symbol,research_mode=mode,expiration=expiry))
            assert response.status_code==200,response.text
            result=response.json()
            from alphaos_api.research2 import ObservationResponse
            ObservationResponse.model_validate(result)
            assert result['schema_version']=='alphaos-observation-v1'
            assert result['research_performed'] is False and result['verified_for_trading'] is False
            assert 'research_session' not in result and 'candidates' not in result
            assert result['expiration']==expiry
            assert result['archive']['storage']['archive_sha256']==storages[symbol].row['archive_sha256']
            assert len(response.content)<10000
            assert perf_counter()-start<3
            return symbol,result
        with ThreadPoolExecutor(4) as pool:
            for symbol,result in pool.map(invoke,range(4)): data[symbol]=result
    assert not calls
    service.history_loader=original
    for symbol,observed in data.items():
        full=post(client,'market',dict(symbol=symbol,research_mode=mode,expiration=expiry,available_capital=150)).json()['research']
        assert observed['as_of']==full['as_of']
        assert observed['spot']==full['research_session']['market']['spot']
        for key in ('storage','freshness','diagnostics','provider','session_date'):
            assert observed['archive'][key]==full['archive'][key]


@pytest.mark.parametrize('defect,code',[('stale','archive_stale'),('missing','archive_missing'),('corrupt','archive_unavailable')])
def test_observation_fails_closed_without_history(boundary,defect,code):
    client,storage,service,loader=boundary
    if defect=='stale': service.clock=lambda:datetime.fromisoformat('2030-01-02T23:00:00+00:00')
    elif defect=='missing': storage.row=None
    else: storage.raw=b'corrupt'
    response=post(client,'observation',{'symbol':'QQQ'})
    assert response.status_code==503
    assert response.json()['error']['code']==code
    loader.assert_not_called()


@pytest.mark.parametrize('field,value',[('width',5),('available_capital',150),('objective','test')])
def test_observation_rejects_research_parameters(boundary,field,value):
    assert post(boundary[0],'observation',dict(symbol='QQQ',**{field:value})).status_code==422


def test_observation_missing_expiration_never_substitutes(boundary):
    response=post(boundary[0],'observation',dict(symbol='QQQ',expiration='2031-01-17'))
    assert response.status_code==422 and response.json()['error']['code']=='archive_expiration_unavailable'
    boundary[3].assert_not_called()


def test_full_rest_mcp_still_return_research(boundary):
    client,_,_,_=boundary
    request=dict(symbol='QQQ',available_capital=150,width=1)
    expected=post(client,'market',request).json()
    _,tokens=login(client)
    result=call(client,tokens['access_token'],'run_market',request)
    assert result['structuredContent']==expected
    assert expected['schema_version']=='alphaos-interface-v2'
    assert 'candidates' in expected['research']['research_session']


def test_encoder_retains_redaction_nonfinite_and_large_integer_compatibility(monkeypatch):
    from alphaos_api.app import respond
    monkeypatch.setenv('PUBLIC_API_SECRET','test-secret')
    value=dict(schema_version='alphaos-interface-v2',text='test-secret',bad=float('nan'),profit=float('inf'),large=2**80)
    decoded=json.loads(respond(value).body)
    assert decoded==dict(schema_version='alphaos-interface-v2',text='[REDACTED]',bad=None,profit='unlimited',large=2**80)


def test_cold_observation_does_not_import_public_sdk():
    code='''
import sys
# Fixture helpers use pytest's top-level test-module imports. A fresh child
# does not inherit pytest's sys.path changes.
sys.path.insert(0, sys.argv[1])
from datetime import datetime
from alphaos_api.research2 import ArchiveResearchService, ObservationRequest
from tests.performance_archive_fixture import dense_storage,AS_OF
from modules.supabase_archive import read_latest_option_snapshot
s=dense_storage('SPY',production_scale=True)
service=ArchiveResearchService(read_snapshot=lambda symbol,as_of:read_latest_option_snapshot(s,symbol,as_of,max_age_seconds=300),history_loader=lambda _:(_ for _ in ()).throw(AssertionError()),clock=lambda:datetime.fromisoformat(AS_OF))
assert service.observe(ObservationRequest(symbol='SPY'))['research_performed'] is False
assert 'public_api_sdk' not in sys.modules
'''
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, '-c', code, str(root / 'tests')],
        cwd=root, env={**os.environ, 'PYTHONPATH': str(root)},
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f'Cold observation subprocess exited {result.returncode}\n'
        f'stdout:\n{result.stdout}\nstderr:\n{result.stderr}'
    )
