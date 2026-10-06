"""Environment-only adapter to the SAME provider functions used by Streamlit."""
from modules import public_provider as shared
from modules.market_state_research import build_research_dataset

class MarketProvider:
    def quote(self,symbol):
        return shared.get_public_quotes((symbol,))
    def expirations(self,symbol):
        return shared.get_public_option_expirations(symbol)
    def chain(self,symbol,expiration):
        return shared.get_public_option_chain(symbol,expiration)
    def history(self,symbol,as_of):
        bars=shared.get_public_research_bars(symbol,'FIVE_YEARS').copy()
        bars['symbol']=symbol
        return build_research_dataset(bars,as_of,dict(source='Public regular-market ONE_DAY OHLC',
            requested_period='FIVE_YEARS',provider_diagnostics=bars.attrs.get('provider_diagnostics',{}),
            completion_policy='Exclude today and later using America/New_York; daily timestamps use UTC dates.'))
