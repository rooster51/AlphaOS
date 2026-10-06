"""Temporary allowlisted protocol diagnostics. Never record raw request values."""
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import os
import secrets
from urllib.parse import parse_qs, urlsplit

logger = logging.getLogger(__name__)
request_id = ContextVar('protocol_request_id', default='outside_request')
PATHS = {'/mcp','/mcp/','/.well-known/oauth-protected-resource',
    '/.well-known/oauth-protected-resource/mcp','/.well-known/oauth-authorization-server',
    '/.well-known/openid-configuration','/register','/authorize','/token','/revoke','/oauth/consent'}
ERRORS = {'invalid_request','invalid_client','invalid_grant','invalid_scope','invalid_target',
    'unsupported_grant_type','invalid_redirect_uri','invalid_client_metadata','access_denied',
    'invalid_token','insufficient_scope','rate_limited'}


def enabled():
    return os.environ.get('ALPHAOS_PROTOCOL_DIAGNOSTICS','1') == '1'


def emit(event, **fields):
    if enabled():
        logger.warning('alphaos_protocol %s',json.dumps(dict(
            timestamp=datetime.now(timezone.utc).isoformat(),request_id=request_id.get(),
            event=event,**fields),sort_keys=True))


def client_kind(value):
    if value == 'https://chatgpt.com/oauth/client.json':
        return 'cimd_stable'
    if value.startswith('https://chatgpt.com/oauth/') and value.endswith('/client.json'):
        return 'cimd_callback'
    return 'registered_or_unknown' if value else 'missing'


def redirect_kind(value):
    try:
        parsed=urlsplit(value)
    except ValueError:
        return 'other'
    if parsed.scheme == 'https' and parsed.netloc == 'chatgpt.com':
        if parsed.path == '/connector_platform_oauth_redirect':
            return 'chatgpt.com/connector_platform_oauth_redirect'
        if parsed.path.startswith('/connector/oauth/'):
            return 'chatgpt.com/connector/oauth/{redacted}'
    return 'other' if value else 'missing'


class ProtocolDiagnostics:
    def __init__(self,app):
        self.app=app

    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or scope.get('path') not in PATHS or not enabled():
            return await self.app(scope,receive,send)
        marker=request_id.set(secrets.token_hex(6))
        path=scope['path'];headers=dict(scope.get('headers',[]))
        accept=headers.get(b'accept',b'').lower()
        content_type=headers.get(b'content-type',b'').split(b';')[0].lower()
        origin=headers.get(b'origin',b'')
        version=headers.get(b'mcp-protocol-version',b'')
        fields=dict(path=path,method=scope['method'] if scope['method'] in
            {'GET','POST','OPTIONS','DELETE','HEAD'} else 'other',
            accept_json=b'application/json' in accept,accept_sse=b'text/event-stream' in accept,
            accept_present=bool(accept),content_type=content_type.decode() if content_type in
                {b'application/json',b'application/x-www-form-urlencoded',b'text/event-stream'} else 'other_or_missing',
            origin='chatgpt' if origin==b'https://chatgpt.com' else ('missing' if not origin else 'other'),
            protocol_version=version.decode() if version in {b'2024-11-05',b'2025-03-26',b'2025-06-18',b'2025-11-25',b'2026-07-28'} else 'other_or_missing')
        query=parse_qs(scope.get('query_string',b'').decode('utf-8',errors='replace'))
        if path=='/authorize':
            fields.update(client_registration=client_kind(query.get('client_id',[''])[0]),
                redirect=redirect_kind(query.get('redirect_uri',[''])[0]))
        body=bytearray();response_body=bytearray();status=0
        async def read():
            message=await receive()
            if message['type']=='http.request' and len(body)<131072:
                body.extend(message.get('body',b'')[:131072-len(body)])
            return message
        async def write(message):
            nonlocal status
            if message['type']=='http.response.start':status=message['status']
            if message['type']=='http.response.body' and len(response_body)<1024 and status>=400:
                response_body.extend(message.get('body',b'')[:1024-len(response_body)])
            await send(message)
        try:
            await self.app(scope,read,write)
        finally:
            try:
                if path in {'/mcp','/mcp/','/register'} and body:
                    data=json.loads(body)
                    if isinstance(data,dict):
                        if path=='/register':
                            method=data.get('token_endpoint_auth_method')
                            fields.update(client_registration='dcr',client_auth_method=method if method in
                                {'none','client_secret_post','client_secret_basic','private_key_jwt'} else 'default_or_other')
                            uris=data.get('redirect_uris')
                            if isinstance(uris,list) and uris and isinstance(uris[0],str):fields['redirect']=redirect_kind(uris[0])
                        else:
                            method=data.get('method')
                            fields['rpc_method']=method if method in {'initialize','notifications/initialized','tools/list','tools/call','ping'} else 'other'
                if response_body:
                    data=json.loads(response_body);error=data.get('error')
                    fields['error']=error if isinstance(error,str) and error in ERRORS else 'protocol_or_other'
            except (ValueError,TypeError,AttributeError):
                fields['parse']='not_json'
            emit('http',status=status,**fields)
            request_id.reset(marker)
