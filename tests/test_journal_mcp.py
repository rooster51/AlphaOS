from test_mcp_api import env,login,call,rpc
from test_positions import entry,position_db


def test_journal_mcp_closed_workflow(env,position_db):
    c,provider,_,clock=env;_,tokens=login(c);token=tokens['access_token']
    tools=rpc(c,token,'tools/list').json()['result']['tools']
    assert len(tools)==22
    assert all(t['annotations']['readOnlyHint'] for t in tools if t['name'].startswith('get_trade_'))
    result=call(c,token,'record_position',dict(entry=entry()));pid=result['structuredContent']['position_id']
    assert not call(c,token,'monitor_position',dict(position_id=pid))['isError']
    assert not call(c,token,'close_position',dict(position_id=pid,closure=dict(amount=.07,timestamp=clock().isoformat(),exit_reason='profit_target')))['isError']
    provider.reset_mock()
    r=call(c,token,'get_trade_journal',dict(filters=dict(symbol='SPY'),limit=10))
    assert not r['isError'],r
    assert r['structuredContent']['n_closed']==1
    r=call(c,token,'get_trade_review',dict(position_id=pid))
    assert not r['isError'] and r['structuredContent']['event_count']==2
    r=call(c,token,'get_trade_performance',dict(group_by='strategy'))
    assert not r['isError'],r
    assert r['structuredContent']['summary']['n_realized']==1
    assert r['structuredContent']['groups'][0]['value']=='PCS'
    assert not provider.mock_calls
