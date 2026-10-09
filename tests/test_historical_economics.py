from dataclasses import replace
import json

import numpy as np
import pytest

from modules.historical_economics import (HistoricalScenario, ScenarioEvidence,
    evaluate_historical_economics as evaluate)
from modules.premium_engine import payoff

AS_OF = '2026-10-09'


def trade(legs=None, credit=-2):
    return dict(symbol='QQQ', expiration='2026-10-16', spot=100, credit=credit,
        fees=1, shares=0, source='Explicit test fixture', legs=legs or [leg('Call',100,1)])


def leg(kind, strike, qty):
    return dict(type=kind, strike=strike, qty=qty)


def evidence(returns=(-.1,0,.1)):
    return ScenarioEvidence('QQQ','2026-10-16',100,'2026-10-09T14:00:00+00:00',
        '2026-10-09T14:01:00+00:00',600,5,5,'Test historical returns','explicit fixture',
        tuple(HistoricalScenario(str(i),r,'2026-10-08T20:00:00+00:00') for i,r in enumerate(returns)))


def run(t=None, e=None, **kwargs):
    return evaluate(t or trade(), as_of=AS_OF, evidence=e or evidence(), minimum_samples=2, **kwargs)


@pytest.mark.parametrize('legs,credit,expected',[
    ([leg('Call',100,1)],-2,[-201,-201,799]), ([leg('Put',100,1)],-2,[799,-201,-201]),
    ([leg('Call',100,1),leg('Call',105,-1)],-2,[-201,-201,299]),
    ([leg('Put',95,-1),leg('Put',100,1)],-2,[299,-201,-201]),
    ([leg('Put',95,1),leg('Put',100,-1)],2,[-301,199,199]),
    ([leg('Call',100,-1),leg('Call',105,1)],2,[199,199,-301]),
    ([leg('Call',95,1),leg('Call',100,-2),leg('Call',105,1)],-1,[-101,399,-101]),
    ([leg('Put',95,1),leg('Put',100,-2),leg('Put',105,1)],-1,[-101,399,-101]),
    ([leg('Call',95,1),leg('Call',100,-2),leg('Call',110,1)],1,[99,599,-401]),
    ([leg('Put',90,1),leg('Put',100,-2),leg('Put',105,1)],1,[-401,599,99]),
    ([leg('Put',90,1),leg('Put',95,-1),leg('Call',105,-1),leg('Call',110,1)],2,[-301,199,-301]),
])
def test_all_families_use_existing_payoff(legs,credit,expected):
    t=trade(legs,credit); r=run(t)
    assert [payoff(legs,credit,p,fees=1) for p in (90,100,110)]==pytest.approx(expected)
    assert [s['payoff_dollars'] for s in r['scenario_payoffs']] == pytest.approx(expected)
    assert r['historical_economics']['expected_value_dollars'] == pytest.approx(np.mean(expected))
    assert r['eligible_for_consideration'] is False
    json.dumps(r,allow_nan=False)


def test_metrics_costs_quantiles_and_negative_ev():
    r=run(slippage_dollars=2)
    m=r['historical_economics']
    assert m['expected_value_dollars']==pytest.approx(391/3)
    assert m['median_payoff']==-203
    assert m['p10_payoff']==-203
    assert m['p90_payoff']==pytest.approx(597)
    assert m['average_winning_payoff']==pytest.approx(797)
    assert m['average_losing_payoff']==-203
    assert m['positive_payoff_frequency']==1/3
    assert m['profit_factor']==pytest.approx(797/406)
    assert m['ev_over_max_risk']==pytest.approx((391/3)/203)
    assert run(e=evidence((-.1,0,.01)))['historical_economics']['expected_value_dollars']<0


@pytest.mark.parametrize('returns,pf,note',[
    ((.03,.04),None,'undefined_no_losses'),
    ((-.1,0),0,'defined'),
    ((.02,.02),None,'undefined_no_losses'),
])
def test_profit_factor_edge_cases(returns,pf,note):
    t=trade();t['fees']=0
    # Exact zero is tested separately; decimal .02 may round above strike.
    if returns==(.02,.02):
        t['credit']=-10; returns=(.1,.1)
    r=run(t,evidence(returns))
    assert r['historical_economics']['profit_factor']==pf
    assert r['metric_notes']['profit_factor']==note


