"""Regression coverage for retained explicit-trade REST/MCP contracts."""
import pytest
from test_api_hardening import manual
from test_mcp_api import env, login, call


INTERFACES = [
    ('/v1/trade/research','research_explicit_trade'),
    ('/v1/research/trade','unified_explicit_trade_research'),
]


@pytest.mark.parametrize('path,tool', INTERFACES)
@pytest.mark.parametrize('method', ['tolerance','nearest'])
def test_explicit_trade_rest_mcp_economics_and_presentation_remain_identical(env,path,tool,method):
    client,provider,_,_=env
    _,tokens=login(client)
    request=dict(manual(),method=method,commission_per_contract=1.25,entry_slippage=.10,terminal_friction=.20)
    params={'include_advanced':True} if 'unified' in tool else {}
    rest=client.post(path,params=params,json=request,headers={'Authorization':'Bearer owner-test-secret'})
    assert rest.status_code==200,rest.text
    result=call(client,tokens['access_token'],tool,dict(trade=request,**params))
    assert not result.get('isError'),result
    assert result['structuredContent']==rest.json()
    body=rest.json()
    if 'unified' in tool:
        assert body['schema_version']=='alphaos-unified-trade-v1'
        assert set(body)=={'schema_version','trade_snapshot','market_structure','historical_analog_behavior',
                           'historical_scenario_payoff','advanced_research','caveats'}
        trade=body['trade_snapshot']
        assert not trade['live_trade_state']['usable_for_execution_analysis']
        assert body['advanced_research']['included'] is True
        assert body['historical_scenario_payoff']['summary']['n']>0
    else:
        assert set(body)=={'meta','evidence','caveats'}
        assert body['meta']['schema_version']=='alphaos-research-v1'
        assert not body['meta']['quote_freshness']['usable_for_live_research']
        trade=body['evidence']
    assert trade['credit']==.35
    assert trade['max_profit']==pytest.approx(35)
    assert trade['max_loss']==pytest.approx(65)
    provider.quote.assert_not_called();provider.chain.assert_not_called();provider.expirations.assert_not_called()
    provider.history.assert_called_once()  # Shared completed-history cache, no live repricing.


@pytest.mark.parametrize('path,tool', INTERFACES)
@pytest.mark.parametrize('case,code,status', [
    ('orientation','invalid_vertical_orientation',422),
    ('credit','invalid_vertical_credit',422),
    ('expired','expired_option',422),
    ('horizon','unsupported_horizon',400),
    ('symbol','unsupported_symbol',400),
])
def test_semantic_rejections_match_and_stop_before_provider(env,path,tool,case,code,status):
    client,provider,_,_=env;_,tokens=login(client)
    request=manual()
    if case=='orientation':request['legs'][0]['strike']=97
    elif case=='credit':request['credit']=1
    elif case=='expired':request['expiration']='2026-09-23'
    elif case=='horizon':request['horizon']=4
    else:request['symbol']='IWM'
    rest=client.post(path,json=request,headers={'Authorization':'Bearer owner-test-secret'})
    result=call(client,tokens['access_token'],tool,dict(trade=request))
    assert rest.status_code==status
    assert rest.json()['error']['code']==code
    assert result['isError'] and result['structuredContent']==rest.json()
    provider.history.assert_not_called();provider.quote.assert_not_called();provider.chain.assert_not_called()


@pytest.mark.parametrize('path,tool', INTERFACES)
def test_history_failure_is_sanitized_without_live_fallback(env,path,tool):
    client,provider,_,_=env;_,tokens=login(client)
    provider.history.side_effect=RuntimeError('public-test-secret account-test-secret')
    rest=client.post(path,json=manual(),headers={'Authorization':'Bearer owner-test-secret'})
    result=call(client,tokens['access_token'],tool,dict(trade=manual()))
    assert rest.status_code==503
    assert rest.json()['error']['code']=='provider_unavailable'
    assert result['isError'] and result['structuredContent']==rest.json()
    assert 'public-test-secret' not in rest.text and 'account-test-secret' not in rest.text
    provider.quote.assert_not_called();provider.chain.assert_not_called()


@pytest.mark.parametrize('path,tool', INTERFACES)
def test_model_validation_stays_at_transport_boundary(env,path,tool):
    client,provider,_,_=env;_,tokens=login(client)
    request=dict(manual(),commission_per_contract=-1)
    rest=client.post(path,json=request,headers={'Authorization':'Bearer owner-test-secret'})
    result=call(client,tokens['access_token'],tool,dict(trade=request))
    assert rest.status_code==422 and rest.json()['error']['code']=='invalid_request'
    assert result['isError'] and result['structuredContent']['error']['code']=='invalid_tool_request'
    provider.history.assert_not_called();provider.quote.assert_not_called()
