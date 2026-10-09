"""Market-entry temporal gates; all archive/provider data are fixtures."""
from copy import deepcopy
from datetime import datetime
from unittest.mock import Mock

import pytest

from modules import structure_economics
from modules.run_market import run_market, attach_market_economics
from tests.test_run_market import history
from tests.test_market_archive_adapter import payload
from tests.test_opportunity_session import run, trade
from tests.test_research2_api import boundary, post
from tests.test_mcp_api import login, call


def assert_unavailable(economics):
    assert all(value is None for value in economics['historical_economics'].values())
    assert economics['sample_size']==0 and economics['evidence'] is None
    assert not economics['eligible_for_consideration']
    assert economics['economics_coverage']=='deterministic_only'
    assert economics['execution_evidence']['status']=='unavailable'
    assert economics['intraday_economics']['expected_value_dollars'] is None
    assert economics['early_exit']['status']=='unavailable'
    assert economics['capital_requirement']['broker_buying_power'] is None
    assert 'intraday_entry_not_completed_session' in economics['missing_evidence']


def test_market_shared_gate_no_reanchoring_or_extra_reads(monkeypatch):
    original=structure_economics.prepare_structure_evidence
    builder=Mock(wraps=original)
    selector=Mock(side_effect=AssertionError('Intraday must not select daily analogs'))
    monkeypatch.setattr(structure_economics,'prepare_structure_evidence',builder)
    monkeypatch.setattr(structure_economics,'analog_research',selector)
    result=run_market(payload(),history=history(),available_capital=150)
    session=result['research_session']
    assert session['candidates']
    assert builder.call_count==1
    selector.assert_not_called()
    comparison=session['historical_comparison']
    assert comparison['candidate_group_ids']==[0]*len(session['candidates'])
    assert comparison['comparability_representation']=='groups_only'
    assert comparison['pairwise_comparability']==[] # discovery output stays linear in candidate count
    assert not comparison['groups'][0]['directly_comparable']
    for candidate in session['candidates']:
        e=candidate['research']['historical_economics']
        assert_unavailable(e)
        assert e['deterministic_expiration']['max_loss']==candidate['research']['capital_at_risk']
        assert e['capital_eligibility']['available_capital']==150
        assert e['capital_eligibility']['status']=='within_expiration_loss_budget'
        assert not e['overnight_exposure']['required_to_hold_to_expiration']
    assert session['holding_policy']['preference']=='avoid_overnight_exposure'
    assert any(e['reason']=='exceeds_available_capital' for e in session['excluded'])
    assert session['comparison']['winner'] is session['comparison']['recommendation'] is None


@pytest.mark.parametrize('direction',['bullish','bearish'])
def test_all_existing_directional_discovery_preserved(direction):
    session=run(direction)
    before=deepcopy(session)
    attach_market_economics(session,observed_at='2030-01-02T20:30:00Z')
    assert len(session['candidates'])==len(before['candidates'])
    assert session['comparison']==before['comparison']
    assert session['strategy_routes']==before['strategy_routes']
    assert session['excluded']==before['excluded']
    for old,new in zip(before['candidates'],session['candidates']):
        assert new['input_index']==old['input_index']
        assert new['research']['trade']==old['research']['trade']
        assert_unavailable(new['research']['historical_economics'])
        assert new['research']['historical_economics']['overnight_exposure']['required_to_hold_to_expiration']


def test_condor_symmetric_and_broken_wing_butterfly_coverage():
    sessions=[run('bullish'),run('bearish'),run(
        market={'spot':500,'opportunity_state':{'movement_state':'range_bound'}},
        candidates=[trade([('Put',490,1),('Put',495,-1),('Call',505,-1),('Call',510,1)],2),
                    trade([('Call',495,1),('Call',500,-2),('Call',505,1)],-1)])]
    families=set()
    for session in sessions:
        attach_market_economics(session,observed_at='2030-01-02T20:30:00Z')
        for c in session['candidates']:
            families.add(c['strategy_family'])
            assert_unavailable(c['research']['historical_economics'])
    assert {'long_call','long_put','call_debit_spread','put_debit_spread','put_credit_spread',
            'call_credit_spread','bullish_bwb','bearish_bwb','iron_condor','butterfly'}<=families


@pytest.mark.parametrize('expiration',['2030-01-02','2030-01-03','2030-01-08'])
def test_zero_dte_future_and_unsupported_horizons_stay_null(expiration):
    p=payload()
    p['options']['requested_expirations']=[expiration]
    for row in p['options']['valid_contracts']: row['expiration']=expiration
    result=run_market(p,history=history(),expiration=expiration)
    candidates=result['research_session']['candidates']
    assert candidates
    for c in candidates: assert_unavailable(c['research']['historical_economics'])


def test_later_clock_does_not_make_intraday_entry_completed():
    reader,loader=Mock(),Mock()
    t=dict(symbol='QQQ',spot=500,expiration='2030-01-03')
    bundle=structure_economics.prepare_structure_evidence(t,as_of='2030-01-02',
        now=datetime.fromisoformat('2030-01-03T12:00:00Z'),read_snapshot=reader,
        history_loader=loader,entry_observed_at='2030-01-02T20:30:00Z')
    assert bundle['missing_reason']=='intraday_entry_not_completed_session'
    reader.assert_not_called(); loader.assert_not_called()


def test_market_rest_mcp_economics_parity(boundary):
    client,_,service,loader=boundary
    service.read_snapshot=Mock(wraps=service.read_snapshot)
    body=dict(symbol='QQQ',available_capital=150)
    rest=post(client,'market',body)
    assert rest.status_code==200
    candidates=rest.json()['research']['research_session']['candidates']
    assert candidates
    for c in candidates: assert_unavailable(c['research']['historical_economics'])
    assert service.read_snapshot.call_count==loader.call_count==1
    _,tokens=login(client)
    mcp=call(client,tokens['access_token'],'run_market',body)
    assert mcp['structuredContent']==rest.json()
    assert service.read_snapshot.call_count==loader.call_count==2


def test_no_candidate_empty_groups_and_no_invention():
    session=run_market(payload())['research_session']
    assert not session['candidates']
    assert session['historical_comparison']['groups']==[]
    assert session['historical_comparison']['winner'] is None
