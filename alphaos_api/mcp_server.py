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
from .positions import EntryRequest, CloseRequest
from .journal import JournalFilters, Group
from uuid import UUID

INSTRUCTIONS = '''For symbol research requests (Run QQQ/SPY/SPX/XSP), use run_symbol_research for one coherent workflow.
Use mode=overview for market context and mode=find for candidate discovery. For Refresh SYMBOL alone use mode=overview, refresh=true; scan only when requested.
Present data state, context/structure, then qualifying candidates in generator order; disclose defaults and stopped stages.
Never label stopped/context-only research live. Ask for missing expiration or spread identity; never infer a held position.
AlphaOS provides read-only market research, never trade execution or a recommended winner.
Preserve sample sizes, timestamps and caveats. Candidate generator order is not a ranking.
Historical frequencies are descriptive, not calibrated forecasts. Threshold survival is not option probability of profit.
Scenario EV is historical scenario economics, not guaranteed expectancy. Current quote and completed research session differ.
Calendar DTE and observed-session research horizon differ. A 0–2 DTE scan with research_horizon=3 is NOT expiration-matched profitability evidence.
Support/resistance describes historical price structure, not guaranteed floors or ceilings. Daily OHLC cannot reconstruct exact intraday paths.
Reuse snapshot_id for related context and candidate_id for saved scan research. Stale IDs require an explicit fresh scan.
For exact spread follow-ups prefer unified_candidate_research with a returned candidate_id, or unified_vertical_research with explicit expiration and strikes. PCS is short higher put/long lower put; CCS short lower call/long higher call. Do not silently choose expiration. For Compare those two, reuse existing compare_trades only with matching explicit symbol, scenario spot, horizon, method and friction; otherwise refresh/clarify the common context. Prices supplied for comparison are explicit scenarios, not verified fills. No winner selection. Use separate local tracking tools only for user-declared entries and closures.
For SPX use actual SPX data and SPXW PM-settled contracts; other roots including SPX are unverified and unsupported. For XSP use actual XSP data. Default wings are 5 points for SPX and 1 for SPY/QQQ/XSP; never substitute a requested unavailable width. A 0DTE request must use the current America/New_York date and dte_min=dte_max=0. Historical sessions are not intraday expiration probabilities.
Local tracking is distinct from research: record_position and close_position change only AlphaOS records, never brokerage positions. Resolve ambiguous matches with get_active_positions before selecting an ID. Monitor descriptors are not recommendations or probabilities. Never request credentials in conversation or tool arguments. Authentication occurs only in the AlphaOS browser consent page.'''

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
            wing_width: Annotated[float|None,Field(gt=0,le=100,allow_inf_nan=False)]=None,refresh: bool=False) -> CallToolResult:
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

    @tool('Use this when the user asks Run QQQ/SPY/SPX/XSP, what is QQQ doing, find trades, or refresh a symbol. One workflow validates data, retrieves context/structure and optionally unranked vertical candidates. mode=run also researches each returned candidate; overview excludes scans; find returns candidate IDs. Defaults: 1-7 calendar DTE, 3 observed sessions, first 4 generator entries (not ranked), $5 SPX wings or $1 SPY/QQQ/XSP wings, $0.05 credit/share. State all defaults. Stale or closed quotes stop live scans. refresh=true refreshes quote/chain observations. Do not use to manage positions or execute trades.')
    async def run_symbol_research(symbol: Symbol,mode: Literal['run','overview','find']='run',horizon: Horizon=3,
            strategy: Literal['pcs','ccs','both']='both',expiration: date|None=None,
            dte_min: Annotated[int,Field(ge=0,le=180)]=1,dte_max: Annotated[int,Field(ge=0,le=180)]=7,
            maximum_candidates: Annotated[int,Field(ge=1,le=10)]=4,
            minimum_credit: Annotated[float,Field(ge=0,allow_inf_nan=False)]=.05,
            wing_width: Annotated[float|None,Field(gt=0,le=100,allow_inf_nan=False)]=None,refresh: bool=False) -> CallToolResult:
        return await invoke('/v1/research/'+quote(symbol,safe='')+'/run',dict(mode=mode,horizon=horizon,strategy=strategy,
            expiration=expiration,dte_min=dte_min,dte_max=dte_max,maximum_candidates=maximum_candidates,
            minimum_credit=minimum_credit,wing_width=wing_width,refresh=refresh))

    @tool('Use this when researching a qualifying candidate from a recent scan. Returns unified Trade Snapshot, Market Structure, Historical Analog Behavior at short/breakeven/long strikes, Historical Scenario Payoff, and Advanced Research. Uses the saved observation without silent repricing; expired IDs require a new explicit scan. include_advanced exposes detailed tables. Historical frequencies are not future probabilities.')
    async def unified_candidate_research(candidate_id: Annotated[str,Field(max_length=100)],include_advanced: bool=False) -> CallToolResult:
        return await invoke('/v1/research/candidates/'+quote(candidate_id,safe=''),dict(include_advanced=include_advanced))

    @tool('Use this when the user asks to research an exact PCS or CCS by strikes. Requires explicit symbol and expiration: ask if missing unless resolved from a returned candidate. Put short strike must exceed long strike; call short must be below long. Returns five unified research sections; hypothetical current natural credit, not held-position P&L. Freshness gating is mandatory. include_advanced adds details.')
    async def unified_vertical_research(symbol: Symbol,expiration: date,option_type: Literal['put','call'],
            short_strike: Positive,long_strike: Positive,horizon: Horizon=3,refresh: bool=False,include_advanced: bool=False) -> CallToolResult:
        return await invoke('/v1/research/'+quote(symbol,safe='')+'/vertical',dict(expiration=expiration,option_type=option_type,
            short_strike=short_strike,long_strike=long_strike,horizon=horizon,refresh=refresh,include_advanced=include_advanced))

    @tool('Use this for unified non-live historical scenario research of a user-entered vertical with explicit spot and credit, including when markets are closed. Prices are user inputs, not verified live fills or held-position P&L. Returns the same five trade-centered sections. No position management or execution.')
    async def unified_explicit_trade_research(trade: TradeRequest,include_advanced: bool=False) -> CallToolResult:
        return await invoke('/v1/research/trade',dict(include_advanced=include_advanced),body=trade.model_dump(mode='json'))

    tracking_annotations = ToolAnnotations(read_only_hint=False,destructive_hint=False,
        idempotent_hint=True,open_world_hint=False)

    @server.tool(description='Record only an explicitly user-declared PCS/CCS entry in AlphaOS local tracking. Never infer execution from research. Supply a UUID request_id and reuse it for retries. Entry timestamp must include timezone. Captured evidence is observed now, not reconstructed historically. No brokerage order is submitted.',annotations=tracking_annotations,meta=security)
    async def record_position(entry: EntryRequest) -> CallToolResult:
        return await invoke('/v1/positions',body=entry.model_dump(mode='json'))

    @tool('List locally recorded active positions, optionally filtered by symbol. If multiple positions match, present matches and ask for selection; never guess a position_id.')
    async def get_active_positions(symbol: Symbol|None=None) -> CallToolResult:
        return await invoke('/v1/positions',dict(symbol=symbol))

    @tool('Refresh exact contracts for an active position_id and compare with its frozen entry evidence. Values are quote estimates, not fills. Preserve quality limitations and individual state reasons. No recommendations or execution. Does not rerun historical research.')
    async def monitor_position(position_id: UUID) -> CallToolResult:
        return await invoke('/v1/positions/'+str(position_id)+'/monitor')

    @server.tool(description='Record explicit user-declared closure of a selected position_id in local tracking only. Supply timestamp with timezone and classify exit_basis: actual (default; explicit fill amount), estimated (explicit estimate, excluded from realized results), or unknown (omit amount). Optional exit_reason/user_note. Never infer closure or a fill from quotes. No brokerage order is submitted.',annotations=tracking_annotations,meta=security)
    async def close_position(position_id: UUID,closure: CloseRequest) -> CallToolResult:
        return await invoke('/v1/positions/'+str(position_id)+'/close',body=closure.model_dump(mode='json'))

    @tool('Retrieve a locally tracked active or closed position by position_id, including immutable entry evidence and any explicit declared closure.')
    async def get_position(position_id: UUID) -> CallToolResult:
        return await invoke('/v1/positions/'+str(position_id))

    @tool('List closed recorded trades with filters and pagination, newest closure first. Always preserve n_closed and per-trade evidence availability. Actual user-declared outcomes differ from estimates and historical scenario EV. Missing monitoring/regime/VWAP evidence is unknown; never invent it.')
    async def get_trade_journal(filters: JournalFilters|None=None,limit: Annotated[int,Field(ge=1,le=100)]=20,
            offset: Annotated[int,Field(ge=0)]=0) -> CallToolResult:
        return await invoke('/v1/journal',dict(**(filters or JournalFilters()).model_dump(mode='json',exclude_none=True),limit=limit,offset=offset))

    @tool('Review a recorded position by explicit position_id: immutable entry evidence, paginated append-only monitoring timeline, declared outcome and metrics. MFE/MAE describe recorded observations only, never continuous paths. No market data or historical research is rerun. Use journal filters to resolve ambiguous requests first.')
    async def get_trade_review(position_id: UUID,event_limit: Annotated[int,Field(ge=1,le=500)]=100,
            event_offset: Annotated[int,Field(ge=0)]=0) -> CallToolResult:
        return await invoke('/v1/journal/'+str(position_id),dict(event_limit=event_limit,event_offset=event_offset))

    @tool('Summarize actual user-declared closed outcomes, optionally grouped by symbol/strategy/DTE/time/context/reason/history. Every metric includes n; disclose small samples and missing evidence. Realized Expectancy Per Recorded Trade is not Historical Scenario EV or forecast POP. Estimates/unknown fills are excluded from realized metrics. Groups are labels, never rankings. Recorded 50% mark comparisons do not establish causality or continuous profit giveback.')
    async def get_trade_performance(filters: JournalFilters|None=None,group_by: Group|None=None) -> CallToolResult:
        return await invoke('/v1/journal/performance',dict(**(filters or JournalFilters()).model_dump(mode='json',exclude_none=True),group_by=group_by))

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
