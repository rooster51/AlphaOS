"""Full output parity and ownership for the candidate-copy experiment."""
from copy import deepcopy
import pytest
from modules.position_research import research_position,_research_position

CASES=[
 ([('Call',100,1),('Call',105,-1)],-2),
 ([('Put',100,1),('Put',95,-1)],-2),
 ([('Put',95,1),('Put',100,-1)],2),
 ([('Call',100,-1),('Call',105,1)],2),
 ([('Call',95,1),('Call',100,-2),('Call',105,1)],-2),
 ([('Put',90,1),('Put',100,-2),('Put',105,1)],1),
 ([('Call',95,1),('Call',100,-2),('Call',110,1)],1),
 ([('Put',90,1),('Put',95,-1),('Call',105,-1),('Call',115,1)],2),
 ([('Put',95,1),('Put',100,-1),('Call',100,-1),('Call',105,1)],2),
 ([('Call',100,1)],-2),
 ([('Put',100,1)],-2),
]
@pytest.mark.parametrize('legs,credit',CASES)
@pytest.mark.parametrize('expiration',['2030-01-18','2031-01-17'])
@pytest.mark.parametrize('detail',['none','landmarks','full'])
def test_owned_discovery_matches_defensive_research(legs,credit,expiration,detail):
 candidate=dict(symbol='SPY',spot=100,expiration=expiration,credit=credit,fees=0,shares=0,
  source='fixture',strategy='fixture',legs=[dict(type=t,strike=s,qty=q,expiration=expiration,
   archive_quality={'warnings':['observed']},bid=1,ask=2) for t,s,q in legs])
 before=deepcopy(candidate)
 args=dict(symbol='SPY',spot=100,as_of='2030-01-03',payoff_detail=detail)
 public=research_position(candidate,**args)
 owned=_research_position(candidate,owned=True,**args)
 assert public==owned
 assert candidate==before
 public['trade']['legs'][0]['archive_quality']['warnings'].append('mutated')
 assert candidate==before

@pytest.mark.parametrize('owned',[False,True])
def test_owned_does_not_skip_validation(owned):
 candidate=dict(symbol='SPY',spot=100,expiration='2030-01-18',credit=-2,fees=0,shares=0,
  legs=[dict(type='Call',strike=100,qty=1),dict(type='Call',strike=105,qty=-.5)])
 with pytest.raises(ValueError):
  _research_position(candidate,symbol='SPY',spot=100,as_of='2030-01-03',owned=owned)
