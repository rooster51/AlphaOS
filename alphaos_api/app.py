"""Authenticated read-only HTTP surface over the existing AlphaOS research engine."""
import hmac
import os
from datetime import date
from typing import Literal
from fastapi import FastAPI,APIRouter,Depends,Query
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from fastapi.responses import JSONResponse
from modules.daily_archive import json_value
from modules.price_structure import nearest_levels
from modules.forward_distribution import summarize_forward_distribution
from .contracts import APIError,TradeRequest,CompareRequest,ResearchResponse,ErrorResponse,SCHEMA_VERSION
from .service import ResearchService,symbol_value,horizon_value

app=FastAPI(title='AlphaOS Research API',version=SCHEMA_VERSION,debug=False,
    description='Read-only descriptive research using the same AlphaOS engine as Streamlit. No order execution or recommendations.')
app.state.service=ResearchService()
security=HTTPBearer(auto_error=False)


def authenticate(credentials:HTTPAuthorizationCredentials|None=Depends(security)):
    expected=os.environ.get('ALPHAOS_API_TOKEN')
    if not expected:raise APIError('api_not_configured',503)
    if credentials is None:raise APIError('authentication_required',401)
    if not hmac.compare_digest(credentials.credentials.encode(),expected.encode()):raise APIError('forbidden',403)


router=APIRouter(prefix='/v1',dependencies=[Depends(authenticate)],responses={
    status:{'model':ErrorResponse} for status in (400,401,403,404,409,410,422,429,500,503)})


def sanitized(value):
    secrets=[os.environ.get(k) for k in ('PUBLIC_API_SECRET','PUBLIC_ACCOUNT_NUMBER','ALPHAOS_API_TOKEN')]
    def clean(item):
        if isinstance(item,dict):
            return {k:clean(v) for k,v in item.items() if not any(word in k.lower() for word in ('account_id','account_number','secret','token','authorization','password'))}
        if isinstance(item,list):return [clean(v) for v in item]
        if isinstance(item,str):
            for secret in secrets:
                if secret:item=item.replace(secret,'[REDACTED]')
        return item
    return clean(json_value(value))


def respond(value):return JSONResponse(sanitized(value))


def error_response(code,status):
    return JSONResponse({'error':{'code':code,'message':code.replace('_',' ').capitalize()},'schema_version':SCHEMA_VERSION},
        status_code=status,headers={'WWW-Authenticate':'Bearer'} if status==401 else None)


@app.exception_handler(APIError)
async def api_error(request,exc):return error_response(exc.code,exc.status)


@app.exception_handler(RequestValidationError)
async def invalid_request(request,exc):
    # Never reflect request values, headers, or Pydantic exception strings.
    return error_response('invalid_request',422)


@app.exception_handler(HTTPException)
async def http_error(request,exc):return error_response('not_found' if exc.status_code==404 else 'http_error',exc.status_code)


@app.middleware('http')
async def safe_boundary(request,call_next):
    try:
        length=request.headers.get('content-length')
        if length and int(length)>131072:return error_response('request_too_large',413)
        response=await call_next(request)
        response.headers['Cache-Control']='no-store'
        return response
    except Exception:
        # Handle at the ASGI boundary so Uvicorn never receives a raw SDK traceback.
        return error_response('internal_error',500)


@app.get('/health')
def health():return {'status':'ok','schema_version':SCHEMA_VERSION,'read_only':True,'authentication_configured':bool(os.environ.get('ALPHAOS_API_TOKEN'))}


@router.get('/market/{symbol}',response_model=ResearchResponse,operation_id='get_market_snapshot')
def market_snapshot(symbol:str,horizon:int=3,spot:float|None=Query(None,gt=0,allow_inf_nan=False),snapshot_id:str|None=None):
    service=app.state.service;s=service.snapshot(symbol,horizon,spot,snapshot_id)
    a=s['prepared']['analog']
    return respond(service.envelope(dict(market_state=a['target'],analog_config=a['config'],analog_N=len(a['analogs']),
        underlying_quote=s['quote'],timing=service.timing(s['quote']['quote'])),s))


@router.get('/structure/{symbol}',response_model=ResearchResponse,operation_id='get_price_structure')
def price_structure(symbol:str,horizon:int=3,spot:float|None=Query(None,gt=0,allow_inf_nan=False),snapshot_id:str|None=None,levels:int=Query(3,ge=1,le=10)):
    service=app.state.service;s=service.snapshot(symbol,horizon,spot,snapshot_id)
    return respond(service.envelope(dict(atr=s['prepared']['structure']['atr'],levels=nearest_levels(s['prepared']['structure'],levels)),s))


