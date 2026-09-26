import base64
from copy import deepcopy
import hashlib
import importlib
import json
import re
from urllib.parse import urlsplit, parse_qs
from unittest.mock import Mock, AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from alphaos_api.mcp_server import build_mcp
from alphaos_api.service import ResearchService
from test_api_hardening import dataset, chain, Clock, manual

api = importlib.import_module('alphaos_api.app')
BASE = 'https://alphaos.onrender.com'
CALLBACK = 'https://chatgpt.com/connector_platform_oauth_redirect'


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv('ALPHAOS_API_TOKEN','owner-test-secret')
    monkeypatch.setenv('PUBLIC_API_SECRET','public-test-secret')
    monkeypatch.setenv('PUBLIC_ACCOUNT_NUMBER','account-test-secret')
    monkeypatch.setenv('ALPHAOS_PUBLIC_URL',BASE)
    provider=Mock()
    provider.quote.return_value=[dict(symbol='SPY',last=100.,updated_at='2026-09-24T15:00:00Z')]
    provider.expirations.return_value=['2026-09-25']
    provider.chain.return_value=chain()
    provider.history.return_value=dataset()
    clock=Clock()
    monkeypatch.setattr(api.app.state,'service',ResearchService(provider,clock))
    app=FastAPI()
    app.include_router(api.router)
    app.add_api_route('/health',api.health)
    app.exception_handlers.update(api.app.exception_handlers)
    app.middleware('http')(api.safe_boundary)
    build_mcp(app,api.sanitized)
    with TestClient(app,base_url=BASE,follow_redirects=False) as client:
        yield client,provider,app,clock


def registration(client,**changes):
    payload=dict(redirect_uris=[CALLBACK],token_endpoint_auth_method='none',
        grant_types=['authorization_code','refresh_token'],response_types=['code'],scope='research:read')
    payload.update(changes)
    return client.post('/register',json=payload)


def authorize(client,client_id,**changes):
    verifier='v'*64
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    params=dict(client_id=client_id,redirect_uri=CALLBACK,response_type='code',
        code_challenge=challenge,code_challenge_method='S256',scope='research:read',state='test-state',resource=BASE+'/mcp')
    params.update(changes)
    response=client.get('/authorize',params=params)
    return response,verifier


def consent(client,location,origin=BASE,**changes):
    page=client.get(location)
    assert page.status_code==200,page.text
    csrf=re.search(r'name="csrf" value="([^"]+)"',page.text).group(1)
    ticket=parse_qs(urlsplit(location).query)['ticket'][0]
    form=dict(ticket=ticket,csrf=csrf,owner_token='owner-test-secret',decision='allow')
    form.update(changes)
    return client.post('/oauth/consent',data=form,headers={} if origin is None else {'Origin':origin}),form


@pytest.mark.parametrize('origin',[BASE,None,'null'])
def test_consent_browser_origins_preserve_authorization_and_pkce(env,origin):
    c,_,_,_=env
    cid=registration(c).json()['client_id']
    auth,verifier=authorize(c,cid)
    rejected,_=consent(c,auth.headers['location'],origin=origin,owner_token='wrong')
    assert rejected.status_code==403
    approved,form=consent(c,auth.headers['location'],origin=origin)
    assert approved.status_code==303
    code=parse_qs(urlsplit(approved.headers['location']).query)['code'][0]
    headers={} if origin is None else {'Origin':origin}
    assert c.post('/oauth/consent',data=form,headers=headers).status_code==400
    assert token_request(c,cid,code,'wrong-verifier').status_code==400
    assert token_request(c,cid,code,verifier).status_code==200
    assert token_request(c,cid,code,verifier).status_code==400


