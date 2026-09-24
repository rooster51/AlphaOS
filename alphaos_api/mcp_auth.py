"""Private-owner OAuth adapter. Protocol validation/PKCE use the official MCP SDK."""
from collections import OrderedDict, deque
from html import escape
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from urllib.parse import urlencode, urlsplit, parse_qsl, urlunsplit, unquote

import httpx
from pydantic import AnyHttpUrl
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Route
from mcp.server.auth.provider import (AccessToken, AuthorizationCode, RefreshToken,
    AuthorizeError, RegistrationError, TokenError)
from mcp.server.auth.handlers.authorize import AuthorizationHandler
from mcp.server.auth.handlers.token import TokenHandler
from mcp.server.auth.handlers.register import RegistrationHandler
from mcp.server.auth.middleware.client_auth import ClientAuthenticator
from mcp.server.auth.routes import build_metadata
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from mcp.shared.auth import OAuthToken, OAuthClientInformationFull

SCOPE = 'research:read'
CHATGPT_CLIENT = 'https://chatgpt.com/oauth/client.json'
CHATGPT_CALLBACK = 'https://chatgpt.com/connector_platform_oauth_redirect'
logger = logging.getLogger(__name__)
SECURITY_HEADERS = {'Cache-Control': 'no-store', 'Pragma': 'no-cache',
    'Referrer-Policy': 'no-referrer', 'X-Content-Type-Options': 'nosniff',
    'Content-Security-Policy': "default-src 'none'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"}


def fingerprint(value):
    return hashlib.sha256(value.encode()).hexdigest()


class OwnerCode(AuthorizationCode):
    owner_version: str


class Store:
    def __init__(self, limit=256):
        self.entries = OrderedDict()
        self.limit = limit

    def put(self, key, value, ttl):
        now = time.time()
        for k in list(self.entries):
            if self.entries[k][0] <= now:
                self.entries.pop(k)
        if len(self.entries) >= self.limit:
            self.entries.popitem(last=False)
        self.entries[key] = (now + ttl, value)

    def get(self, key, consume=False):
        item = self.entries.pop(key, None) if consume else self.entries.get(key)
        if item is None or item[0] <= time.time():
            self.entries.pop(key, None)
            return None
        return item[1]


