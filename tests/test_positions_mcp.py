from test_mcp_api import env,login,call,rpc
from test_positions import entry,position_db


def test_tracking_tools_end_to_end(env,position_db):
    c,provider,_,clock=env
    _,tokens=login(c);token=tokens['access_token']
    listed=rpc(c,token,'tools/list').json()['result']['tools']
    assert len(listed)==22
    for tool in listed:
        assert tool['annotations']['readOnlyHint']==(tool['name'] not in {'record_position','close_position'})
    response=call(c,token,'record_position',dict(entry=entry()))
    assert not response['isError'],response
    p=response['structuredContent'];pid=p['position_id']
    assert call(c,token,'get_active_positions',{})['structuredContent']['match_count']==1
    assert call(c,token,'get_position',dict(position_id=pid))['structuredContent']['entry_snapshot']==p['entry_snapshot']
    provider.history.reset_mock()
    r=call(c,token,'monitor_position',dict(position_id=pid))
    assert not r['isError'],r
    assert r['structuredContent']['current_snapshot']['estimated_pl'] is not None
    provider.history.assert_not_called()
    closed=call(c,token,'close_position',dict(position_id=pid,closure=dict(amount=.07,timestamp=clock().isoformat())))
    assert not closed['isError'] and closed['structuredContent']['status']=='closed'
    assert call(c,token,'get_active_positions',{})['structuredContent']['positions']==[]
