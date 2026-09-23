"""Read-only HTTP surface for AlphaOS research.

Phase 7 deliberately keeps HTTP concerns separate from Streamlit. Research
calculations continue to live in modules/ and are imported here so there is
one quantitative engine, not a second implementation.
"""
from datetime import date, datetime\nfrom math import isfinite\nfrom zoneinfo import ZoneInfo
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from modules.market_state_research import load_market_state
from modules.selector_research import context_from_dataset
from modules.price_structure import nearest_levels
from modules.phase6_research import research_workspace, compare_candidates, chain_verticals

API_VERSION = "phase7-research-api-v1"
SUPPORTED_SYMBOLS = {"SPY", "QQQ"}
SUPPORTED_HORIZONS = {1, 2, 3, 5, 10}

app = FastAPI(
    title="AlphaOS Research API",
    version=API_VERSION,
    description="Read-only descriptive market and options research. No order execution or trade recommendations.",
)


def _symbol(value: str) -> str:
    value = value.upper().strip()
    if value not in SUPPORTED_SYMBOLS:
        raise HTTPException(400, "symbol must be SPY or QQQ")
    return value


def _snapshot(symbol: str, spot: float | None, horizon: int):
    if horizon not in SUPPORTED_HORIZONS:
        raise HTTPException(400, "horizon must be one of 1, 2, 3, 5, 10 observed sessions")
    try:
        dataset = load_market_state(_symbol(symbol), "FIVE_YEARS")
        research_close = float(dataset["features"].close.iloc[-1])
        anchor = research_close if spot is None else float(spot)
        if anchor <= 0:
            raise HTTPException(400, "spot must be positive")
        return context_from_dataset(dataset, anchor, horizon, "API explicit spot" if spot is not None else "Completed research close", dataset["metadata"].get("data_read_at", "Unavailable"))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, f"research dataset unavailable: {exc}") from exc


def _meta(snapshot):
    return {
        "api_version": API_VERSION,
        "symbol": snapshot["dataset"]["metadata"]["symbol"],
        "research_date": snapshot["research_date"],
        "research_close": snapshot["research_close"],
        "current_spot": snapshot["current_spot"],
        "quote_timestamp": snapshot["quote_timestamp"],
        "retrieved_at": snapshot["scan_retrieved_at"],
        "observed_session_horizon": snapshot["horizon"],
        "snapshot_id": snapshot["snapshot_id"],
        "disclaimer": "Historical analog frequencies and scenario economics are descriptive research, not calibrated forecast probabilities or recommendations.",
    }


class Leg(BaseModel):
    type: Literal["Put", "Call"]
    strike: float = Field(gt=0)
    qty: int


class TradeRequest(BaseModel):
    symbol: str
    expiration: date
    spot: float = Field(gt=0)
    credit: float = Field(gt=0)
    legs: list[Leg]
    horizon: int = 3
    method: Literal["tolerance", "nearest"] = "tolerance"
    commission_per_contract: float = Field(default=0, ge=0)
    entry_slippage: float = Field(default=0, ge=0)
    terminal_friction: float = Field(default=0, ge=0)


class CompareRequest(BaseModel):
    research_trade: TradeRequest
    candidates: list[TradeRequest] = Field(min_length=1, max_length=50)


def _trade(req: TradeRequest):
    symbol = _symbol(req.symbol)
    return {
        "symbol": symbol,
        "strategy": "Vertical credit spread",
        "expiration": req.expiration.isoformat(),
        "spot": req.spot,
        "stock_basis": req.spot,
        "shares": 0,
        "fees": 0,
        "credit": req.credit,
        "source": "AlphaOS Research API explicit input",
        "legs": [leg.model_dump() for leg in req.legs],
    }


@app.get("/health")
def health():
    return {"status": "ok", "api_version": API_VERSION, "read_only": True}


@app.get("/v1/market/{symbol}")
def market_snapshot(symbol: str, horizon: int = Query(3), spot: float | None = Query(None, gt=0)):
    s = _snapshot(symbol, spot, horizon)
    target = s["analog"]["target"]
    return jsonable_encoder({
        "meta": _meta(s),
        "market_state": target,
        "analog_config": s["analog"]["config"],
        "analog_n": len(s["analog"]["sample"]),
    })


@app.get("/v1/quote/{symbol}")
def live_quote(symbol: str):
    from modules.public_data import get_public_quotes
    symbol = _symbol(symbol)
    try:
        rows = get_public_quotes((symbol,))
        quote = next((q for q in rows if q["symbol"] == symbol), None)
        if not quote:
            raise HTTPException(503, "Public quote unavailable")
        return jsonable_encoder({"api_version": API_VERSION, "source": "Public", "quote": quote})
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, f"Public quote unavailable: {exc}") from exc


@app.get("/v1/options/{symbol}/expirations")
def option_expirations(symbol: str):
    from modules.public_data import get_public_option_expirations
    symbol = _symbol(symbol)
    try:
        return {"api_version": API_VERSION, "source": "Public", "symbol": symbol, "expirations": get_public_option_expirations(symbol)}
    except Exception as exc:
        raise HTTPException(503, f"Public expirations unavailable: {exc}") from exc


@app.get("/v1/options/{symbol}/chain/{expiration}")
def option_chain(symbol: str, expiration: date):
    from modules.public_data import get_public_option_chain
    symbol = _symbol(symbol)
    try:
        chain = get_public_option_chain(symbol, expiration.isoformat())
        return jsonable_encoder({"api_version": API_VERSION, "source": "Public", "retrieved_at": datetime.now(ZoneInfo("America/New_York")).isoformat(), "chain": chain})
    except Exception as exc:
        raise HTTPException(503, f"Public option chain unavailable: {exc}") from exc


