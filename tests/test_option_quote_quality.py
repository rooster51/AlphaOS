from datetime import datetime,timezone,timedelta
import pytest
from modules.option_quote_quality import option_quality
from alphaos_api.service import ResearchService
from test_api_hardening import env,vertical

NOW=datetime(2026,10,1,18,tzinfo=timezone.utc)
def leg(v):return dict(bid_timestamp=v,ask_timestamp=v)

@pytest.mark.parametrize('value',[NOW.isoformat(),'2026-10-01T14:00:00-04:00',NOW.timestamp(),NOW.timestamp()*1000])
def test_same_instant_units(value):
    q=option_quality([leg(value)],NOW)
    assert q['oldest_age_seconds']==0 and q['fresh_contract_count']==1
    assert ResearchService(clock=lambda:NOW).timing(None,[leg(value)])['oldest_quote_age_seconds']==0

def test_old_distant_member_is_not_selected_age():
    selected=[leg(NOW.isoformat()),leg((NOW-timedelta(seconds=3)).isoformat())]
    q=option_quality(selected+[leg('2015-01-01T05:00:00Z')],NOW,scope='entire_chain')
    assert q['newest_age_seconds']==0 and q['oldest_age_seconds']>3e8
    assert q['fresh_contract_count']==2 and q['fresh_contract_percentage']==pytest.approx(200/3)
    used=option_quality(selected,NOW)
    assert used['all_contracts_fresh'] and used['oldest_age_seconds']==3

def test_missing_future_and_empty():
    q=option_quality([leg(None),leg('invalid'),leg((NOW+timedelta(seconds=90)).isoformat())],NOW)
    assert q['missing_timestamp_contract_count']==2 and q['future_timestamp_contract_count']==1
    assert q['fresh_contract_count']==0 and not q['all_contracts_fresh']
    assert option_quality([],NOW)['oldest_age_seconds'] is None

def test_service_coverage_recomputed_on_cache_hit(env):
    c,p,s,clock=env
    p.chain.return_value['calls'][-1]['bid_timestamp']='2015-01-01T05:00:00Z'
    q=s.chain('SPY','2026-09-25')['quality']
    assert q['scope']=='entire_chain' and q['fresh_contract_count']==7
    clock.advance(10)
    assert s.chain('SPY','2026-09-25')['quality']['newest_age_seconds']==10
    result=vertical(c).json()['evidence']['quotes']
    assert result['consumed_contract_quality']['all_contracts_fresh']
    assert result['timing']['oldest_quote_age_seconds']==10