@pytest.mark.parametrize('origin',[BASE,None,'null'])
@pytest.mark.parametrize('failure',['foreign_origin','invalid_csrf','missing_cookie','expired_ticket'])
def test_consent_origin_compatibility_retains_csrf_protections(env,origin,failure):
    from alphaos_api.mcp_auth import fingerprint
    c,_,app,_=env
    cid=registration(c).json()['client_id'];auth,_=authorize(c,cid)
    page=c.get(auth.headers['location'])
    assert page.status_code==200
    cookie_header=page.headers['set-cookie'].lower()
    assert '__host-alphaos-consent=' in cookie_header
    assert all(flag in cookie_header for flag in ('secure','httponly','samesite=lax','max-age=300'))
    ticket=parse_qs(urlsplit(auth.headers['location']).query)['ticket'][0]
    csrf=re.search(r'name="csrf" value="([^"]+)"',page.text).group(1)
    form=dict(ticket=ticket,csrf=csrf,owner_token='owner-test-secret',decision='allow')
    if failure=='foreign_origin':origin='https://evil.example'
    elif failure=='invalid_csrf':form['csrf']='wrong'
    elif failure=='missing_cookie':c.cookies.clear()
    else:
        key=fingerprint(ticket)
        _,pending=app.state.oauth.pending.entries[key]
        app.state.oauth.pending.entries[key]=(0,pending)
    response=c.post('/oauth/consent',data=form,headers={} if origin is None else {'Origin':origin})
    assert response.status_code==400
    assert response.json()=={'error':'invalid_request'}


@pytest.mark.parametrize('callback',[CALLBACK,'https://chatgpt.com/connector/oauth/test-client'])
def test_consent_csp_allows_only_validated_callback(env,callback):
    from alphaos_api.mcp_auth import SECURITY_HEADERS
    c,_,_,_=env
    original=dict(SECURITY_HEADERS)
    assert registration(c,redirect_uris=['https://evil.example/callback']).status_code==400
    cid=registration(c,redirect_uris=[callback]).json()['client_id']
    rejected,_=authorize(c,cid,redirect_uri='https://evil.example/callback')
    assert rejected.status_code==400
    auth,_=authorize(c,cid,redirect_uri=callback)
    page=c.get(auth.headers['location'])
    assert page.status_code==200
    csp=page.headers['content-security-policy']
    directives=dict((p.strip().split()[0],p.strip().split()[1:]) for p in csp.split(';') if p.strip())
    assert directives['form-action']==["'self'",callback]
    assert '*' not in csp
    assert 'https://evil.example/callback' not in directives['form-action']
    assert 'https://chatgpt.com/arbitrary' not in directives['form-action']
    assert csp.replace("form-action 'self' "+callback,"form-action 'self'")==original['Content-Security-Policy']
    for name,value in original.items():
        if name!='Content-Security-Policy':assert page.headers[name]==value
    assert SECURITY_HEADERS==original


def token_request(client,client_id,code,verifier,**changes):
    form=dict(grant_type='authorization_code',client_id=client_id,code=code,
        code_verifier=verifier,redirect_uri=CALLBACK,resource=BASE+'/mcp')
    form.update(changes)
    return client.post('/token',data=form)


def login(client):
    reg=registration(client)
    assert reg.status_code==201,reg.text
    cid=reg.json()['client_id']
    auth,verifier=authorize(client,cid)
    assert auth.status_code==302,auth.text
    approved,_=consent(client,auth.headers['location'])
    assert approved.status_code==303,approved.text
    query=parse_qs(urlsplit(approved.headers['location']).query)
    assert query['state']==['test-state'] and query['iss']==[BASE]
    response=token_request(client,cid,query['code'][0],verifier)
    assert response.status_code==200,response.text
    return cid,response.json()


def rpc(client,token,method,params=None,version='2025-11-25'):
    headers={'Accept':'application/json, text/event-stream','MCP-Protocol-Version':version}
    params=dict(params or {})
    if version=='2026-07-28':
        params['_meta']={'io.modelcontextprotocol/protocolVersion':version,'io.modelcontextprotocol/clientCapabilities':{}}
        headers['Mcp-Method']=method
        if 'name' in params:headers['Mcp-Name']=params['name']
    if token:headers['Authorization']='Bearer '+token
    return client.post('/mcp',headers=headers,json=dict(jsonrpc='2.0',id=1,method=method,params=params or {}))


