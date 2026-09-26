"""HTTP validation, stable errors and a finite JSON response contract."""
from datetime import date
from typing import Literal
from pydantic import BaseModel,Field,ConfigDict

SCHEMA_VERSION='alphaos-research-v1'
CAVEATS=[
 'Historical analog frequencies are descriptive, not calibrated forecast probabilities.',
 'Scenario EV is historical scenario economics, not guaranteed expectancy or fair value.',
 'Daily OHLC cannot reconstruct exact intraday paths or assignment/execution.',
 'Analog observations may overlap; non-overlap is a dependence diagnostic.',
 'Support/resistance zones are descriptive price structure, not hard barriers.',
 'Current quotes and completed-session research are distinct dated observations.',
 'Provider adjustment and exchange-calendar completeness may be unverified.'
]

class APIError(Exception):
    def __init__(self,code,status=422): self.code,self.status=code,status

class Leg(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    type: Literal['Put','Call']
    strike: float=Field(gt=0)
    qty: Literal[-1,1]

class TradeRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    symbol: str=Field(max_length=5)
    expiration: date
    spot: float=Field(gt=0)
    credit: float=Field(gt=0)
    legs: list[Leg]=Field(min_length=2,max_length=2)
    horizon: int=3
    method: Literal['tolerance','nearest']='tolerance'
    commission_per_contract: float=Field(default=0,ge=0,le=100)
    entry_slippage: float=Field(default=0,ge=0,le=10000)
    terminal_friction: float=Field(default=0,ge=0,le=10000)

class CompareRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    research_trade: TradeRequest
    candidates: list[TradeRequest]=Field(min_length=1,max_length=20)

class ResponseMeta(BaseModel):
    schema_version: str
    generated_at: str
    source: str
    symbol: str
    research_session: str | None
    research_close: float | None
    quote_as_of: str | None
    current_spot: float | None
    quote_freshness: dict | None = None
    observed_session_horizon: int | None
    snapshot_id: str | None

class ResearchResponse(BaseModel):
    meta: ResponseMeta
    evidence: dict
    caveats: list[str]

class ErrorResponse(BaseModel):
    error: dict
    schema_version: str
