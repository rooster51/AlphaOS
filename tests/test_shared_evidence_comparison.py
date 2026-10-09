from datetime import date, datetime
from unittest.mock import Mock

import pytest

from alphaos_api.research2 import StructuresRequest
from modules import structure_economics as economics
from tests.test_structure_economics_integration import trusted, request
from tests.test_research2_api import boundary, post
from tests.test_mcp_api import login, call


CASES = [([('Call',100,1)],-2), ([('Put',100,1)],-2),
    ([('Call',100,1),('Call',105,-1)],-2),
    ([('Put',95,1),('Put',100,-1)],2),
    ([('Call',95,1),('Call',100,-2),('Call',105,1)],-1),
    ([('Call',95,1),('Call',100,-2),('Call',110,1)],1),
    ([('Put',90,1),('Put',100,-2),('Put',105,1)],1),
    ([('Put',90,1),('Put',95,-1),('Call',105,-1),('Call',110,1)],2)]


def compare(service, items):
    return service.compare(StructuresRequest(structures=items))['research']


def test_shared_sample_all_payoffs_and_order(trusted, monkeypatch):
    service, spot, _, loader = trusted
    reader = Mock(wraps=service.read_snapshot)
    service.read_snapshot = reader
    adapter = Mock(wraps=economics.build_scenario_evidence)
    selector = Mock(wraps=economics.analog_research)
    monkeypatch.setattr(economics, 'build_scenario_evidence', adapter)
    monkeypatch.setattr(economics, 'analog_research', selector)
    items = [request(spot, [dict(type=t,strike=k,qty=q) for t,k,q in legs], credit)
             .model_copy(update={'fees': float(i+1)}) for i,(legs,credit) in enumerate(CASES)]
    result = compare(service, items)
    assert reader.call_count == loader.call_count == adapter.call_count == selector.call_count == 1
    # Reconstruct terminal prices independently from the selector's validated outcomes.
    bundle = economics.prepare_structure_evidence(result['candidates'][0]['trade'],
        as_of='2026-10-08', now=service.clock(), read_snapshot=service.read_snapshot,
        history_loader=service.history_loader)
    terminal = {s.observation_id: spot*(1+s.terminal_return) for s in bundle['evidence'].scenarios}
    fingerprints = set()
    for candidate, item in zip(result['candidates'], items):
        assert candidate['trade']['legs'] == [leg.model_dump() for leg in item.legs]
        e = candidate['historical_economics']
        fingerprints.add(e['evidence']['fingerprint'])
        values = []
        for observation in e['scenario_payoffs']:
            price = terminal[observation['observation_id']]
            intrinsic = sum(leg.qty*max((price-leg.strike) if leg.type=='Call' else (leg.strike-price),0)
                            for leg in item.legs)
            expected = (intrinsic+item.credit)*100-item.fees
            assert observation['payoff_dollars'] == pytest.approx(expected)
            values.append(expected)
        assert e['historical_economics']['expected_value_dollars'] == pytest.approx(sum(values)/len(values))
        assert not e['eligible_for_consideration']
        assert e['capital_eligibility']['status']=='not_assessed'
        assert e['execution_evidence']['status']=='unavailable'
        assert e['early_exit']['status']=='unavailable'
    assert len(fingerprints)==1
    assert all(p['directly_comparable'] for p in result['historical_comparison']['pairwise_comparability'])
    assert result['comparison']['winner'] is result['comparison']['recommendation'] is None


def test_interleaved_context_groups(trusted):
    service,spot,_,loader=trusted
    service.read_snapshot=Mock(wraps=service.read_snapshot)
    a=request(spot)
    b=a.model_copy(update={'expiration':date(2026,10,12)})
    result=compare(service,[a,b,a])
    h=result['historical_comparison']
    assert h['candidate_group_ids']==[0,1,0]
    assert service.read_snapshot.call_count==loader.call_count==2
    assert [g['context']['horizon_sessions'] for g in h['groups']]==[1,2]
    assert h['groups'][0]['evidence_fingerprints']!=h['groups'][1]['evidence_fingerprints']
    assert [p['directly_comparable'] for p in h['pairwise_comparability']]==[False,True,False]
    assert h['pairwise_comparability'][0]['missing_reason']=='different_evidence_context'