def call(client,token,name,args):
    response=rpc(client,token,'tools/call',dict(name=name,arguments=args))
    assert response.status_code==200,response.text
    return response.json()['result']


def test_discovery_auth_handshake_and_list(env):
    c,p,app,_=env
    assert c.get('/health').status_code==200
    assert c.get('/v1/quote/SPY').status_code==401
    unauth=rpc(c,None,'tools/list')
    assert unauth.status_code==401
    assert '/.well-known/oauth-protected-resource/mcp' in unauth.headers['www-authenticate']
    assert c.get('/.well-known/oauth-protected-resource/mcp').json()['resource']==BASE+'/mcp'
    meta=c.get('/.well-known/oauth-authorization-server').json()
    assert meta['authorization_response_iss_parameter_supported'] and meta['code_challenge_methods_supported']==['S256']
    assert meta['issuer']==BASE
    assert c.get('/.well-known/oauth-protected-resource/mcp').json()['authorization_servers']==[meta['issuer']]
    assert meta['client_id_metadata_document_supported'] is True
    assert rpc(c,'owner-test-secret','tools/list').status_code==401
    _,tokens=login(c);token=tokens['access_token']
    handshake=rpc(c,token,'initialize',dict(protocolVersion='2025-11-25',capabilities={},clientInfo={'name':'test','version':'1'}))
    assert handshake.status_code==200,handshake.text
    assert handshake.json()['result']['serverInfo']['name']=='AlphaOS'
    listed=rpc(c,token,'tools/list').json()['result']['tools']
    assert {t['name'] for t in listed}=={'market_snapshot','price_structure','forward_distribution','live_quote','option_expirations',
        'scan_credit_spreads','research_candidate','research_vertical','research_explicit_trade','compare_trades'}
    assert all(t['annotations']['readOnlyHint'] and not t['annotations']['destructiveHint'] for t in listed)
    assert all(t['_meta']['securitySchemes'][0]['scopes']==['research:read'] for t in listed)
    modern=rpc(c,token,'tools/list',version='2026-07-28')
    assert modern.status_code==200,modern.text
    p.quote.assert_not_called()


def test_quote_context_and_rest_parity(env):
    c,p,_,_=env;_,t=login(c);token=t['access_token']
    quote=call(c,token,'live_quote',{'symbol':'SPY'})
    assert not quote.get('isError')
    assert quote['structuredContent']['meta']['current_spot']==100
    market=call(c,token,'market_snapshot',{'symbol':'SPY','horizon':3})['structuredContent']
    for name in ('price_structure','forward_distribution'):
        result=call(c,token,name,dict(symbol='SPY',horizon=3,snapshot_id=market['meta']['snapshot_id']))
        assert result['structuredContent']['meta']==market['meta']
    p.quote.assert_called_once();p.history.assert_called_once()
    assert c.get('/v1/quote/SPY',headers={'Authorization':'Bearer owner-test-secret'}).json()['meta']['current_spot']==100


@pytest.mark.parametrize('name,args',[
    ('live_quote',{'symbol':'AAPL'}),('live_quote',{'symbol':'public-test-secret'}),
    ('market_snapshot',{'symbol':'SPY','horizon':4}),('live_quote',{}),
    ('research_explicit_trade',{'trade':{'symbol':'SPY','credit':'owner-test-secret'}}),
    ('place_order',{}),('scan_credit_spreads',{'symbol':'SPY','maximum_candidates':101})])
def test_invalid_tool_inputs_safe(env,name,args):
    c,p,_,_=env;_,t=login(c)
    result=call(c,t['access_token'],name,args)
    assert result['isError']
    assert 'owner-test-secret' not in json.dumps(result) and 'public-test-secret' not in json.dumps(result)
    p.quote.assert_not_called()


def test_provider_error_is_safe(env,caplog):
    c,p,_,_=env;_,t=login(c)
    p.quote.side_effect=RuntimeError('public-test-secret account-test-secret')
    result=call(c,t['access_token'],'live_quote',{'symbol':'SPY'})
    assert result['isError'] and result['structuredContent']['error']['code']=='provider_unavailable'
    assert 'public-test-secret' not in json.dumps(result)+caplog.text


