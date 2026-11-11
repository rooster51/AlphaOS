from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from alphaos_api.app import app
from alphaos_api.live_options import (ResearchScenario, ResearchLimits, ChainResearchRequest,
    research_scenario, strategy_geometry)
from alphaos_api.service import ResearchService
from modules.premium_engine import payoff

NOW = datetime(2026, 11, 5, 15, tzinfo=timezone.utc)
EXP = '2026-11-06'


def build(specs, symbol='SPY'):
    rows = []
    for kind, strike, qty, price in specs:
        contract = f'{symbol}261106{kind}{round(strike*1000):08d}'
        rows.append(dict(contract=contract, type='Call' if kind=='C' else 'Put', strike=strike,
            bid=price if qty < 0 else price-.01, ask=price if qty > 0 else price+.01,
            bid_timestamp=NOW.isoformat(), ask_timestamp=NOW.isoformat(),
            volume=10, open_interest=20, bid_size=10, ask_size=10))
    chain = dict(symbol=symbol, expiration=EXP, calls=[row for row in rows if row['type']=='Call'],
        puts=[row for row in rows if row['type']=='Put'])
    return chain, [dict(contract=row['contract'], qty=spec[2]) for row, spec in zip(rows,specs)]


CASES = [
    ('long_call', [('C',100,1,3)], None, 300.65, [103.0065]),
    ('long_put', [('P',100,1,3)], 9699.35, 300.65, [96.9935]),
    ('call_debit_spread', [('C',100,1,3),('C',105,-1,1)], 298.7, 201.3, [102.013]),
    ('put_debit_spread', [('P',105,1,3),('P',100,-1,1)], 298.7, 201.3, [102.987]),
    ('put_credit_spread', [('P',95,1,1),('P',100,-1,3)], 198.7, 301.3, [98.013]),
    ('call_credit_spread', [('C',105,1,1),('C',100,-1,3)], 198.7, 301.3, [101.987]),
    ('iron_condor', [('P',90,1,.5),('P',95,-1,1.5),('C',105,-1,1.5),('C',110,1,.5)], 197.4, 302.6, [93.026,106.974]),
    ('iron_butterfly', [('P',95,1,.5),('P',100,-1,1.5),('C',100,-1,1.5),('C',105,1,.5)], 197.4, 302.6, [98.026,101.974]),
    ('long_call_butterfly', [('C',95,1,6),('C',100,-2,3),('C',105,1,1)], 397.4, 102.6, [96.026,103.974]),
    ('long_put_butterfly', [('P',95,1,1),('P',100,-2,3),('P',105,1,6)], 397.4, 102.6, [96.026,103.974]),
    ('long_straddle', [('C',100,1,3),('P',100,1,3)], None, 601.3, [93.987,106.013]),
    ('long_strangle', [('C',105,1,2),('P',95,1,2)], None, 401.3, [90.987,109.013]),
]


@pytest.mark.parametrize('symbol', ['SPY','QQQ'])
@pytest.mark.parametrize('family,specs,profit,risk,roots', CASES)
def test_family_exact_payoff_parity(symbol, family, specs, profit, risk, roots):
    chain, legs = build(specs,symbol)
    result = research_scenario(chain,ResearchScenario(strategy=family,legs=legs),100,NOW,NOW.isoformat(),ResearchLimits(),.65)
    assert result['status']=='available', result
    assert result['contract_multiplier']==100
    assert result['max_profit']==pytest.approx(profit) if profit is not None else result['profit_unbounded']
    assert result['max_loss']==pytest.approx(risk)
    assert result['breakevens']==pytest.approx(roots)
    signed = [dict(type='Call' if kind=='C' else 'Put',strike=strike,qty=qty) for kind,strike,qty,price in specs]
    credit = -sum(qty*price for kind,strike,qty,price in specs)
    fees = .65*sum(abs(qty) for kind,strike,qty,price in specs)
    for price in [0, *[spec[1] for spec in specs], *roots, 1e6]:
        expected = credit*100-fees+sum(qty*100*max(0,price-strike if kind=='C' else strike-price) for kind,strike,qty,_ in specs)
        assert payoff(signed,credit,price,fees=fees)==pytest.approx(expected)
    assert all(payoff(signed,credit,root,fees=fees)==pytest.approx(0,abs=1e-8) for root in roots)
    for point in result['payoff']:
        assert point['pnl']==pytest.approx(payoff(signed,credit,point['terminal_price'],fees=fees))
    assert result['greek_exposure']['delta'] is None