@pytest.mark.parametrize('field,value', [('spot',101.0),('symbol','SPY'),('as_of',date(2026,10,7))])
def test_other_context_dimensions_never_share(trusted,field,value):
    service,spot,_,_=trusted
    a=request(spot)
    h=compare(service,[a,a.model_copy(update={field:value})])['historical_comparison']
    assert h['candidate_group_ids']==[0,1]
    assert not h['pairwise_comparability'][0]['directly_comparable']


@pytest.mark.parametrize('defect,reason',[
    ('missing','verified_archive_unavailable'),('stale','verified_archive_unavailable'),
    ('incomplete','as_of_session_not_complete'),('horizon','unsupported_expiration_session_horizon'),
    ('gap','historical_evidence_validation_failed')])
def test_group_failure_reused_and_null(trusted,defect,reason):
    service,spot,storage,loader=trusted
    if defect=='missing': service.read_snapshot=Mock(side_effect=RuntimeError('secret'))
    else: service.read_snapshot=Mock(wraps=service.read_snapshot)
    if defect=='stale': storage.row['observed_at']='2026-10-08T19:00:00Z'
    if defect=='incomplete': service.clock=lambda:datetime.fromisoformat('2026-10-08T19:00:00Z')
    if defect=='gap': loader.return_value=loader.return_value.drop(loader.return_value.index[-5])
    item=request(spot)
    if defect=='horizon': item=item.model_copy(update={'expiration':date(2026,10,14)}) # 4 sessions
    result=compare(service,[item,item])
    assert service.read_snapshot.call_count==(0 if defect in ('incomplete','horizon') else 1)
    assert loader.call_count==(1 if defect=='gap' else 0)
    for c in result['candidates']:
        e=c['historical_economics']
        assert reason in e['missing_evidence']
        assert e['historical_economics']['expected_value_dollars'] is None
        assert not e['eligible_for_consideration']
    assert not result['historical_comparison']['pairwise_comparability'][0]['directly_comparable']


def test_twenty_candidates_single_build(trusted):
    service,spot,_,loader=trusted
    result=compare(service,[request(spot)]*20)
    assert len(result['candidates'])==20
    assert loader.call_count==1
    assert len(result['historical_comparison']['pairwise_comparability'])==190
    with pytest.raises(ValueError): StructuresRequest(structures=[request(spot)]*21)


def test_comparison_rest_mcp_exact_parity(boundary,trusted,monkeypatch):
    client,_,service,_=boundary
    wired,spot,_,_=trusted
    for attr in ('read_snapshot','history_loader','clock'):
        monkeypatch.setattr(service,attr,getattr(wired,attr))
    body={'structures':[request(spot).model_dump(mode='json'),
        request(spot,[dict(type='Put',strike=100,qty=1)]).model_dump(mode='json')]}
    rest=post(client,'structures/compare',body)
    assert rest.status_code==200
    assert rest.json()['research']['historical_comparison']['groups'][0]['evidence_available']
    _,tokens=login(client)
    mcp=call(client,tokens['access_token'],'compare_structures',{'comparison':body})
    assert mcp['structuredContent']==rest.json()


def test_fingerprint_mismatch_fails_comparability(trusted,monkeypatch):
    service,spot,_,_=trusted
    original=economics.evaluate_structure_evidence
    calls=[]
    def altered(*args,**kwargs):
        result=original(*args,**kwargs)
        calls.append(result)
        if len(calls)==2: result['evidence']['fingerprint']='different'
        return result
    monkeypatch.setattr(economics,'evaluate_structure_evidence',altered)
    result=compare(service,[request(spot),request(spot)])
    pair=result['historical_comparison']['pairwise_comparability'][0]
    assert not pair['directly_comparable']
    assert pair['missing_reason']=='different_evidence_fingerprint'
    calls[0]['provenance']['verification']='changed'
    assert calls[1]['provenance']['verification']=='server_verified_archive_reader'


def test_deterministic_comparison_unchanged(trusted):
    from modules.strategy_compare import compare_strategy_research
    service,spot,_,_=trusted
    items=[request(spot),request(spot,[dict(type='Put',strike=100,qty=1)])]
    expected=compare_strategy_research([service._structure(item) for item in items])
    from alphaos_api.research2 import json_safe
    assert compare(service,items)['comparison']==json_safe(expected)