def test_scan_candidate_vertical_and_compare(env):
    c,p,app,clock=env;_,t=login(c);token=t['access_token']
    scan=call(c,token,'scan_credit_spreads',dict(symbol='SPY',expiration='2026-09-25',maximum_candidates=2))
    assert not scan.get('isError'),scan
    candidates=scan['structuredContent']['evidence']['candidates']
    assert len(candidates)==2
    result=call(c,token,'research_candidate',{'candidate_id':candidates[0]['candidate_id']})
    assert not result.get('isError'),result
    exact=call(c,token,'research_vertical',dict(symbol='SPY',expiration='2026-09-25',option_type='put',short_strike=99,long_strike=98))
    assert exact['structuredContent']['evidence']['credit']==pytest.approx(.35)
    p.quote.assert_called_once();p.chain.assert_called_once();p.history.assert_called_once()
    a=manual();b=deepcopy(a);b['legs'][0]['strike']=98;b['legs'][1]['strike']=97
    manual_result=call(c,token,'research_explicit_trade',dict(trade=a))
    assert not manual_result.get('isError'),manual_result
    compared=call(c,token,'compare_trades',dict(comparison=dict(research_trade=a,candidates=[b,a])))
    assert [e['short_strike'] for e in compared['structuredContent']['evidence']['candidates']]==[98,99]
    clock.advance(121)
    assert call(c,token,'research_candidate',{'candidate_id':candidates[0]['candidate_id']})['structuredContent']['error']['code']=='stale_snapshot'


def test_oauth_pkce_resource_redirect_and_code_replay(env):
    c,_,_,_=env
    assert registration(c,redirect_uris=['https://evil.example/callback']).status_code==400
    cid=registration(c).json()['client_id']
    wrong,_=authorize(c,cid,resource='https://evil.example/mcp')
    assert 'error=invalid_target' in wrong.headers['location']
    assert 'iss=' in wrong.headers['location']
    auth,verifier=authorize(c,cid)
    rejected,_=consent(c,auth.headers['location'],owner_token='wrong')
    assert rejected.status_code==403
    approved,form=consent(c,auth.headers['location'])
    code=parse_qs(urlsplit(approved.headers['location']).query)['code'][0]
    assert token_request(c,cid,code,'wrong-verifier').status_code==400
    assert token_request(c,cid,code,verifier,resource='https://evil.example').status_code==400
    assert token_request(c,cid,code,verifier,redirect_uri='https://evil.example').status_code==400
    assert token_request(c,cid,code,verifier).status_code==200
    assert token_request(c,cid,code,verifier).status_code==400
    assert c.post('/oauth/consent',data=form,headers={'Origin':BASE}).status_code==400


def test_oauth_csrf_denial_refresh_rotation_and_revocation(env,monkeypatch):
    c,_,app,_=env
    cid=registration(c).json()['client_id'];auth,_=authorize(c,cid)
    rejected,_=consent(c,auth.headers['location'],csrf='wrong')
    assert rejected.status_code==400
    denied,_=consent(c,auth.headers['location'],decision='deny')
    assert 'error=access_denied' in denied.headers['location']
    cid,t=login(c)
    form=dict(grant_type='refresh_token',client_id=cid,refresh_token=t['refresh_token'],resource=BASE+'/mcp')
    refreshed=c.post('/token',data=form)
    assert refreshed.status_code==200,refreshed.text
    assert refreshed.json()['refresh_token']!=t['refresh_token']
    assert c.post('/token',data=form).status_code==400
    assert rpc(c,refreshed.json()['access_token'],'tools/list').status_code==401
    # Explicit revocation of a fresh grant must revoke access and refresh together.
    cid,t=login(c)
    refreshed=c.post('/token',data=dict(grant_type='refresh_token',client_id=cid,
        refresh_token=t['refresh_token'],resource=BASE+'/mcp'))
    assert c.post('/revoke',data=dict(client_id=cid,token=refreshed.json()['refresh_token'])).status_code==200
    assert rpc(c,refreshed.json()['access_token'],'tools/list').status_code==401
    assert rpc(c,t['access_token'],'tools/list').status_code==401
    _,t=login(c);monkeypatch.setenv('ALPHAOS_API_TOKEN','rotated-test-only')
    assert rpc(c,t['access_token'],'tools/list').status_code==401


