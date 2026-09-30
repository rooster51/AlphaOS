"""Verified research instruments. Provider identities are exact, never ETF proxies."""
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class Instrument:
    canonical_symbol: str
    asset_type: str
    provider_type: str
    provider_response_symbol: str
    option_roots: tuple[str,...]
    default_wing_width: float
    exercise_style: str
    settlement: str
    contract_multiplier: int = 100
    timezone: str = 'America/New_York'
    research_proxy_used: bool = False
    supports_0dte: bool = True
    @property
    def underlying_bid_ask_expected(self):return self.asset_type!='index'
    @property
    def provider_request_symbol(self):return self.canonical_symbol

REGISTRY = {
    'SPY':Instrument('SPY','ETF','EQUITY','SPY',('SPY',),1,'American','physical'),
    'QQQ':Instrument('QQQ','ETF','EQUITY','QQQ',('QQQ',),1,'American','physical'),
    'SPX':Instrument('SPX','index','INDEX','SPX-INDEX',('SPXW',),5,'European','cash; accepted SPXW series PM per exchange specifications'),
    'XSP':Instrument('XSP','index','INDEX','XSP-INDEX',('XSP',),1,'European','cash; PM'),
}
SYMBOLS=tuple(REGISTRY)

def instrument(symbol):
    return REGISTRY[symbol.strip().upper()]

def metadata(symbol):
    spec=instrument(symbol)
    return dict(**asdict(spec),underlying_bid_ask_expected=spec.underlying_bid_ask_expected,provider_settlement_metadata_verified=False,provider_quote_symbol=spec.canonical_symbol,
        provider_history_symbol=spec.canonical_symbol,provider_options_symbol=spec.canonical_symbol,
        history_basis='Direct target-index OHLC' if spec.asset_type=='index' else 'Direct ETF OHLC',
        settlement_caveat='Public quote/chain responses do not verify settlement timing. Exercise/settlement descriptions are exchange specifications, not per-contract provider metadata. Daily terminal-price scenarios are not official settlement-value backtests.')