@pytest.mark.parametrize('change', [dict(bid_timestamp=None),dict(ask_timestamp=(NOW-timedelta(seconds=31)).isoformat()),dict(bid=5,ask=3),dict(contract='QQQ261106C00100000')])
def test_missing_stale_crossed_identity(change):
    chain, legs=build([('C',100,1,3)])
    chain['calls'][0].update(change)
    result=research_scenario(chain,ResearchScenario(strategy='long_call',legs=legs),100,NOW,NOW.isoformat(),ResearchLimits(),0)
    assert result['status']=='unavailable'


@pytest.mark.parametrize('family,specs', [
    ('iron_condor',[('P',90,1,.5),('P',105,-1,2),('C',100,-1,2),('C',110,1,.5)]),
    ('iron_butterfly',[('P',90,1,.5),('P',100,-1,2),('C',100,-1,2),('C',105,1,.5)]),
    ('long_call_butterfly',[('C',95,1,6),('C',100,-1,3),('C',105,1,1)]),
    ('long_call_butterfly',[('C',99.999,1,1.001),('C',100,-2,1),('C',100.002,1,1.001)]),
    ('long_strangle',[('P',105,1,3),('C',100,1,3)]),
])
def test_invalid_geometry(family,specs):
    chain,legs=build(specs)
    result=research_scenario(chain,ResearchScenario(strategy=family,legs=legs),100,NOW,NOW.isoformat(),ResearchLimits(),0)
    assert result['reason']=='unsupported_strategy_geometry'


@pytest.mark.parametrize('limits,breach', [
    (dict(max_loss=300),'maximum_loss_exceeded'),(dict(max_debit=300),'maximum_debit_exceeded'),
    (dict(max_contracts=1),'maximum_contracts_exceeded'),(dict(max_bid_ask_spread=.001),'maximum_bid_ask_spread_exceeded'),
    (dict(dte_min=2),'dte_outside_range'),
])
def test_hypothetical_constraints_include_fees(limits,breach):
    chain,legs=build([('C',100,2,3)])
    result=research_scenario(chain,ResearchScenario(strategy='long_call',legs=legs),100,NOW,NOW.isoformat(),ResearchLimits(**limits),.65)
    assert breach in result['limit_breaches']
    assert not result['eligible_for_analysis']
    assert result['entry_fees']==1.3
    assert result['max_loss']==pytest.approx(601.3)


def test_custom_unbounded_and_zero_risk_returns():
    chain,legs=build([('C',100,-1,3)])
    result=research_scenario(chain,ResearchScenario(strategy='custom',legs=legs),100,NOW,NOW.isoformat(),ResearchLimits(),0)
    assert result['loss_unbounded'] and result['max_loss'] is None
    assert result['return_on_max_risk'] is None
    result=research_scenario(chain,ResearchScenario(strategy='custom',legs=legs),100,NOW,NOW.isoformat(),ResearchLimits(max_loss=1000),0)
    assert result['status']=='unavailable'


def test_duplicate_expiration_and_multiplier():
    chain,legs=build([('C',100,1,3)])
    request=ResearchScenario(strategy='custom',legs=legs+legs)
    assert research_scenario(chain,request,100,NOW,NOW.isoformat(),ResearchLimits(),0)['reason']=='duplicate_contracts'
    expired=NOW+timedelta(days=2)
    assert research_scenario(chain,ResearchScenario(strategy='long_call',legs=legs),100,expired,NOW.isoformat(),ResearchLimits(),0)['reason']=='expired_contract'
    with pytest.raises(ValidationError):
        ChainResearchRequest(scenarios=[dict(strategy='long_call',legs=legs)],contract_multiplier=10)
    for qty in [0,True,1.5,21]:
        with pytest.raises(ValidationError):
            ResearchScenario(strategy='long_call',legs=[dict(contract=legs[0]['contract'],qty=qty)])