@router.get('/distribution/{symbol}',response_model=ResearchResponse,operation_id='get_forward_distribution')
def forward_distribution(symbol:str,horizon:int=3,spot:float|None=Query(None,gt=0,allow_inf_nan=False),snapshot_id:str|None=None):
    service=app.state.service;s=service.snapshot(symbol,horizon,spot,snapshot_id)
    return respond(service.envelope(summarize_forward_distribution(s['prepared']['analog'],horizon,s['prepared']['current_spot']),s))


@router.get('/quote/{symbol}',response_model=ResearchResponse,operation_id='get_live_quote')
def live_quote(symbol:str):
    service=app.state.service;symbol=symbol_value(symbol);q=service.quote(symbol)
    return respond(service.envelope(dict(**q,timing=service.timing(q['quote'])),symbol=symbol,quote=q['quote']))


@router.get('/options/{symbol}/expirations',response_model=ResearchResponse,operation_id='get_option_expirations')
def option_expirations(symbol:str):
    service=app.state.service;symbol=symbol_value(symbol)
    return respond(service.envelope(service.expirations(symbol),symbol=symbol))


@router.get('/options/{symbol}/chain/{expiration}',response_model=ResearchResponse,operation_id='get_option_chain')
def option_chain(symbol:str,expiration:date):
    service=app.state.service;symbol=symbol_value(symbol)
    return respond(service.envelope(service.chain(symbol,expiration),symbol=symbol))


@router.get('/options/{symbol}/vertical',response_model=ResearchResponse,operation_id='research_trade')
def research_live_vertical(symbol:str,expiration:date,option_type:Literal['put','call'],
        short_strike:float=Query(gt=0,allow_inf_nan=False),long_strike:float=Query(gt=0,allow_inf_nan=False),horizon:int=3,refresh:bool=False):
    service=app.state.service
    bundle,trade,quote=service.exact_trade(symbol,expiration,option_type,short_strike,long_strike,horizon,refresh)
    result=service.research(bundle,trade)
    return respond(service.envelope(dict(**service.evidence(result,trade),quotes=quote),bundle))


@router.get('/options/{symbol}/scan',response_model=ResearchResponse,operation_id='scan_credit_spreads')
def scan_credit_spreads(symbol:str,strategy:Literal['pcs','ccs','both']='both',expiration:date|None=None,
        dte_min:int=Query(1,ge=0,le=180),dte_max:int=Query(7,ge=0,le=180),research_horizon:int=3,
        maximum_short_distance:float=Query(.05,gt=0,le=.25,allow_inf_nan=False),minimum_credit:float=Query(.05,ge=0,allow_inf_nan=False),
        maximum_candidates:int=Query(20,ge=1,le=100),wing_width:float=Query(1,gt=0,le=100,allow_inf_nan=False),refresh:bool=False):
    return respond(app.state.service.scan(symbol,strategy,expiration,dte_min,dte_max,research_horizon,
        maximum_short_distance,minimum_credit,maximum_candidates,wing_width,refresh))


@router.get('/candidates/{candidate_id}',response_model=ResearchResponse,operation_id='research_candidate')
def research_candidate(candidate_id:str):return respond(app.state.service.candidate(candidate_id))


def friction(req):return {k:getattr(req,k) for k in ('commission_per_contract','entry_slippage','terminal_friction')}


@router.post('/trade/research',response_model=ResearchResponse,operation_id='research_explicit_trade')
def research_explicit_trade(req:TradeRequest):
    service=app.state.service;trade=service.manual_trade(req);s=service.snapshot(req.symbol,req.horizon,req.spot)
    r=service.research(s,trade,req.method,**friction(req))
    return respond(service.envelope(service.evidence(r,trade),s))


@router.post('/trade/compare',response_model=ResearchResponse,operation_id='compare_trades')
def compare_trades(req:CompareRequest):
    service=app.state.service;primary=service.manual_trade(req.research_trade)
    trades=[service.manual_trade(c) for c in req.candidates]
    for candidate in req.candidates:
        if (symbol_value(candidate.symbol)!=primary['symbol'] or candidate.spot!=primary['spot']
            or candidate.horizon!=req.research_trade.horizon or candidate.method!=req.research_trade.method
            or friction(candidate)!=friction(req.research_trade)):
            raise APIError('comparison_context_mismatch')
    s=service.snapshot(primary['symbol'],req.research_trade.horizon,primary['spot'])
    base=service.research(s,primary,req.research_trade.method,**friction(req.research_trade))
    candidates=[]
    for trade in trades:
        # Each candidate's robustness must be its own payoff, not the primary's.
        r=service.research(s,trade,req.research_trade.method,**friction(req.research_trade))
        candidates.append(service.evidence(r,trade))
    return respond(service.envelope(dict(research_trade=service.evidence(base,primary),candidates=candidates,
        ordering='Input order; no ranking or automatic selection.'),s))


app.include_router(router)
