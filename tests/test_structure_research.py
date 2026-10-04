from copy import deepcopy
from datetime import date
import pytest

from modules.structure_research import research_structure,discover_debit_spreads
from modules.opportunity_router import opportunity_state,research_routed_structures
from modules.options_payoff import trade_analysis
from modules.premium_engine import demo_chain,generate


def trade(legs,credit,**extra):
    return dict(symbol='QQQ',expiration='2030-01-18',spot=100,credit=credit,shares=0,fees=0,
        legs=[dict(type=k,strike=s,qty=q) for k,s,q in legs],**extra)


@pytest.mark.parametrize('legs,credit,family,profit,loss,roots',[
    ([('Call',100,1),('Call',105,-1)],-2,'call_debit_spread',300,200,[102]),
    ([('Put',100,1),('Put',95,-1)],-2,'put_debit_spread',300,200,[98]),
    ([('Call',95,1),('Call',100,-2),('Call',105,1)],-2,'butterfly',300,200,[97,103]),
    ([('Put',95,1),('Put',100,-2),('Put',105,1)],-2,'butterfly',300,200,[97,103]),
    ([('Put',90,1),('Put',100,-2),('Put',105,1)],1,'bullish_bwb',600,400,[94]),
    ([('Call',95,1),('Call',100,-2),('Call',110,1)],1,'bearish_bwb',600,400,[106]),
    ([('Put',90,1),('Put',95,-1),('Call',105,-1),('Call',115,1)],2,'iron_condor',200,800,[93,107]),
    ([('Put',95,1),('Put',100,-1),('Call',100,-1),('Call',105,1)],2,'butterfly',200,300,[98,102]),
])
def test_normalized_economics(legs,credit,family,profit,loss,roots):
    candidate=trade(legs,credit,max_profit=99999,pop=.99,score=10,winner=True)
    before=deepcopy(candidate)
    r=research_structure(candidate,as_of='2030-01-17',expected_move=3)
    assert r['strategy_family']==family and r['underlying']=='QQQ'
    assert r['max_profit']==profit and r['max_loss']==r['capital_at_risk']==loss
    assert r['breakevens']==roots and r['dte']==1
    assert r['payoff']['grid']==trade_analysis(candidate)['grid']
    assert r['breakeven_moves'][0]['move_pct']==pytest.approx((roots[0]-100)/100)
    assert 'winner' not in r['trade'] and 'score' not in r['trade'] and 'pop' not in r['trade']
    assert candidate==before


def test_unknown_evidence_and_scaling():
    t=trade([('Call',100,2),('Call',105,-2)],-4)
    t['fees']=2
    r=research_structure(t)
    assert r['max_loss']==402 and r['max_profit']==598
    assert r['expected_move_context'] is None and r['dte'] is None
    assert r['evidence']['expected_move_status']=='unknown'
    assert r['evidence']['option_legs'][0]['delta'] is None


def chain():
    def leg(kind,strike,bid,delta):
        return dict(type=kind,strike=strike,bid=bid,ask=bid+.2,delta=delta,iv=.2,contract=f'{kind}{strike}')
    return dict(symbol='QQQ',expiration='2030-01-18',
        calls=[leg('Call',100,2.9,.5),leg('Call',105,.9,.2)],
        puts=[leg('Put',100,2.9,-.5),leg('Put',95,.9,-.2)])


def test_existing_debit_constructor_is_reused():
    c=chain();before=deepcopy(c)
    r=discover_debit_spreads(c,100,width=5,as_of='2030-01-17')
    assert [x['strategy_family'] for x in r['candidates']]==['call_debit_spread','put_debit_spread']
    for item in r['candidates']:
        assert item['entry_debit']==2 and item['max_profit']==300
        assert item['evidence']['option_legs'][0]['iv']==.2
        assert 'midpoint' in item['evidence']['pricing_assumption']
    assert c==before


@pytest.mark.parametrize('defect',['unknown_delta','crossed','duplicate','missing_price','wrong_expiry','malformed'])
def test_debit_insufficient_chain_returns_none(defect):
    c=chain();c['puts']=[]
    if defect=='unknown_delta':c['calls'][0]['delta']=None
    if defect=='crossed':c['calls'][0]['ask']=.1
    if defect=='duplicate':c['calls'].append(deepcopy(c['calls'][0]))
    if defect=='missing_price':c['calls'][0]['bid']=None
    if defect=='wrong_expiry':c['calls'][0]['expiration']='2030-01-19'
    if defect=='malformed':c['calls'][0]=None
    r=discover_debit_spreads(c,100,directions=('bullish',))
    assert not r['candidates'] and r['excluded_contract_count']>0


@pytest.mark.parametrize('change',[dict(credit=None),dict(credit=1),dict(legs=[]),dict(shares=100),
    dict(expiration='bad'),dict(spot=0),dict(legs=[dict(type='Call',strike=100,qty=1)]),
    dict(legs=[dict(type='Call',strike=100,qty=1),dict(type='Call',strike=100,qty=-1)])])
def test_malformed_candidates_fail_closed(change):
    t=trade([('Call',100,1),('Call',105,-1)],-2);t.update(change)
    with pytest.raises(ValueError):research_structure(t)


def test_generated_condor_and_bwb_preserve_shared_economics():
    c=demo_chain(30,spot=500,as_of=date(2030,1,1))
    candidates=generate(c,500,30/365,None,width=5,fee=0,min_net_credit=0,as_of=date(2030,1,1))
    selected=[t for t in candidates if t['strategy'] in ('Iron condor','Put broken-wing butterfly','Call broken-wing butterfly')]
    assert {t['strategy'] for t in selected}=={'Iron condor','Put broken-wing butterfly','Call broken-wing butterfly'}
    for t in selected:
        r=research_structure(t,symbol='QQQ')
        assert r['max_loss']==pytest.approx(t['max_loss'])
        assert r['max_profit']==pytest.approx(t['max_profit'])


def test_router_overlap_input_order_no_winner_and_unknown():
    debit=trade([('Call',100,1),('Call',105,-1)],-2)
    bwb=trade([('Put',90,1),('Put',100,-2),('Put',105,1)],1)
    state=opportunity_state(direction='bullish',premium_state='rich')
    r=research_routed_structures(state,[bwb,{},debit])
    assert [x['input_index'] for x in r['candidates']]==[0,2]
    assert r['excluded'][0]['reason']=='invalid_or_insufficient_candidate'
    assert 'winner' not in r and 'not a ranking' in r['candidate_order']
    assert research_routed_structures(opportunity_state(),[debit,bwb])['no_candidate']
    assert research_routed_structures(opportunity_state(movement_state='breakout'),[debit])['no_candidate']
    assert state['premium_state']=='rich'


def test_selector_condor_shape_and_multiple_roots():
    c=dict(symbol='QQQ',expiration='2030-01-18',side='Short / Credit',entry_price=2,
        legs=[dict(type=k,strike=s,action=a,quantity=1) for k,s,a in
            [('Put',90,'Buy'),('Put',95,'Sell'),('Call',105,'Sell'),('Call',115,'Buy')]])
    r=research_structure(c,spot=100)
    assert r['strategy_family']=='iron_condor' and r['required_move'] is None
    assert len(r['breakeven_moves'])==2 and r['max_loss']==800
