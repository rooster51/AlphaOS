"""Issue #49: stage truth, source schema parity and safe correlated boundaries."""
import asyncio
import importlib
import json
import logging
import re

import pandas as pd
import pytest
from alphaos_api.research2 import MarketRequest
from modules.supabase_archive import ArchiveUnavailable
from tests.test_research2_api import boundary, post
from tests.test_candidate_generation_diagnostics import prepare
from tests.test_run_market import history
from test_mcp_api import login, call


def prepare_breakout(boundary,symbol):
    client,storage,service=prepare(boundary,symbol)
    bars=history();bars['date']=pd.bdate_range(end='2026-10-15',periods=len(bars));bars['symbol']=symbol
    bars.loc[bars.index[-21:-1],['open','close','high','low']]=[100,100,101,99]
    bars.loc[bars.index[-1],['open','close','high','low']]=[110,110,111,109]
    service.history_loader=lambda _:bars.copy()
    return client,storage,service


@pytest.mark.parametrize('symbol', ['SPY','QQQ'])
@pytest.mark.parametrize('mode', ['current','historical'])
def test_unknown_direction_breakout_has_no_supported_route_not_bad_quotes_or_capital(boundary,symbol,mode):
    client,storage,service=prepare_breakout(boundary,symbol)
    request=dict(symbol=symbol,expiration='2026-10-19',available_capital=150,research_mode=mode)
    result=post(client,'market',request)
    assert result.status_code==200,result.text
    data=result.json()
    if symbol=='QQQ' and mode=='current':
        from pathlib import Path
        from tests.test_website_mcp_parity import expected_fixture
        fixture=json.loads((Path(__file__).parents[1]/'web/tests/fixtures/unsupported-routes-parity.json').read_text())
        assert data==expected_fixture(fixture['response'])
    session=data['research']['research_session'];d=session['diagnostics']
    assert session['opportunity_state']['direction']=='unknown'
    assert session['opportunity_state']['movement_state']=='breakout'
    assert session['strategy_routes']['routes']==['long_option','directional_debit_spread','directional_bwb']
    assert d['zero_candidate_reason']=='no_supported_constructor_route'
    assert d['clean_contract_counts']=={'calls':2,'puts':2}
    assert not session['candidates'] and d['capital_rejection_count']==0
    stages={s['stage']:s for s in d['pipeline']}
    assert stages['routing']['reason_counts']=={'no_supported_constructor_route':3}
    assert stages['routing']['output_count']==0
    assert all(stages[s]['status']=='not_attempted' for s in ['construction','economics','capital_eligibility'])
    _,tokens=login(client)
    assert call(client,tokens['access_token'],'run_market',request)['structuredContent']==data


def test_mcp_argument_properties_match_rest_including_historical_mode():
    app=importlib.import_module('alphaos_api.app').app
    tools=asyncio.run(app.state.mcp.list_tools())
    assert len(tools)==17
    schema=next(t for t in tools if t.name=='run_market').model_dump(mode='json',by_alias=True)['inputSchema']
    model=MarketRequest.model_json_schema()
    assert schema['properties']==model['properties']
    assert schema['required']==model['required']
    assert schema['properties']['research_mode']['default']=='current'
    assert schema['properties']['research_mode']['enum']==['current','historical']


@pytest.mark.parametrize('case,status,code', [('archive',503,'archive_unavailable'),('unexpected',500,'internal_error'),('auth',401,'authentication_required')])
def test_backend_errors_are_correlated_and_logs_are_allowlisted(boundary,monkeypatch,caplog,case,status,code):
    client,_,service,_=boundary
    def broken(*args,**kwargs):
        if case=='archive':raise ArchiveUnavailable('DO_NOT_LOG_storage_url_or_key')
        raise RuntimeError('DO_NOT_LOG_sdk_token')
    monkeypatch.setattr(service,'read_snapshot',broken)
    if case=='unexpected':monkeypatch.setattr(service,'run',broken)
    correlation='a'*32
    headers={'X-AlphaOS-Request-ID':correlation,'Authorization':'Bearer owner-test-secret' if case!='auth' else ''}
    with caplog.at_level(logging.WARNING,logger='alphaos_api.research'):
        response=client.post('/v1/research/market',json={'symbol':'QQQ','objective':'DO_NOT_LOG_objective'},headers=headers)
    assert response.status_code==status
    assert response.json()['error']['code']==code
    assert response.headers['X-AlphaOS-Request-ID']==correlation
    records=[r for r in caplog.records if r.name=='alphaos_api.research']
    record=json.loads(records[-1].getMessage().removeprefix('research_request '))
    assert record['code']==code and record['status']==status and record['elapsed_ms']>=0
    assert set(record)=={'request_id','code','status','elapsed_ms'}
    assert 'DO_NOT_LOG' not in caplog.text and 'owner-test-secret' not in caplog.text
    assert response.headers['cache-control']=='no-store'


def test_invalid_correlation_is_replaced_and_success_has_no_error_log(boundary,caplog):
    client,_,_=prepare(boundary,'SPY')
    response=client.post('/v1/research/market',json={'symbol':'SPY'},headers={'Authorization':'Bearer owner-test-secret','X-AlphaOS-Request-ID':'sensitive-value'})
    assert response.status_code==200
    assert re.fullmatch('[0-9a-f]{32}',response.headers['X-AlphaOS-Request-ID'])
    assert not [r for r in caplog.records if r.name=='alphaos_api.research']