def test_batch_authorization_shared_observations_and_underlying(monkeypatch):
    monkeypatch.setenv('ALPHAOS_API_TOKEN','fixture-token')
    chain,legs=build([('C',100,1,3)])
    provider=Mock()
    provider.chain.return_value=chain
    provider.quote.return_value=[dict(symbol='SPY',last=100,bid=99.99,ask=100.01,provider_outcome='SUCCESS',
        **{key:NOW.isoformat() for key in ('updated_at','bid_timestamp','ask_timestamp','provider_retrieved_at')})]
    service=ResearchService(provider,lambda:NOW)
    monkeypatch.setitem(app.state._state,'service',service)
    client=TestClient(app)
    path=f'/v1/options/SPY/chain/{EXP}'
    payload=dict(scenarios=[dict(strategy='long_call',legs=legs),dict(strategy='long_call',legs=legs)],limits={},entry_fee_per_contract=.65)
    assert client.post(path,json=payload).status_code==401
    provider.chain.assert_not_called()
    auth={'Authorization':'Bearer fixture-token'}
    response=client.post(path,json=payload,headers=auth)
    assert response.status_code==200,response.text
    assert len(response.json()['evidence']['scenarios'])==2
    assert all(item['status']=='available' for item in response.json()['evidence']['scenarios'])
    assert provider.chain.call_count==provider.quote.call_count==1
    provider.expirations.assert_not_called()
    provider.quote.return_value[0]['bid_timestamp']=(NOW-timedelta(seconds=15)).isoformat()
    result=client.post(path,json=payload,headers=auth).json()['evidence']
    assert all(item['reason']=='underlying_quote_ineligible' for item in result['scenarios'])
    assert not any('order' in path for path in client.get('/openapi.json').json()['paths'])

def test_narrow_wings_scaling_fees_and_credit_floor():
    specs=[('C',99.999,1,1.0002),('C',100,-2,1),('C',100.001,1,1.0002)]
    chain,legs=build(specs)
    result=research_scenario(chain,ResearchScenario(strategy='long_call_butterfly',legs=legs),100,NOW,NOW.isoformat(),ResearchLimits(),0)
    assert result['max_loss']==pytest.approx(.04,abs=1e-8)
    assert result['max_profit']==pytest.approx(.06,abs=1e-8)
    assert result['breakevens']==pytest.approx([99.9994,100.0006])
    chain,legs=build([('P',95,1,1),('P',100,-1,3)])
    result=research_scenario(chain,ResearchScenario(strategy='put_credit_spread',legs=legs),100,NOW,NOW.isoformat(),ResearchLimits(min_credit=200),.65)
    assert result['limit_breaches']==['minimum_credit_not_met']
    chain,legs=build([('C',100,1,1)])
    chain['calls'][0].update(delta=.5,gamma=.01,theta=-.1,vega=.2,rho=.03)
    result=research_scenario(chain,ResearchScenario(strategy='long_call',legs=legs),100,NOW,NOW.isoformat(),ResearchLimits(),0)
    assert result['greek_exposure']['delta']==50

def test_zero_risk_custom_does_not_invent_return_and_wrong_date_rejected():
    chain,legs=build([('C',100,1,1),('C',105,-1,2)])
    result=research_scenario(chain,ResearchScenario(strategy='custom',legs=legs),100,NOW,NOW.isoformat(),ResearchLimits(),0)
    assert result['max_loss']==0
    assert result['return_on_max_risk'] is None
    wrong=[dict(contract=legs[0]['contract'].replace('261106','261113'),qty=1)]
    assert research_scenario(chain,ResearchScenario(strategy='long_call',legs=wrong),100,NOW,NOW.isoformat(),ResearchLimits(),0)['status']=='unavailable'
    with pytest.raises(ValidationError):
        ChainResearchRequest(scenarios=[dict(strategy='long_call',legs=wrong,expiration='2026-11-13')])
