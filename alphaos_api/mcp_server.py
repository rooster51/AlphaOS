"""Thin in-process MCP adapter to the existing validated REST/service workflows."""
from contextlib import asynccontextmanager
from datetime import date
import json
import os
from typing import Annotated, Literal
from urllib.parse import quote, urlsplit

import httpx
from pydantic import Field
from mcp.server.mcpserver import MCPServer
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings, RequestBodyLimitMiddleware
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from .contracts import TradeRequest, CompareRequest, SCHEMA_VERSION
from .mcp_auth import OwnerOAuth, SCOPE
from .protocol_diagnostics import ProtocolDiagnostics

INSTRUCTIONS = '''AlphaOS provides read-only market research, never trade execution or a recommended winner.
Preserve sample sizes, timestamps and caveats. Candidate generator order is not a ranking.
Historical frequencies are descriptive, not calibrated forecasts. Threshold survival is not option probability of profit.
Scenario EV is historical scenario economics, not guaranteed expectancy. Current quote and completed research session differ.
Calendar DTE and observed-session research horizon differ. A 0–2 DTE scan with research_horizon=3 is NOT expiration-matched profitability evidence.
Support/resistance describes historical price structure, not guaranteed floors or ceilings. Daily OHLC cannot reconstruct exact intraday paths.
Reuse snapshot_id for related context and candidate_id for saved scan research. Stale IDs require an explicit fresh scan.
Never request credentials in conversation or tool arguments. Authentication occurs only in the AlphaOS browser consent page.'''

Horizon = Literal[1,2,3,5,10]
Symbol = Annotated[str, Field(min_length=1,max_length=5,pattern=r'^[A-Za-z]+$')]
Positive = Annotated[float, Field(gt=0,allow_inf_nan=False)]


