"""Read-only interface orchestration; research stays in the AlphaOS modules."""
from datetime import date, datetime, timezone
from math import isfinite
import os
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from modules.position_research import research_position
from modules.strategy_compare import compare_strategy_research
from modules.run_market import run_latest_market
from modules.structure_economics import structure_historical_economics, compare_historical_economics
from modules.supabase_archive import archive_client, read_latest_option_snapshot, ArchiveUnavailable
from .contracts import APIError

VERSION = 'alphaos-interface-v2'


class Request(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class MarketRequest(Request):
    symbol: Literal['QQQ', 'SPY']
    expiration: date | None = None
    available_capital: float | None = Field(default=None, ge=0)
    objective: str | None = Field(default=None, max_length=1000)
    width: float = Field(default=5, gt=0, le=100)


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


def envelope(request, research, source, caveats=()):
    return json_safe(dict(schema_version=VERSION, request=request.model_dump(mode='json'),
        read_only=True, research=research, provenance=dict(source=source), caveats=list(caveats)))


class ArchiveResearchService:
    def __init__(self, *, read_snapshot=None, history_loader=None, clock=None):
        self.read_snapshot = read_snapshot or self._read
        self.history_loader = history_loader or self._history
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _read(symbol, as_of):
        # Lazy trusted server wiring. No connection or secret loading on import.
        # Reader implements ALL selection, checksum, identity and freshness rules.
        try:
            age = float(os.environ.get('ALPHAOS_ARCHIVE_MAX_AGE_SECONDS', '600'))
            if not isfinite(age) or age < 0:
                raise ValueError()
            return read_latest_option_snapshot(archive_client(), symbol, as_of, max_age_seconds=age)
        except Exception:
            raise ArchiveUnavailable('Archive unavailable or invalid configuration.') from None

    @staticmethod
    def _history(symbol):
        # Reuse the historical API provider's daily bars, not a second collector.
        from modules.public_provider import get_public_research_bars
        bars = get_public_research_bars(symbol, 'FIVE_YEARS').copy()
        bars['symbol'] = symbol
        return bars

    def run(self, request):
        history = None
        caveats = ['Archive observations are not executable live quotes.',
            'Capital is expiration max-loss eligibility, not broker buying power or margin.',
            'Objective is recorded context; it does not override evidence or filter strategy routes.',
            'Default width is 5 points. Omitted expiration uses the archive adapter selection.']
        # Load/verify archive FIRST; never fall back to live chain on failure.
        now = self.clock()
        try:
            record = self.read_snapshot(request.symbol, now.isoformat())
        except Exception:
            raise APIError('archive_unavailable', 503) from None
        try:
            history = self.history_loader(request.symbol)
        except Exception:
            caveats.append('Completed daily history unavailable; missing classifier evidence stays unknown.')
        try:
            result = run_latest_market(request.symbol, as_of=now.isoformat(),
                read_snapshot=lambda symbol, as_of: record, history=history,
                expiration=request.expiration.isoformat() if request.expiration else None,
                available_capital=request.available_capital, objective=request.objective, width=request.width)
        except (ValueError, TypeError, KeyError, OverflowError):
            raise APIError('archive_research_unavailable', 422) from None
        return envelope(request, result, 'Verified Supabase archive; completed Public daily history when available', caveats)

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
    def run_market(request: MarketRequest):
        return respond(service().run(request))

    @router.post('/research/structure', operation_id='research_structure_v2')
    def research_structure(request: StructureRequest):
        return respond(service().structure(request))

    @router.post('/research/structures/compare', operation_id='compare_structures_v2')
    def compare_structures(request: StructuresRequest):
        return respond(service().compare(request))