@app.get("/v1/structure/{symbol}")
def price_structure(symbol: str, horizon: int = Query(3), spot: float | None = Query(None, gt=0), levels: int = Query(3, ge=1, le=10)):
    s = _snapshot(symbol, spot, horizon)
    zones = nearest_levels(s["structure"], levels)
    return jsonable_encoder({"meta": _meta(s), "atr": s["structure"]["atr"], "levels": zones.to_dict("records")})


@app.get("/v1/distribution/{symbol}")
def forward_distribution(symbol: str, horizon: int = Query(3), spot: float | None = Query(None, gt=0)):
    from modules.forward_distribution import summarize_forward_distribution
    s = _snapshot(symbol, spot, horizon)
    result = summarize_forward_distribution(s["analog"], horizon, s["current_spot"])
    return jsonable_encoder({"meta": _meta(s), "distribution": result})


def _run(req: TradeRequest):
    if req.horizon not in SUPPORTED_HORIZONS:
        raise HTTPException(400, "horizon must be one of 1, 2, 3, 5, 10 observed sessions")
    trade = _trade(req)
    s = _snapshot(req.symbol, req.spot, req.horizon)
    dataset = s["dataset"]
    bars = dataset["features"][["date", "symbol", "open", "high", "low", "close"]]
    try:
        result = research_workspace(
            bars, trade, date.today(), req.horizon, req.method, dataset["metadata"],
            prepared=s,
            commission_per_contract=req.commission_per_contract,
            entry_slippage=req.entry_slippage,
            terminal_friction=req.terminal_friction,
        )
        return s, result
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/v1/trade/research")
def research_trade(req: TradeRequest):
    s, result = _run(req)
    e = result["evidence"]
    return jsonable_encoder({
        "meta": _meta(s),
        "context": e["context"],
        "threshold": e["threshold"]["summary"],
        "threshold_non_overlapping": e["threshold"]["non_overlapping_summary"],
        "economics": e["economics"]["net_summary"],
        "economics_non_overlapping": e["economics"]["non_overlapping_net_summary"],
        "robustness": result["robustness"].to_dict("records"),
        "levels": result["levels"].to_dict("records"),
        "provenance": result["provenance"],
    })


@app.post("/v1/trade/compare")
def compare_trades(req: CompareRequest):
    s, research = _run(req.research_trade)
    trades = [_trade(c) for c in req.candidates]
    try:
        compared = compare_candidates(trades, research, date.today(),
            commission_per_contract=req.research_trade.commission_per_contract,
            entry_slippage=req.research_trade.entry_slippage,
            terminal_friction=req.research_trade.terminal_friction)
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return jsonable_encoder({
        "meta": _meta(s),
        "candidates": compared["candidates"].to_dict("records"),
        "rejected": compared["rejected"].to_dict("records"),
        "note": "Rows preserve input order. AlphaOS does not rank or auto-select a trade.",
    })


@app.get("/v1/options/{symbol}/vertical")
def research_live_vertical(symbol: str, expiration: date, short_strike: float = Query(gt=0), long_strike: float = Query(gt=0), option_type: Literal["put", "call"] = Query(), horizon: int = Query(3)):
    """Fetch Public quotes for exact legs, use natural credit, then run AlphaOS research."""
    from modules.public_data import get_public_option_chain, get_public_quotes
    symbol = _symbol(symbol)
    if horizon not in SUPPORTED_HORIZONS:
        raise HTTPException(400, "horizon must be one of 1, 2, 3, 5, 10 observed sessions")
    try:
        quotes = get_public_quotes((symbol,))
        quote = next((q for q in quotes if q["symbol"] == symbol), None)
        if not quote or not quote.get("last") or not isfinite(quote["last"]):
            raise HTTPException(503, "Underlying Public quote unavailable")
        chain = get_public_option_chain(symbol, expiration.isoformat())
        side = chain["puts"] if option_type == "put" else chain["calls"]
        short = next((x for x in side if float(x["strike"]) == short_strike), None)
        long = next((x for x in side if float(x["strike"]) == long_strike), None)
        if not short or not long:
            raise HTTPException(404, "Requested option leg is not present in the Public chain")
        if short.get("bid") is None or long.get("ask") is None:
            raise HTTPException(422, "Natural executable-side quote is incomplete")
        credit = float(short["bid"]) - float(long["ask"])
        if credit <= 0:
            raise HTTPException(422, "Natural short-bid minus long-ask credit is not positive")
        req = TradeRequest(symbol=symbol, expiration=expiration, spot=float(quote["last"]), credit=credit, horizon=horizon,
            legs=[Leg(type="Put" if option_type == "put" else "Call", strike=short_strike, qty=-1), Leg(type="Put" if option_type == "put" else "Call", strike=long_strike, qty=1)])
        s, result = _run(req)
        e = result["evidence"]
        return jsonable_encoder({"meta": {**_meta(s), "source": "Public", "underlying_quote": quote, "pricing": "short bid minus long ask; hypothetical natural fill", "short_contract": short, "long_contract": long},
            "context": e["context"], "threshold": e["threshold"]["summary"], "economics": e["economics"]["net_summary"], "robustness": result["robustness"].to_dict("records"), "levels": result["levels"].to_dict("records")})
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, f"Public vertical research unavailable: {exc}") from exc
