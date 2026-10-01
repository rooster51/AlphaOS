import pytest
from test_mcp_api import env,login,call,rpc
from test_index_support import index_fixture

@pytest.mark.parametrize('symbol',['SPX','XSP'])
def test_index_mcp_workflow_and_fourteen_tools(env,symbol):
    c,p,app,clock=env;index_fixture(p,symbol)
    _,tokens=login(c);token=tokens['access_token']
    assert len(rpc(c,token,'tools/list').json()['result']['tools'])==19
    out=call(c,token,'run_symbol_research',dict(symbol=symbol,dte_min=0,dte_max=0,maximum_candidates=2))
    assert not out['isError'],out
    assert out['structuredContent']['status']=='complete'
    t=out['structuredContent']['qualifying_candidates'][0]['trade_snapshot']
    assert t['symbol']==symbol
    q=call(c,token,'live_quote',dict(symbol=symbol))
    assert not q['isError']
    assert q['structuredContent']['meta']['quote_freshness']['usable_for_live_research']