def build_mcp(app, sanitize):
    oauth = OwnerOAuth(os.environ.get('ALPHAOS_PUBLIC_URL','https://alphaos.onrender.com'))
    annotations = ToolAnnotations(read_only_hint=True, destructive_hint=False,
        idempotent_hint=True, open_world_hint=True)
    security = {'securitySchemes':[{'type':'oauth2','scopes':[SCOPE]}]}
    async def safe_results(ctx, call_next):
        result = await call_next(ctx)
        wire = result.model_dump(by_alias=True) if hasattr(result,'model_dump') else result
        if isinstance(wire,dict) and wire.get('isError') and not wire.get('structuredContent'):
            data={'schema_version':SCHEMA_VERSION,'error':{'code':'invalid_tool_request','message':'Invalid tool request'}}
            return CallToolResult(content=[TextContent(type='text',text=json.dumps(data))],structured_content=data,is_error=True)
        return result

    server = MCPServer('AlphaOS', version=SCHEMA_VERSION, instructions=INSTRUCTIONS,middleware=[safe_results],
        token_verifier=oauth, log_level='WARNING', auth=AuthSettings(issuer_url=oauth.base,
            resource_server_url=oauth.resource, required_scopes=[SCOPE], validate_token_resource=True))

    async def invoke(path, params=None, body=None):
        # ASGI transport does not make an external HTTP request. It preserves REST
        # validation, error sanitization, comparisons, and app.state.service caches.
        try:
            token = os.environ.get('ALPHAOS_API_TOKEN','')
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=oauth.base) as client:
                response = await client.request('POST' if body is not None else 'GET', path,
                    params={k:str(v).lower() if isinstance(v,bool) else v for k,v in (params or {}).items() if v is not None},
                    json=body, headers={'Authorization':'Bearer '+token})
            data = sanitize(response.json())
            return CallToolResult(content=[TextContent(type='text',text=json.dumps(data))],
                structured_content=data, is_error=response.status_code>=400)
        except Exception:
            data = {'schema_version':SCHEMA_VERSION,'error':{'code':'internal_error','message':'Research unavailable'}}
            return CallToolResult(content=[TextContent(type='text',text=json.dumps(data))], structured_content=data,is_error=True)

    tool = lambda description: server.tool(description=description,annotations=annotations,meta=security)

    @tool('Use for current spot plus completed-session market state. Preserve both timestamps and analog sample size. Reuse snapshot_id in structure/distribution calls.')
    async def market_snapshot(symbol: Symbol, horizon: Horizon=3, snapshot_id: str|None=None) -> CallToolResult:
        return await invoke('/v1/market/'+quote(symbol,safe=''),dict(horizon=horizon,snapshot_id=snapshot_id))

    @tool('Use for historical support/resistance zones, not guaranteed price barriers. Supply snapshot_id and matching horizon to reuse a market observation.')
    async def price_structure(symbol: Symbol, levels: Annotated[int,Field(ge=1,le=10)]=3,
            horizon: Horizon=3, snapshot_id: str|None=None) -> CallToolResult:
        return await invoke('/v1/structure/'+quote(symbol,safe=''),dict(levels=levels,horizon=horizon,snapshot_id=snapshot_id))

    @tool('Use for descriptive forward distributions over observed sessions. Historical scenarios are not calibrated forecasts; preserve N and caveats.')
    async def forward_distribution(symbol: Symbol, horizon: Horizon=3, snapshot_id: str|None=None) -> CallToolResult:
        return await invoke('/v1/distribution/'+quote(symbol,safe=''),dict(horizon=horizon,snapshot_id=snapshot_id))

    @tool('Use to retrieve the last available Public underlying quote and its timestamp/staleness flags. Quote time differs from the completed research session.')
    async def live_quote(symbol: Symbol) -> CallToolResult:
        return await invoke('/v1/quote/'+quote(symbol,safe=''))

    @tool('Use to resolve an explicit available expiration date before researching exact contracts. Do not substitute dates silently.')
    async def option_expirations(symbol: Symbol) -> CallToolResult:
        return await invoke('/v1/options/'+quote(symbol,safe='')+'/expirations')

    @tool('Use to enumerate unranked PCS/CCS evidence in generator order; the first candidate is not a recommendation. Calendar DTE differs from observed-session horizon: dte_min=0,dte_max=2,research_horizon=3 is NOT expiration-matched profitability evidence. Preserve N, caveats and candidate IDs. Credit is dollars/share; distances are fractions of spot. Explicit expiration overrides DTE filters. refresh requests new quotes.')
    async def scan_credit_spreads(symbol: Symbol, strategy: Literal['pcs','ccs','both']='both', expiration: date|None=None,
            dte_min: Annotated[int,Field(ge=0,le=180)]=1,dte_max: Annotated[int,Field(ge=0,le=180)]=7,
            research_horizon: Horizon=3,maximum_short_distance: Annotated[float,Field(gt=0,le=.25,allow_inf_nan=False)]=.05,
            minimum_credit: Annotated[float,Field(ge=0,allow_inf_nan=False)]=.05,
            maximum_candidates: Annotated[int,Field(ge=1,le=100)]=20,
            wing_width: Annotated[float,Field(gt=0,le=100,allow_inf_nan=False)]=1,refresh: bool=False) -> CallToolResult:
        params=dict(strategy=strategy,expiration=expiration,dte_min=dte_min,dte_max=dte_max,
            research_horizon=research_horizon,maximum_short_distance=maximum_short_distance,
            minimum_credit=minimum_credit,maximum_candidates=maximum_candidates,wing_width=wing_width,refresh=refresh)
        return await invoke('/v1/options/'+quote(symbol,safe='')+'/scan',params)

    @tool('Use for full research on an exact candidate_id returned by a recent scan. Reuses its saved quotes/history; stale IDs fail instead of silently repricing. Survival is not option POP.')
    async def research_candidate(candidate_id: Annotated[str,Field(max_length=100)]) -> CallToolResult:
        return await invoke('/v1/candidates/'+quote(candidate_id,safe=''))

    @tool('Use for an exact live vertical: explicit expiration, short strike, long strike, and put/call type. Uses short bid minus long ask, never substitutes contracts. Scenario EV is historical economics, not guaranteed expectancy. Horizon is observed sessions, not automatic expiration DTE.')
    async def research_vertical(symbol: Symbol,expiration: date,option_type: Literal['put','call'],
            short_strike: Positive,long_strike: Positive,horizon: Horizon=3,refresh: bool=False) -> CallToolResult:
        params=dict(expiration=expiration,option_type=option_type,short_strike=short_strike,
            long_strike=long_strike,horizon=horizon,refresh=refresh)
        return await invoke('/v1/options/'+quote(symbol,safe='')+'/vertical',params)

    @tool('Use for a user-supplied one-lot vertical with explicit spot and credit. Reuses TradeRequest validation and research; supplied prices are not verified live fills. Preserve sample sizes and caveats.')
    async def research_explicit_trade(trade: TradeRequest) -> CallToolResult:
        return await invoke('/v1/trade/research',body=trade.model_dump(mode='json'))

    @tool('Use to compare explicit verticals in input order using one shared context. Never choose a winner or rank. Symbol, spot, horizon, method and friction must match; each trade receives its own payoff evidence.')
    async def compare_trades(comparison: CompareRequest) -> CallToolResult:
        return await invoke('/v1/trade/compare',body=comparison.model_dump(mode='json'))

    host=urlsplit(oauth.base).netloc
    mcp_app=server.streamable_http_app(stateless_http=True,json_response=True,max_request_body_size=131072,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,
            allowed_hosts=[host,'localhost:*','127.0.0.1:*','testserver'],
            allowed_origins=[oauth.base,'https://chatgpt.com']))
    app.router.routes.extend(oauth.routes())
    app.add_middleware(RequestBodyLimitMiddleware,max_body_size=131072)
    app.add_middleware(ProtocolDiagnostics)
    app.mount('/',mcp_app)
    app.state.mcp=server
    app.state.oauth=oauth

    @asynccontextmanager
    async def lifespan(application):
        async with mcp_app.router.lifespan_context(mcp_app):
            yield
    app.router.lifespan_context=lifespan