class OwnerOAuth:
    """One process/owner; restarting revokes all grants. No brokerage tokens issued."""
    def __init__(self, base_url):
        self.base = base_url.rstrip('/')
        parsed = urlsplit(self.base)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username:
            raise ValueError('MCP public URL must be an HTTPS origin.')
        self.resource = self.base + '/mcp'
        self.clients = Store(128)
        self.metadata_clients = Store(128)
        self.pending = Store(128)
        self.codes = Store(128)
        self.access = Store(512)
        self.refresh = Store(512)
        self.spent_refresh = Store(2048)
        self.requests = {}

    def limited(self, bucket, limit, seconds=60):
        queue = self.requests.setdefault(bucket, deque())
        now = time.time()
        while queue and queue[0] <= now - seconds:
            queue.popleft()
        if len(queue) >= limit:
            return True
        queue.append(now)
        return False

    async def get_client(self, client_id):
        # A published client identity is recoverable after process restart. Only
        # exact official ChatGPT document locations may be fetched (no redirects).
        if client_id == CHATGPT_CLIENT or re.fullmatch(
                r'https://chatgpt\.com/oauth/[A-Za-z0-9_-]{1,100}/client\.json', client_id):
            cached = self.metadata_clients.get(client_id)
            if cached:
                return cached
            try:
                document, ttl = await self.fetch_client_metadata(client_id)
                methods = document.get('token_endpoint_auth_methods_supported')
                if methods is None:
                    methods = [document.get('token_endpoint_auth_method')]
                if (document.get('client_id') != client_id or not isinstance(methods,list)
                        or 'none' not in methods):
                    return None
                callback = (CHATGPT_CALLBACK if client_id == CHATGPT_CLIENT else
                    'https://chatgpt.com/connector/oauth/'+client_id.split('/')[-2])
                if document.get('redirect_uris') != [callback]:
                    return None
                if (set(document.get('grant_types',[])) != {'authorization_code','refresh_token'}
                        or document.get('response_types') != ['code']):
                    return None
                client = OAuthClientInformationFull(client_id=client_id,
                    redirect_uris=[callback],token_endpoint_auth_method='none',
                    grant_types=['authorization_code','refresh_token'],response_types=['code'],
                    scope=SCOPE,client_name='ChatGPT',application_type='web')
                if ttl > 0:
                    self.metadata_clients.put(client_id,client,ttl)
                return client
            except Exception:
                return None
        return self.clients.get(client_id)

    async def fetch_client_metadata(self, client_id):
        async with httpx.AsyncClient(timeout=10,follow_redirects=False) as client:
            async with client.stream('GET',client_id,headers={'Accept':'application/json'}) as response:
                if response.status_code != 200 or 'application/json' not in response.headers.get('content-type',''):
                    raise ValueError('Invalid client metadata')
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 65536:
                        raise ValueError('Client metadata too large')
                cache = response.headers.get('cache-control','').lower()
                age = re.search(r'(?:^|,)\s*max-age=(\d+)',cache)
                ttl = min(300,int(age[1])) if age else 60
                if 'no-store' in cache or 'no-cache' in cache:
                    ttl = 0
                return json.loads(body),ttl

    async def basic_client_request(self, request):
        # SDK 2.2 requires form client_id even for RFC 6749 HTTP Basic.
        # Adapt header-only requests; the SDK still verifies ID and secret.
        header = request.headers.get('authorization','')
        if not header.startswith('Basic '):
            return request
        form = await request.form()
        if form.get('client_id'):
            return request  # Let the SDK reject conflicting header/body IDs.
        decoded = base64.b64decode(header[6:],validate=True).decode('utf-8')
        client_id, _ = decoded.split(':',1)
        body = urlencode([*form.multi_items(),('client_id',unquote(client_id))]).encode()
        scope = dict(request.scope)
        scope['headers'] = [(k,v) for k,v in scope['headers'] if k not in (b'content-length',b'content-type')]
        scope['headers'] += [(b'content-type',b'application/x-www-form-urlencoded'),
            (b'content-length',str(len(body)).encode())]
        async def receive():
            return {'type':'http.request','body':body,'more_body':False}
        return Request(scope,receive)

    async def register_client(self, client_info):
        if not client_info.redirect_uris or len(client_info.redirect_uris) > 2:
            raise RegistrationError('invalid_redirect_uri')
        for uri in client_info.redirect_uris:
            # Exact official callback forms, never arbitrary redirects or userinfo.
            if not re.fullmatch(r'https://chatgpt\.com/(?:connector_platform_oauth_redirect|connector/oauth/[A-Za-z0-9_-]+)', str(uri)):
                raise RegistrationError('invalid_redirect_uri')
        if set(client_info.grant_types) - {'authorization_code', 'refresh_token'}:
            raise RegistrationError('invalid_client_metadata')
        self.clients.put(client_info.client_id, client_info, 86400)

    async def authorize(self, client, params):
        if params.resource != self.resource:
            raise AuthorizeError('invalid_target')
        if params.scopes != [SCOPE] or not re.fullmatch(r'[A-Za-z0-9_-]{43}', params.code_challenge):
            raise AuthorizeError('invalid_request')
        if not os.environ.get('ALPHAOS_API_TOKEN'):
            raise AuthorizeError('temporarily_unavailable')
        ticket = secrets.token_urlsafe(32)
        self.pending.put(fingerprint(ticket), {'client': client, 'params': params, 'csrf': None}, 300)
        return self.base + '/oauth/consent?' + urlencode({'ticket': ticket})

    async def load_authorization_code(self, client, authorization_code):
        return self.codes.get(fingerprint(authorization_code))

    def issue(self, client_id, scopes, family=None):
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        family = family or secrets.token_urlsafe(24)
        owner_version = fingerprint(os.environ.get('ALPHAOS_API_TOKEN', ''))
        a = AccessToken(token=access, client_id=client_id, scopes=scopes,
            expires_at=int(time.time())+900, resource=self.resource, subject='owner', claims={'iss': self.base})
        r = RefreshToken(token=refresh, client_id=client_id, scopes=scopes,
            expires_at=int(time.time())+28800, resource=self.resource, subject='owner')
        self.access.put(fingerprint(access), (a, family, owner_version), 900)
        self.refresh.put(fingerprint(refresh), (r, family, owner_version), 28800)
        return OAuthToken(access_token=access, token_type='Bearer', expires_in=900,
            refresh_token=refresh, scope=' '.join(scopes))

    async def exchange_authorization_code(self, client, authorization_code):
        code = self.codes.get(fingerprint(authorization_code.code), consume=True)
        if (code is None or code.client_id != client.client_id
            or code.owner_version != fingerprint(os.environ.get('ALPHAOS_API_TOKEN',''))):
            raise TokenError('invalid_grant')
        return self.issue(client.client_id, code.scopes)

    async def load_refresh_token(self, client, refresh_token):
        key = fingerprint(refresh_token)
        entry = self.refresh.get(key)
        spent = self.spent_refresh.get(key)
        if spent and spent[0] == client.client_id:
            self.revoke_family(spent[1])
            return None
        if entry and entry[2] == fingerprint(os.environ.get('ALPHAOS_API_TOKEN', '')):
            return entry[0]
        return None

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        entry = self.refresh.get(fingerprint(refresh_token.token), consume=True)
        if entry is None or entry[0].client_id != client.client_id:
            raise TokenError('invalid_grant')
        self.spent_refresh.put(fingerprint(refresh_token.token),(client.client_id,entry[1]),28800)
        return self.issue(client.client_id, scopes, entry[1])

    async def verify_token(self, token):
        entry = self.access.get(fingerprint(token))
        if entry and entry[2] == fingerprint(os.environ.get('ALPHAOS_API_TOKEN', '')):
            return entry[0]
        return None

    async def load_access_token(self, token):
        return await self.verify_token(token)

    async def revoke_token(self, token):
        key = fingerprint(token.token)
        entry = self.access.get(key) or self.refresh.get(key)
        if entry:
            self.revoke_family(entry[1])

    def revoke_family(self, family):
        for store in (self.access,self.refresh):
            for key,(_,value) in list(store.entries.items()):
                if value[1] == family:
                    store.entries.pop(key,None)

    async def revoke(self, request):
        # SDK 2.2's revocation form requires client_secret even for public clients.
        # Authenticate through its shared authenticator, then implement RFC 7009's
        # same-client, idempotent revocation without requiring a dummy secret.
        if self.limited('revoke', 30):
            return JSONResponse({'error':'rate_limited'},429,headers=SECURITY_HEADERS)
        try:
            request = await self.basic_client_request(request)
            client = await ClientAuthenticator(self).authenticate_request(request)
            form = await request.form()
            raw = str(form.get('token',''))
            token = await self.load_access_token(raw) or await self.load_refresh_token(client,raw)
            if token and token.client_id == client.client_id:
                await self.revoke_token(token)
            return JSONResponse({}, headers=SECURITY_HEADERS)
        except Exception:
            return JSONResponse({'error':'invalid_client'},401,headers=SECURITY_HEADERS)

    async def consent(self, request):
        if request.method == 'GET':
            ticket = request.query_params.get('ticket', '')
            pending = self.pending.get(fingerprint(ticket))
            if not pending:
                return JSONResponse({'error': 'invalid_request'}, 400, headers=SECURITY_HEADERS)
            csrf = secrets.token_urlsafe(32)
            pending['csrf'] = fingerprint(csrf)
            # All user/client-provided text is escaped; no external assets/scripts.
            client_id = escape(pending['client'].client_id)
            redirect = escape(str(pending['params'].redirect_uri))
            html = f'''<!doctype html><html><head><title>Connect AlphaOS research</title></head><body>
<h1>Allow read-only AlphaOS research</h1>
<p>This client can access Public market data and historical research. It cannot place orders or access portfolio endpoints.</p>
<p>Client: {client_id}<br>Return address: {redirect}</p>
<p>Enter your AlphaOS API token here on AlphaOS only. Never enter your Public secret or paste credentials into a conversation.</p>
<form method="post" action="/oauth/consent">
<input type="hidden" name="ticket" value="{escape(ticket)}">
<input type="hidden" name="csrf" value="{escape(csrf)}">
<label>AlphaOS owner token <input type="password" name="owner_token" required autocomplete="off"></label>
<button name="decision" value="allow">Allow research access</button>
<button name="decision" value="deny" formnovalidate>Cancel</button></form></body></html>'''
            response = HTMLResponse(html, headers=SECURITY_HEADERS)
            response.set_cookie('__Host-alphaos-consent', csrf, max_age=300, secure=True, httponly=True, samesite='lax', path='/')
            return response
        if self.limited('consent', 10):
            return JSONResponse({'error': 'rate_limited'}, 429, headers=SECURITY_HEADERS)
        form = await request.form()
        ticket, csrf = str(form.get('ticket','')), str(form.get('csrf',''))
        pending = self.pending.get(fingerprint(ticket))
        cookie = request.cookies.get('__Host-alphaos-consent','')
        if (not pending or not csrf or not cookie or not hmac.compare_digest(csrf, cookie)
            or not hmac.compare_digest(fingerprint(csrf), pending['csrf'] or '')
            or request.headers.get('origin') != self.base):
            return JSONResponse({'error': 'invalid_request'}, 400, headers=SECURITY_HEADERS)
        params, client = pending['params'], pending['client']
        fields = {'state': params.state, 'iss': self.base}
        if form.get('decision') == 'deny':
            fields['error'] = 'access_denied'
        elif form.get('decision') == 'allow':
            expected = os.environ.get('ALPHAOS_API_TOKEN','')
            provided = str(form.get('owner_token',''))
            if not expected or not hmac.compare_digest(provided.encode(), expected.encode()):
                return JSONResponse({'error': 'access_denied'}, 403, headers=SECURITY_HEADERS)
            code = secrets.token_urlsafe(32)
            self.codes.put(fingerprint(code), OwnerCode(code=code, client_id=client.client_id,
                scopes=[SCOPE], expires_at=time.time()+60, code_challenge=params.code_challenge,
                redirect_uri=params.redirect_uri, redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
                resource=self.resource, subject='owner',owner_version=fingerprint(expected)), 60)
            fields['code'] = code
        else:
            return JSONResponse({'error':'invalid_request'},400,headers=SECURITY_HEADERS)
        self.pending.get(fingerprint(ticket), consume=True)
        response = RedirectResponse(str(params.redirect_uri)+'?'+urlencode({k:v for k,v in fields.items() if v is not None}), 303, headers=SECURITY_HEADERS)
        response.delete_cookie('__Host-alphaos-consent', secure=True, httponly=True, samesite='lax')
        return response

    def routes(self):
        options = ClientRegistrationOptions(enabled=True, valid_scopes=[SCOPE], default_scopes=[SCOPE])
        authenticator = ClientAuthenticator(self)
        metadata = build_metadata(AnyHttpUrl(self.base), None, options, RevocationOptions(enabled=True))
        data = metadata.model_dump(mode='json', exclude_none=True)
        # AnyHttpUrl normalizes an empty path to '/'. RFC 9207 requires exact
        # equality with protected-resource authorization_servers and callback iss.
        data.update(issuer=self.base,authorization_response_iss_parameter_supported=True,
            client_id_metadata_document_supported=True,
            token_endpoint_auth_methods_supported=['none','client_secret_post','client_secret_basic'],
            revocation_endpoint_auth_methods_supported=['none','client_secret_post','client_secret_basic'])

        async def discovery(request):
            return JSONResponse(data, headers=SECURITY_HEADERS)

        def guarded(handler, name):
            async def call(request):
                if self.limited(name, 30):
                    return JSONResponse({'error':'rate_limited'}, 429, headers=SECURITY_HEADERS)
                try:
                    if name == 'token':
                        request = await self.basic_client_request(request)
                        form = await request.form()
                        if form.get('resource') != self.resource:
                            return JSONResponse({'error':'invalid_target'}, 400, headers=SECURITY_HEADERS)
                    response = await handler.handle(request)
                    if response.status_code >= 400:
                        # Preserve protocol error codes so clients can reconnect on
                        # invalid_grant; never reflect descriptions/input values.
                        code = json.loads(response.body).get('error')
                        allowed = {'invalid_request','invalid_client','invalid_grant',
                            'invalid_scope','invalid_target','unauthorized_client',
                            'unsupported_grant_type','invalid_redirect_uri','invalid_client_metadata'}
                        return JSONResponse({'error':code if code in allowed else 'invalid_request'},
                            response.status_code, headers=SECURITY_HEADERS)
                    location = response.headers.get('location')
                    if name == 'authorize' and location and urlsplit(location).hostname == 'chatgpt.com':
                        parts = urlsplit(location)
                        query = dict(parse_qsl(parts.query)); query['iss'] = self.base
                        query.pop('error_description',None)
                        response.headers['location'] = urlunsplit(parts._replace(query=urlencode(query)))
                    response.headers.update(SECURITY_HEADERS)
                    return response
                except Exception:
                    return JSONResponse({'error':'invalid_request'}, 400, headers=SECURITY_HEADERS)
            return call
        routes = [Route('/.well-known/oauth-authorization-server', discovery),
            Route('/authorize', guarded(AuthorizationHandler(self),'authorize'), methods=['GET','POST']),
            Route('/register', guarded(RegistrationHandler(self,options),'register'), methods=['POST']),
            Route('/token', guarded(TokenHandler(self,authenticator),'token'), methods=['POST']),
            Route('/revoke', self.revoke, methods=['POST']),
            Route('/oauth/consent', self.consent, methods=['GET','POST'])]
        # Safe stage/status diagnostics only: never URLs with queries, client IDs,
        # headers, bodies, codes, tokens, or exception text.
        def traced(endpoint, stage):
            async def call(request):
                response = await endpoint(request)
                logger.warning('alphaos_oauth stage=%s status=%d',stage,response.status_code)
                return response
            return call
        return [Route(route.path,traced(route.endpoint,route.path),methods=route.methods) for route in routes]
