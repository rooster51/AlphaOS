"""Additive authenticated REST routes; reuse the existing API router and sanitizer."""
from datetime import date
from typing import Literal
from fastapi import Query
from .contracts import TradeRequest
from .phase9 import UnifiedResearch
from .phase9_contracts import SymbolResearchResponse, UnifiedTradeResponse
from modules.unified_trade import build_unified_trade


def register_phase9(router, get_service, respond):
    @router.get('/research/{symbol}/run',response_model=SymbolResearchResponse,operation_id='run_symbol_research')
    def run_symbol(symbol:str,horizon:int=3,mode:Literal['run','overview','find']='run',
            strategy:Literal['pcs','ccs','both']='both',expiration:date|None=None,
            dte_min:int=Query(1,ge=0,le=180),dte_max:int=Query(7,ge=0,le=180),
            maximum_candidates:int=Query(4,ge=1,le=10),minimum_credit:float=Query(.05,ge=0,allow_inf_nan=False),
            wing_width:float|None=Query(None,gt=0,le=100,allow_inf_nan=False),refresh:bool=False):
        return respond(UnifiedResearch(get_service()).run(symbol,horizon,mode,strategy,expiration,dte_min,dte_max,
            maximum_candidates,minimum_credit,wing_width,refresh))

    @router.get('/research/candidates/{candidate_id}',response_model=UnifiedTradeResponse,operation_id='unified_candidate_research')
    def candidate(candidate_id:str,include_advanced:bool=False):
        return respond(UnifiedResearch(get_service()).candidate(candidate_id,include_advanced))

    @router.get('/research/{symbol}/vertical',response_model=UnifiedTradeResponse,operation_id='unified_vertical_research')
    def vertical(symbol:str,expiration:date,option_type:Literal['put','call'],short_strike:float=Query(gt=0,allow_inf_nan=False),
            long_strike:float=Query(gt=0,allow_inf_nan=False),horizon:int=3,refresh:bool=False,include_advanced:bool=False):
        return respond(UnifiedResearch(get_service()).vertical(symbol,expiration,option_type,short_strike,long_strike,horizon,refresh,include_advanced))

    @router.post('/research/trade',response_model=UnifiedTradeResponse,operation_id='unified_explicit_trade_research')
    def explicit(trade:TradeRequest,include_advanced:bool=False):
        service=get_service();t=service.manual_trade(trade);bundle=service.snapshot(trade.symbol,trade.horizon,trade.spot)
        friction={k:getattr(trade,k) for k in ('commission_per_contract','entry_slippage','terminal_friction')}
        result=service.research(bundle,t,trade.method,**friction)
        return respond(build_unified_trade(result,include_advanced=include_advanced))
