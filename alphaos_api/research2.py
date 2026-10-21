"""Read-only interface orchestration; research stays in the AlphaOS modules."""
from datetime import date, datetime, timezone
from math import isfinite
import os
from typing import Literal
import asyncio
from anyio import to_thread
from fastapi import Request as HTTPRequest
from starlette.responses import Response

from pydantic import BaseModel, ConfigDict, Field
from modules.position_research import research_position
from modules.market_archive_adapter import ArchiveExpirationUnavailable
from modules.strategy_compare import compare_strategy_research
from modules.run_market import run_latest_market
from modules.structure_economics import structure_historical_economics, compare_historical_economics
from modules.supabase_archive import research_archive_client as archive_client, read_latest_option_snapshot, ArchiveUnavailable
from .contracts import APIError
from modules.research_timing import execution, stage as timing_stage

VERSION = 'alphaos-interface-v2'


class Request(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class MarketRequest(Request):
    symbol: Literal['QQQ', 'SPY']
    research_mode: Literal['current', 'historical'] = 'current'
    expiration: date | None = None
    available_capital: float | None = Field(default=None, gt=0, strict=True)
    objective: str | None = Field(default=None, max_length=1000)
    width: float | None = Field(default=None, gt=0, le=100, strict=True)


class StructureLeg(Request):
    type: Literal['Call', 'Put']
    strike: float = Field(gt=0)
    qty: int = Field(ge=-100, le=100, strict=True)


class StructureRequest(Request):
    symbol: Literal['QQQ', 'SPY']
    expiration: date
    as_of: date
    spot: float = Field(gt=0)
    credit: float  # signed package cashflow per share, debit negative
    fees: float = Field(default=0, ge=0)
    legs: list[StructureLeg] = Field(min_length=1, max_length=4)


class StructuresRequest(Request):
    structures: list[StructureRequest] = Field(min_length=1, max_length=20)
    thesis: str | None = Field(default=None, max_length=1000)


def json_safe(value):
    """Preserve unbounded payoff meaning; never emit nonstandard JSON numbers."""
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, float) and not isfinite(value):
        return 'unlimited' if value == float('inf') else None
    return value


def envelope(request, research, source, caveats=(), *, json_ready=True):
    value = dict(schema_version=VERSION, request=request.model_dump(mode='json'),
        read_only=True, research=research, provenance=dict(source=source), caveats=list(caveats))
    return json_safe(value) if json_ready else value