def test_quantities_multiplier_and_total_fees():
    t=trade([leg('Call',100,2)],-4); t['fees']=3
    r=run(t,multiplier=10,slippage_dollars=2)
    assert [s['payoff_dollars'] for s in r['scenario_payoffs']]==pytest.approx([-45,-45,155])
    assert r['deterministic_expiration']['max_loss']==45
    assert r['deterministic_expiration']['breakevens']==pytest.approx([102.25])
    assert r['structure_identity']['fees']==3


@pytest.mark.parametrize('changes,reason',[
    ({'as_of':'2026-10-09T14:11:00+00:00'},'stale_or_future_evidence'),
    ({'observed_at':'2026-10-09T14:02:00+00:00'},'stale_or_future_evidence'),
    ({'horizon_sessions':3},'expiration_horizon_mismatch'),
    ({'expiration_sessions':0},'expiration_horizon_mismatch'),
    ({'symbol':'SPY'},'scenario_context_mismatch'),
    ({'scenarios':()},'insufficient_analog_history'),
    ({'scenarios':(HistoricalScenario('future',0,'2026-10-10T00:00:00+00:00'),)},'unmatured_historical_outcome'),
])
def test_evidence_gates(changes,reason):
    r=run(e=replace(evidence(),**changes))
    assert reason in r['missing_evidence']
    assert all(v is None for v in r['historical_economics'].values())
    assert r['scenario_payoffs']==[]


def test_missing_history_and_default_minimum():
    r=evaluate(trade(),as_of=AS_OF)
    assert 'historical_scenarios_unavailable' in r['missing_evidence']
    assert 'insufficient_analog_history' in evaluate(trade(),as_of=AS_OF,evidence=evidence())['missing_evidence']


@pytest.mark.parametrize('holding', ['intraday','swing','monthly','leaps'])
def test_early_exit_never_uses_expiration_ev(holding):
    r=run(holding_period=holding,valuation='early_exit')
    assert r['historical_economics']['expected_value_dollars'] is None
    assert r['early_exit']['status']=='unavailable'
    assert r['deterministic_expiration']['max_loss']==201


def test_intraday_and_capital_fail_closed():
    assert run(holding_period='intraday')['economics_coverage']=='deterministic_only'
    r=run(available_capital=170)
    assert r['eligibility']=='CAPITAL_INELIGIBLE'
    assert r['historical_economics']['expected_value_dollars'] is not None


def test_comparisons_share_canonical_sample_identity():
    e=evidence()
    other=replace(e,scenarios=tuple(reversed(e.scenarios)))
    a=run(e=e);b=run(trade([leg('Put',100,1)]),other)
    assert a['evidence']['fingerprint']==b['evidence']['fingerprint']
    assert [s['observation_id'] for s in a['scenario_payoffs']]==[s['observation_id'] for s in b['scenario_payoffs']]
    assert replace(e,horizon_sessions=3).fingerprint!=e.fingerprint


@pytest.mark.parametrize('change',[
    {'legs':[leg('Call',100,-1)]}, {'credit':2}, {'fees':True},
    {'legs':[leg('Call',100,.5)]}, {'multiplier':50},
    {'legs':[leg('Call',100,1),leg('Put',100,1)]},
])
def test_unsupported_or_ambiguous_trade(change):
    with pytest.raises(ValueError):run(dict(trade(),**change))


def test_invalid_samples():
    for scenarios in ((HistoricalScenario('x',float('nan'),'2026-10-08T00:00:00Z'),),
                      (HistoricalScenario('x',-1.1,'2026-10-08T00:00:00Z'),),
                      evidence().scenarios*2):
        with pytest.raises(ValueError):replace(evidence(),scenarios=scenarios)


def test_all_zero_payoff_and_missing_win_loss_averages():
    t=trade([leg('Call',90,1)],-10);t['fees']=0
    r=run(t,evidence((0,0)))
    m=r['historical_economics']
    assert m['positive_payoff_frequency']==0
    assert m['expected_value_dollars']==0
    assert m['average_winning_payoff'] is None
    assert m['average_losing_payoff'] is None
    assert m['profit_factor'] is None
