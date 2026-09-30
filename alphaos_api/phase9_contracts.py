"""Versioned Phase 9 presentation contracts; nested evidence retains engine field names."""
from typing import Literal
from pydantic import BaseModel


class UnifiedTradeResponse(BaseModel):
    schema_version: Literal['alphaos-unified-trade-v1']
    trade_snapshot: dict
    market_structure: dict
    historical_analog_behavior: dict
    historical_scenario_payoff: dict
    advanced_research: dict
    caveats: list[str]


class SymbolResearchResponse(BaseModel):
    instrument: dict | None = None
    schema_version: Literal['alphaos-symbol-research-v1']
    symbol: str
    mode: Literal['run','overview','find']
    status: Literal['complete','partial','data_unavailable','live_research_stopped','context_only']
    stages: list[str]
    live_trade_state: dict | None
    market_snapshot: dict | None
    market_structure: dict | None
    candidate_scan: dict | None
    qualifying_candidates: list[UnifiedTradeResponse]
    errors: list[dict]
    defaults: dict
    presentation: dict
    caveats: list[str]
    stop_reason: str | None = None
