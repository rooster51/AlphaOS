from datetime import datetime, timezone
import pytest
from test_mcp_api import env, login, call


@pytest.mark.parametrize('symbol',['QQQ','SPY'])
@pytest.mark.parametrize('state',['fresh','stale','closed'])
def test_quote_contract_rest_mcp_identical(env,symbol,state):
    c,p,_,clock=env
    p.quote.return_value=[dict(symbol=symbol,last=745.4,bid=745.2,ask=754.33,updated_at='2026-09-24T15:00:00Z')]
    if state=='stale':p.quote.return_value[0]['updated_at']='2026-09-24T12:00:00Z'
    if state=='closed':
        clock.value=datetime(2026,9,26,14,tzinfo=timezone.utc)
        p.quote.return_value[0]['updated_at']='2026-09-25T19:59:55Z'
    _,tokens=login(c)
    rest=c.get('/v1/quote/'+symbol,headers={'Authorization':'Bearer owner-test-secret'}).json()
    mcp=call(c,tokens['access_token'],'live_quote',{'symbol':symbol})['structuredContent']
    assert rest['evidence']['quote']==mcp['evidence']['quote']
    assert rest['evidence']['retrieved_at']==mcp['evidence']['retrieved_at']
    assert rest['evidence']['freshness']==mcp['evidence']['freshness']
    assert rest['meta']==mcp['meta']
    f=rest['evidence']['freshness']
    assert f['data_status']==('latest_available' if state=='closed' else state)
    assert f['usable_for_live_research']==(state=='fresh')
    assert not f['usable_for_execution_analysis']
    assert f['quote_quality']['bid_ask_reason']=='abnormally_wide_spread'
    assert rest['meta']['current_spot']==(745.4 if state=='fresh' else None)
    assert not rest['evidence']['cache']['hit'] and mcp['evidence']['cache']['hit']
    p.quote.assert_called_once_with(symbol)