def test_host_origin_and_body_limits(env):
    c,_,_,_=env;_,t=login(c)
    headers={'Authorization':'Bearer '+t['access_token'],'Accept':'application/json, text/event-stream'}
    assert c.post('/mcp',headers={**headers,'Host':'evil.example'},json={}).status_code==421
    assert c.post('/mcp',headers={**headers,'Origin':'https://evil.example'},json={}).status_code==403
    assert c.post('/mcp',headers=headers,content='x'*131073).status_code==413


def test_oauth_expiry_scope_cross_client_and_rate_limit(env):
    c,_,app,_=env;cid,t=login(c)
    other=registration(c).json()['client_id']
    form=dict(grant_type='refresh_token',client_id=other,refresh_token=t['refresh_token'],resource=BASE+'/mcp')
    assert c.post('/token',data=form).status_code==400
    form['client_id']=cid;form['scope']='orders:write'
    assert c.post('/token',data=form).status_code==400
    from alphaos_api.mcp_auth import fingerprint
    key=fingerprint(t['access_token'])
    _,value=app.state.oauth.access.entries[key]
    app.state.oauth.access.entries[key]=(0,value)
    assert rpc(c,t['access_token'],'tools/list').status_code==401
    for _ in range(30):registration(c)
    assert registration(c).status_code==429


@pytest.mark.parametrize('invalidator',['expiry','rotation'])
def test_code_expiry_and_rotation_invalidate_pending_grant(env,monkeypatch,invalidator):
    c,_,app,_=env;cid=registration(c).json()['client_id']
    auth,verifier=authorize(c,cid)
    approved,_=consent(c,auth.headers['location'])
    code=parse_qs(urlsplit(approved.headers['location']).query)['code'][0]
    if invalidator=='rotation':
        monkeypatch.setenv('ALPHAOS_API_TOKEN','rotated-owner')
    else:
        from alphaos_api.mcp_auth import fingerprint
        key=fingerprint(code)
        _,value=app.state.oauth.codes.entries[key]
        app.state.oauth.codes.entries[key]=(0,value)
    assert token_request(c,cid,code,verifier).status_code==400


def test_confidential_client_and_malformed_protocol(env):
    c,_,_,_=env
    reg=registration(c,token_endpoint_auth_method='client_secret_post').json()
    auth,verifier=authorize(c,reg['client_id'])
    approved,_=consent(c,auth.headers['location'])
    code=parse_qs(urlsplit(approved.headers['location']).query)['code'][0]
    assert token_request(c,reg['client_id'],code,verifier,client_secret='wrong').status_code==401
    tokens=token_request(c,reg['client_id'],code,verifier,client_secret=reg['client_secret'])
    assert tokens.status_code==200,tokens.text
    token=tokens.json()['access_token']
    headers={'Authorization':'Bearer '+token,'Accept':'application/json, text/event-stream',
        'Content-Type':'application/json','MCP-Protocol-Version':'2025-11-25'}
    for body in ('not json','{"jsonrpc":"2.0","id":1,"method":"tools/call","params":[]}'):
        response=c.post('/mcp',headers=headers,content=body)
        assert response.status_code==400,response.text
        assert 'owner-test-secret' not in response.text


def test_latest_protocol_tool_call(env):
    c,_,_,_=env;_,tokens=login(c)
    response=rpc(c,tokens['access_token'],'tools/call',dict(name='live_quote',arguments={'symbol':'SPY'}),version='2026-07-28')
    assert response.status_code==200,response.text
    assert response.json()['result']['structuredContent']['meta']['symbol']=='SPY'


