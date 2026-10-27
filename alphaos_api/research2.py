"""Read-only interface orchestration; research stays in the AlphaOS modules."""
from datetime import date, datetime, timezone
from copy import deepcopy
from math import isfinite
import os
from typing import Literal
import asyncio
from anyio import to_thread
from fastapi import Request as HTTPRequest
from starlette.responses import Response

from pydantic import BaseModel, ConfigDict, Field, model_validator
from modules.position_research import research_position
from modules.market_archive_adapter import ArchiveExpirationUnavailable
from modules.strategy_compare import compare_strategy_research
from modules.run_market import run_latest_market
from modules.structure_economics import structure_historical_economics, compare_historical_economics
from modules.supabase_archive import research_archive_client as archive_client, read_latest_option_snapshot, ArchiveUnavailable
from .contracts import APIError
from modules.research_timing import execution, stage as timing_stage
from modules.structure_provenance import resolve_structure, hypothetical_evidence, ProvenanceError

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


class ObservationRequest(Request):
    symbol: Literal['QQQ', 'SPY']
    research_mode: Literal['current', 'historical'] = 'current'
    expiration: date | None = None


class ObservationResponse(BaseModel):
    schema_version: Literal['alphaos-observation-v1']
    read_only: Literal[True]
    verified_for_trading: Literal[False]
    research_performed: Literal[False]
    evidence_scope: Literal['archive_observation_only']
    symbol: Literal['SPY','QQQ']
    research_mode: Literal['current','historical']
    as_of: datetime
    requested_as_of: datetime
    expiration: date
    spot: float = Field(gt=0,allow_inf_nan=False)
    session: dict[str,str]
    archive: dict
    request: ObservationRequest
    caveats: list[str]


class StructureLeg(Request):
    type: Literal['Call', 'Put']
    strike: float = Field(gt=0)
    qty: int = Field(ge=-100, le=100, strict=True)
    contract: str | None = Field(default=None, pattern=r'^[A-Z]{1,6}\s*\d{6}[CP]\d{8}$', max_length=32)


