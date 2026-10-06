import pytest
from test_mcp_api import env,login,call,rpc
from test_phase9 import qqq
from alphaos_api.phase9_contracts import SymbolResearchResponse,UnifiedTradeResponse


def test_mcp_natural_orchestration_and_granular_compatibility(env):
    c,p,app,clock=env;qqq(p);_,tokens=login(c);token=tokens['access_token']
    tools=rpc(c,token,'tools/list').json()['result']['tools'];named={t['name']:t for t in tools}
    assert len(named)==17
    assert {'market_snapshot','price_structure','forward_distribution','live_quote','option_expirations','scan_credit_spreads',
        'research_candidate','research_vertical','research_explicit_trade','compare_trades'}<=set(named)
    new=named['run_symbol_research']
    assert new['annotations']['readOnlyHint']
    assert 'Run QQQ' in new['description'] and 'not ranked' in new['description']
    assert new['inputSchema']['properties']['maximum_candidates']['maximum']==10
    assert 'symbol' in new['inputSchema']['required']
    args=dict(symbol='QQQ',expiration='2026-09-25',maximum_candidates=2,minimum_credit=.01)
    result=call(c,token,'run_symbol_research',args)
    assert not result['isError'],result
    out=result['structuredContent'];SymbolResearchResponse.model_validate(out)
    assert out['status']=='complete'
    cid=out['candidate_scan']['candidates'][0]['candidate_id']
    selected=call(c,token,'unified_candidate_research',dict(candidate_id=cid))
    UnifiedTradeResponse.model_validate(selected['structuredContent'])
    rest=c.get('/v1/research/candidates/'+cid,headers={'Authorization':'Bearer owner-test-secret'}).json()
    assert rest==selected['structuredContent']
    assert not call(c,token,'research_candidate',dict(candidate_id=cid))['isError']
    p.quote.assert_called_once()


def test_mcp_stale_run_is_explicit_stop_not_scan(env):
    c,p,app,clock=env;qqq(p);p.quote.return_value[0]['updated_at']='2026-09-23T15:00:00Z'
    _,tokens=login(c)
    result=call(c,tokens['access_token'],'run_symbol_research',dict(symbol='QQQ'))['structuredContent']
    assert result['status']=='live_research_stopped' and result['candidate_scan'] is None
    p.chain.assert_not_called()