class ArchiveResearchService:
    def __init__(self, *, read_snapshot=None, history_loader=None, clock=None):
        self.read_snapshot = read_snapshot or self._read
        self.history_loader = history_loader or self._history
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _read(symbol, as_of, *, research_mode='current'):
        # Lazy trusted server wiring. No connection or secret loading on import.
        # Reader implements ALL selection, checksum, identity and freshness rules.
        try:
            age = float(os.environ.get('ALPHAOS_ARCHIVE_MAX_AGE_SECONDS', '600'))
            if not isfinite(age) or age < 0:
                raise ValueError()
            with timing_stage('archive_client'):
                client = archive_client()
            return read_latest_option_snapshot(client, symbol, as_of,
                max_age_seconds=age, research_mode=research_mode)
        except ArchiveUnavailable:
            raise
        except Exception:
            raise ArchiveUnavailable('Archive unavailable or invalid configuration.') from None

    @staticmethod
    def _history(symbol):
        # Reuse the historical API provider's daily bars, not a second collector.
        from modules.public_provider import get_public_research_bars
        bars = get_public_research_bars(symbol, 'FIVE_YEARS').copy()
        bars['symbol'] = symbol
        return bars

    def run(self, request, *, json_ready=True):
        with execution(request.symbol, request.research_mode):
            return self._run(request, json_ready=json_ready)

    def _run(self, request, *, json_ready=True):
        history = None
        history_loading = dict(status="unavailable", reason="completed_history_unavailable")
        caveats = ['Archive observations are not executable live quotes.',
            'Capital is expiration max-loss eligibility, not broker buying power or margin.',
            'Objective is recorded context; it does not override evidence or filter strategy routes.',
            'Omitted/null width selects automatic observed-strike enumeration; a numeric width is an exact manual override. Omitted expiration uses the archive adapter selection.']
        # Load/verify archive FIRST; never fall back to live chain on failure.
        now = self.clock()
        try:
            with timing_stage('archive_read'):
                record = self.read_snapshot(request.symbol, now.isoformat(), **(
                    {'research_mode': 'historical'} if request.research_mode == 'historical' else {}))
        except ArchiveUnavailable as error:
            raise APIError(error.code, 503) from None
        except Exception:
            raise APIError('archive_unavailable', 503) from None
        try:
            with timing_stage('history_load'):
                history = self.history_loader(request.symbol)
            if history is not None:
                history_loading = dict(status="loaded", reason=None)
        except Exception as error:
            # Fixed provider codes only. Never return exception text, credentials,
            # SDK diagnostics, headers or arbitrary caller-supplied attributes.
            from modules.public_provider import PublicProviderError
            if isinstance(error, PublicProviderError) and error.code in {
                    'public_not_configured', 'public_authentication_failure',
                    'public_rate_limit', 'provider_unavailable'}:
                history_loading['reason'] = error.code
            else:
                from modules.history_diagnostics import HistoryError
                if isinstance(error, HistoryError):
                    stage = error.diagnostics.get('stage')
                    status = error.diagnostics.get('http_status')
                    if stage == 'provider_request' and status in (401, 403):
                        history_loading['reason'] = 'public_authentication_failure'
                    elif stage == 'provider_request' and status == 429:
                        history_loading['reason'] = 'public_rate_limit'
                    elif stage == 'provider_request':
                        history_loading['reason'] = 'public_history_request_failed'
                    elif stage in ('provider_schema', 'normalization'):
                        history_loading['reason'] = 'public_history_schema_or_empty'
                    elif stage in ('ohlc_validation', 'coverage_validation'):
                        history_loading['reason'] = 'public_history_validation_failed'
            caveats.append('Completed daily history unavailable; missing classifier evidence stays unknown.')
        try:
            with timing_stage('research_calculations'):
                result = run_latest_market(request.symbol, as_of=now.isoformat(),
                    read_snapshot=lambda symbol, as_of: record, history=history,
                    research_mode=request.research_mode,
                    expiration=request.expiration.isoformat() if request.expiration else None,
                    available_capital=request.available_capital, objective=request.objective, width=request.width, json_ready=False)
        except ArchiveExpirationUnavailable:
            raise APIError('archive_expiration_unavailable', 422) from None
        except (ValueError, TypeError, KeyError, OverflowError):
            raise APIError('archive_research_unavailable', 422) from None
        result['research_session']['diagnostics']['history_loading'] = history_loading
        result['research_mode'] = request.research_mode
        if request.research_mode == 'historical':
            caveats.append('Historical archive research at the observation timestamp; candidates are not current trading opportunities or executable quotes.')
        return envelope(request, result, 'Verified Supabase archive; completed Public daily history when available', caveats, json_ready=json_ready)

    @staticmethod
    def _structure(request):
        trade = request.model_dump(mode='json', exclude={'as_of'})
        trade.update(shares=0, source='Explicit user-supplied scenario',
            pricing_assumption='Supplied signed package cashflow; not a verified quote or fill')
        try:
            return research_position(trade, symbol=request.symbol, spot=request.spot, as_of=request.as_of.isoformat())
        except (ValueError, TypeError, KeyError, OverflowError):
            raise APIError('invalid_structure', 422) from None

    def structure(self, request):
        research = self._structure(request)
        research['historical_economics'] = structure_historical_economics(research,
            as_of=request.as_of.isoformat(), now=self.clock(),
            read_snapshot=self.read_snapshot, history_loader=self.history_loader)
        return envelope(request, research, 'Explicit user-supplied scenario')

    def compare(self, request):
        researched = [self._structure(item) for item in request.structures]
        historical = compare_historical_economics(researched,
            as_of_dates=[item.as_of.isoformat() for item in request.structures], now=self.clock(),
            read_snapshot=self.read_snapshot, history_loader=self.history_loader)
        return envelope(request, dict(candidates=researched, historical_comparison=historical,
            comparison=compare_strategy_research(researched, thesis=request.thesis)),
            'Explicit user-supplied scenarios', ['Input order is not preference. Different dates, symbols and spots remain explicit per candidate.'])


def register_research2(router, service, respond):
    @router.post('/research/market', operation_id='run_market_v2')
    async def run_market(request: MarketRequest, http_request: HTTPRequest):
        # FastAPI has consumed/validated the body before this handler. Polling
        # here cannot race the body consumer. Python cannot kill a blocking SDK
        # call; checkpoints stop subsequent work as soon as that call returns.
        from modules.research_control import cancellable_research
        with cancellable_research() as cancelled:
            work = asyncio.create_task(to_thread.run_sync(
                lambda: respond(service().run(request, json_ready=False)), abandon_on_cancel=True))
            try:
                while not work.done():
                    if await http_request.is_disconnected():
                        cancelled.set()
                        work.cancel()
                        # The client is gone. A quiet non-success response also
                        # prevents BaseHTTPMiddleware mistaking cancellation for
                        # a "no response returned" internal server error.
                        http_request.state.research_error = 'client_disconnected'
                        return Response(status_code=499)
                    await asyncio.sleep(.025)
                return await work
            finally:
                cancelled.set()
                if not work.done():
                    work.cancel()

    @router.post('/research/structure', operation_id='research_structure_v2')
    def research_structure(request: StructureRequest):
        return respond(service().structure(request))

    @router.post('/research/structures/compare', operation_id='compare_structures_v2')
    def compare_structures(request: StructuresRequest):
        return respond(service().compare(request))