def test_basic_header_only_and_mismatched_client(env):
    c,_,_,_=env
    reg=registration(c,token_endpoint_auth_method='client_secret_basic').json()
    cid=reg['client_id'];credentials=(cid,reg['client_secret'])
    auth,verifier=authorize(c,cid)
    approved,_=consent(c,auth.headers['location'])
    code=parse_qs(urlsplit(approved.headers['location']).query)['code'][0]
    form=dict(grant_type='authorization_code',code=code,code_verifier=verifier,
        redirect_uri=CALLBACK,resource=BASE+'/mcp')
    assert c.post('/token',data={**form,'client_id':'different'},auth=credentials).status_code==401
    assert c.post('/token',data=form,auth=(cid,'wrong')).status_code==401
    tokens=c.post('/token',data=form,auth=credentials)
    assert tokens.status_code==200,tokens.text
    token=tokens.json()['access_token']
    assert rpc(c,token,'tools/list').status_code==200
    refreshed=c.post('/token',data=dict(grant_type='refresh_token',
        refresh_token=tokens.json()['refresh_token'],resource=BASE+'/mcp'),auth=credentials)
    assert refreshed.status_code==200
    assert c.post('/revoke',data={'token':refreshed.json()['refresh_token']},auth=credentials).status_code==200
    assert rpc(c,token,'tools/list').status_code==401


def client_document():
    from alphaos_api.mcp_auth import CHATGPT_CLIENT
    return dict(client_id=CHATGPT_CLIENT,redirect_uris=[CALLBACK],
        token_endpoint_auth_methods_supported=['none','private_key_jwt'],
        token_endpoint_auth_method='private_key_jwt',
        grant_types=['authorization_code','refresh_token'],response_types=['code'])


def test_cimd_identity_survives_restart_but_grants_do_not(env,monkeypatch):
    from alphaos_api.mcp_auth import OwnerOAuth,CHATGPT_CLIENT
    c,_,app,_=env
    fetch=AsyncMock(return_value=(client_document(),60))
    monkeypatch.setattr(OwnerOAuth,'fetch_client_metadata',fetch)
    def cimd_login(client):
        auth,verifier=authorize(client,CHATGPT_CLIENT)
        assert auth.status_code==302
        approved,_=consent(client,auth.headers['location'])
        q=parse_qs(urlsplit(approved.headers['location']).query)
        assert q['iss']==[client.get('/.well-known/oauth-authorization-server').json()['issuer']]
        tokens=token_request(client,CHATGPT_CLIENT,q['code'][0],verifier)
        assert tokens.status_code==200,tokens.text
        return tokens.json()
    before=cimd_login(c)
    assert not app.state.oauth.clients.entries  # No dynamic registration.
    assert rpc(c,before['access_token'],'tools/list').status_code==200
    restarted=FastAPI();restarted.include_router(api.router)
    build_mcp(restarted,api.sanitized)
    with TestClient(restarted,base_url=BASE,follow_redirects=False) as after:
        assert rpc(after,before['access_token'],'tools/list').status_code==401
        assert after.post('/token',data=dict(grant_type='refresh_token',client_id=CHATGPT_CLIENT,
            refresh_token=before['refresh_token'],resource=BASE+'/mcp')).json()['error']=='invalid_grant'
        fresh=cimd_login(after)  # Same client URL, no recreate/register step.
        assert not call(after,fresh['access_token'],'live_quote',{'symbol':'SPY'})['isError']
    assert fetch.await_count==2


@pytest.mark.parametrize('changes',[
    {'client_id':'https://evil.example/client.json'},
    {'redirect_uris':['https://evil.example/callback']},
    {'token_endpoint_auth_methods_supported':['private_key_jwt']},
    {'grant_types':['client_credentials']},
    {'response_types':['token']}])
def test_cimd_rejects_invalid_metadata(env,monkeypatch,changes):
    from alphaos_api.mcp_auth import OwnerOAuth,CHATGPT_CLIENT
    c,_,_,_=env
    document=client_document();document.update(changes)
    monkeypatch.setattr(OwnerOAuth,'fetch_client_metadata',AsyncMock(return_value=(document,60)))
    auth,_=authorize(c,CHATGPT_CLIENT)
    assert auth.status_code==400