class ArchiveReference(Request):
    snapshot_id: str = Field(min_length=1, max_length=128)
    archive_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class StructureRequest(Request):
    symbol: Literal['QQQ', 'SPY']
    expiration: date
    as_of: date
    spot: float = Field(gt=0)
    credit: float  # signed package cashflow per share, debit negative
    fees: float = Field(default=0, ge=0)
    legs: list[StructureLeg] = Field(min_length=1, max_length=4)
    market_data: ArchiveReference | None = None

    @model_validator(mode='after')
    def evidence_mode(self):
        if self.market_data is None and any(leg.contract is not None for leg in self.legs):
            raise ValueError('Contract identities require an archive reference.')
        if self.market_data is not None and any(not leg.contract for leg in self.legs):
            raise ValueError('Every archive-backed leg requires a contract identity.')
        if any(leg.qty == 0 for leg in self.legs):
            raise ValueError('Leg quantities must be nonzero.')
        return self


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
    value = dict(schema_version=VERSION, request=request.model_dump(mode='json',
        exclude_none=isinstance(request, (StructureRequest, StructuresRequest))),
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
        with timing_stage('history_adapter_import'):
            from modules.public_provider import get_public_research_bars
        bars = get_public_research_bars(symbol, 'FIVE_YEARS').copy()
        bars['symbol'] = symbol
        return bars

    def run(self, request, *, json_ready=True):
        with execution(request.symbol, request.research_mode):
            return self._run(request, json_ready=json_ready)

    def observe(self, request, *, json_ready=True):
        from modules.archive_observation import archive_observation
        with execution(request.symbol, request.research_mode):
            now = self.clock()
            try:
                with timing_stage('archive_read'):
                    record = self.read_snapshot(request.symbol, now.isoformat(), **(
                        {'research_mode':'historical'} if request.research_mode == 'historical' else {}))
            except ArchiveUnavailable as error:
                raise APIError(error.code,503) from None
            except Exception:
                raise APIError('archive_unavailable',503) from None
            try:
                with timing_stage('observation_projection'):
                    result = archive_observation(record, symbol=request.symbol, now=now,
                        mode=request.research_mode, expiration=request.expiration.isoformat() if request.expiration else None)
            except ArchiveExpirationUnavailable:
                raise APIError('archive_expiration_unavailable',422) from None
            except (ValueError,TypeError,KeyError,OverflowError):
                raise APIError('archive_research_unavailable',422) from None
            result['request'] = request.model_dump(mode='json')
            return json_safe(result) if json_ready else result

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

    def _structure(self, request, *, now=None, records=None):
        trade = request.model_dump(mode='json', exclude={'as_of', 'market_data'}, exclude_none=True)
        trade.update(shares=0, source='Explicit user-supplied scenario',
            pricing_assumption='Supplied signed package cashflow; not a verified quote or fill')
        evidence = hypothetical_evidence()
        if request.market_data is not None:
            now = now or self.clock()
            records = {} if records is None else records
            try:
                if request.symbol not in records:
                    records[request.symbol] = self.read_snapshot(request.symbol, now.isoformat())
                trade['legs'], evidence = resolve_structure(request, records[request.symbol], now)
            except ArchiveUnavailable as error:
                raise APIError(error.code, 503) from None
            except ProvenanceError as error:
                raise APIError(error.code, 422) from None
            except ArchiveExpirationUnavailable:
                raise APIError('archive_expiration_unavailable', 422) from None
            except Exception:
                raise APIError('market_data_unavailable', 503) from None
            trade.update(source='Verified Supabase archive',
                pricing_assumption='Observed buy ask / sell bid; user-supplied fees; not an executable fill')
        try:
            research = research_position(trade, symbol=request.symbol, spot=request.spot, as_of=request.as_of.isoformat())
        except (ValueError, TypeError, KeyError, OverflowError):
            raise APIError('invalid_structure', 422) from None
        research['evidence']['market_data'] = evidence
        research['evidence']['pricing_assumption'] = trade['pricing_assumption']
        if request.market_data is not None:
            # The outright-option adapter creates its own payoff trade. Preserve
            # the canonical quote-bearing identity there too, without repricing.
            research['payoff']['trade'] = deepcopy(research['trade'])
        return research

    def structure(self, request):
        now = self.clock()
        research = self._structure(request, now=now)
        research['historical_economics'] = structure_historical_economics(research,
            as_of=request.as_of.isoformat(), now=now,
            read_snapshot=self.read_snapshot, history_loader=self.history_loader)
        return envelope(request, research, 'Verified Supabase archive' if request.market_data else 'Explicit user-supplied scenario')

    def compare(self, request):
        now, records = self.clock(), {}
        researched = [self._structure(item, now=now, records=records) for item in request.structures]
        historical = compare_historical_economics(researched,
            as_of_dates=[item.as_of.isoformat() for item in request.structures], now=now,
            read_snapshot=self.read_snapshot, history_loader=self.history_loader)
        return envelope(request, dict(candidates=researched, historical_comparison=historical,
            comparison=compare_strategy_research(researched, thesis=request.thesis)),
            'Per-candidate verified archive or hypothetical provenance' if any(item.market_data for item in request.structures)
            else 'Explicit user-supplied scenarios',
            ['Input order is not preference. Different dates, symbols and spots remain explicit per candidate.'])


def register_research2(router, service, respond):
    @router.post('/research/market', operation_id='run_market_v2')
    async def run_market(request: MarketRequest, http_request: HTTPRequest):
        return await run_cancellable(lambda: service().run(request,json_ready=False),http_request)

    @router.post('/research/observation', operation_id='get_archive_observation_v1',response_model=ObservationResponse)
    async def observe_market(request: ObservationRequest, http_request: HTTPRequest):
        return await run_cancellable(lambda: service().observe(request,json_ready=False),http_request)

    async def run_cancellable(calculate, http_request):
        # FastAPI has consumed/validated the body before this handler. Polling
        # here cannot race the body consumer. Python cannot kill a blocking SDK
        # call; checkpoints stop subsequent work as soon as that call returns.
        from modules.research_control import cancellable_research
        with cancellable_research() as cancelled:
            work = asyncio.create_task(to_thread.run_sync(
                lambda: respond(calculate()), abandon_on_cancel=True))
            try:
                while not work.done():
                    if cancelled.is_set() or await http_request.is_disconnected():
                        cancelled.set()
                        work.cancel()
                        # The client is gone. A quiet non-success response also
                        # prevents BaseHTTPMiddleware mistaking cancellation for
                        # a "no response returned" internal server error.
                        http_request.state.research_error = 'client_disconnected'
                        return Response(status_code=499)
                    await asyncio.sleep(.025)
                if cancelled.is_set():
                    http_request.state.research_error = 'client_disconnected'
                    return Response(status_code=499)
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
