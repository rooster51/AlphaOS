"""Read-only Public provider for scheduled research; no Streamlit or orders."""
import os
from datetime import datetime, timezone
from modules.public_history import fetch_research_bars
from modules.public_session import _select_account


class ProviderUnavailable(RuntimeError):
    """Messages are fixed public diagnostics, never interpolated SDK errors."""


class DailyPublicProvider:
    name = 'Public'

    def __init__(self, client, account_id):
        self.client, self.account_id = client, account_id

    @classmethod
    def from_environment(cls):
        secret = os.environ.get('PUBLIC_API_SECRET')
        if not secret:
            raise ProviderUnavailable('PUBLIC_API_SECRET is not configured.')
        try:
            from public_api_sdk import ApiKeyAuthConfig, PublicApiClient
            client = PublicApiClient(ApiKeyAuthConfig(api_secret_key=secret,validity_minutes=60))
            accounts = client.get_accounts().accounts
            if not accounts:
                raise ValueError
            account = _select_account(accounts,os.environ.get('PUBLIC_ACCOUNT_NUMBER'))
            return cls(client,account.account_id)
        except Exception:
            raise ProviderUnavailable('Public authentication/account selection failed. Check repository secrets and market-data access.') from None

    def history(self, symbol, period, as_of):
        return fetch_research_bars(self.client,symbol,period,as_of=as_of)

    def _marketdata(self, endpoint, body):
        # Identical authenticated read-only market-data POSTs used by the SDK.
        # Inspect per-contract raw fields so one malformed quote cannot cause
        # the SDK's whole-chain model to discard every observation.
        try:
            self.client.auth_manager.refresh_token_if_needed()
            data = self.client.api_client.post(
                f'/userapigateway/marketdata/{self.account_id}/{endpoint}',json_data=body)
            if not isinstance(data,dict):
                raise ValueError
            return data
        except Exception:
            raise ProviderUnavailable('Public market-data retrieval failed; no raw provider error was recorded.') from None

    def underlying(self, symbol):
        raw = self._marketdata('quotes',{'instruments':[{'symbol':symbol,'type':'EQUITY'}]})
        quotes = raw.get('quotes')
        if not isinstance(quotes,list) or len(quotes)!=1 or not isinstance(quotes[0],dict):
            raise ProviderUnavailable('Unexpected Public underlying quote response.')
        return quotes[0]

    def expirations(self, symbol):
        raw = self._marketdata('option-expirations',{'instrument':{'symbol':symbol,'type':'EQUITY'}})
        if raw.get('baseSymbol')!=symbol or not isinstance(raw.get('expirations'),list):
            raise ProviderUnavailable('Unexpected Public expiration response.')
        return raw['expirations']

    def chain(self, symbol, expiration):
        raw = self._marketdata('option-chain',{'instrument':{'symbol':symbol,'type':'EQUITY'},'expirationDate':expiration})
        if raw.get('baseSymbol')!=symbol or not all(isinstance(raw.get(k),list) for k in ('calls','puts')):
            raise ProviderUnavailable('Unexpected Public option-chain envelope.')
        return {'calls':raw['calls'],'puts':raw['puts']}

    @staticmethod
    def now():
        return datetime.now(timezone.utc)