def test_cimd_never_fetches_arbitrary_urls(env,monkeypatch,caplog):
    from alphaos_api.mcp_auth import OwnerOAuth,CHATGPT_CLIENT
    c,_,_,_=env
    fetch=AsyncMock(side_effect=RuntimeError('public-test-secret'))
    monkeypatch.setattr(OwnerOAuth,'fetch_client_metadata',fetch)
    for url in ('http://127.0.0.1/client.json','https://chatgpt.com.evil.example/oauth/client.json',
                'https://chatgpt.com/oauth/client.json?secret=owner-test-secret'):
        assert authorize(c,url)[0].status_code==400
    fetch.assert_not_called()
    assert authorize(c,CHATGPT_CLIENT)[0].status_code==400
    assert 'public-test-secret' not in caplog.text and 'owner-test-secret' not in caplog.text


def test_oauth_diagnostics_never_log_credentials(env,caplog,monkeypatch):
    from alphaos_api.mcp_auth import logger
    # Other UI integration tests can configure process-wide logging.
    monkeypatch.setattr(logger,'disabled',False)
    monkeypatch.setattr(logger,'propagate',True)
    caplog.set_level('WARNING',logger=logger.name)
    c,_,_,_=env
    _,tokens=login(c)
    assert 'stage=/authorize status=302' in caplog.text
    assert 'stage=/token status=200' in caplog.text
    for value in ('owner-test-secret','public-test-secret',tokens['access_token'],tokens['refresh_token']):
        assert value not in caplog.text


@pytest.mark.parametrize('failure',['redirect','oversize','wrong_content_type'])
def test_cimd_http_response_boundaries(env,monkeypatch,failure):
    import httpx
    from alphaos_api.mcp_auth import CHATGPT_CLIENT
    c,_,_,_=env
    requested=[]
    def response(request):
        requested.append(str(request.url))
        if failure=='redirect':
            return httpx.Response(302,headers={'Location':'https://evil.example/client.json'})
        if failure=='oversize':
            return httpx.Response(200,content=b'x'*65537,headers={'Content-Type':'application/json'})
        return httpx.Response(200,content=json.dumps(client_document()),headers={'Content-Type':'text/html'})
    original=httpx.AsyncClient
    def factory(*args,**kwargs):
        kwargs['transport']=httpx.MockTransport(response)
        return original(*args,**kwargs)
    monkeypatch.setattr(httpx,'AsyncClient',factory)
    assert authorize(c,CHATGPT_CLIENT)[0].status_code==400
    assert requested==[CHATGPT_CLIENT]


def test_protocol_diagnostics_allowlist_and_disable(env,monkeypatch,caplog):
    from alphaos_api.protocol_diagnostics import logger,redirect_kind
    monkeypatch.setattr(logger,'disabled',False)
    monkeypatch.setattr(logger,'propagate',True)
    caplog.set_level('WARNING',logger=logger.name)
    c,_,_,_=env
    response=c.post('/mcp?token=never-log-query',headers={'Authorization':'Bearer never-log-auth',
        'Cookie':'secret=never-log-cookie','Origin':'https://never-log-origin.example',
        'Accept':'never-log-accept','MCP-Protocol-Version':'never-log-version'},
        json={'method':'never-log-method','params':{'code':'never-log-code'}})
    assert response.status_code==401
    assert '"path": "/mcp"' in caplog.text and '"status": 401' in caplog.text
    assert 'never-log-' not in caplog.text
    _,tokens=login(c)
    assert not call(c,tokens['access_token'],'live_quote',{'symbol':'SPY'})['isError']
    assert '"rpc_method": "tools/call"' in caplog.text
    assert tokens['access_token'] not in caplog.text and tokens['refresh_token'] not in caplog.text
    assert 'owner-test-secret' not in caplog.text
    assert redirect_kind('https://[')=='other'
    caplog.clear();monkeypatch.setenv('ALPHAOS_PROTOCOL_DIAGNOSTICS','0')
    assert rpc(c,None,'tools/list').status_code==401
    assert 'alphaos_protocol' not in caplog.text
