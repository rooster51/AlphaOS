"""SDK formatting compatibility; fixtures are observations, never trading evidence."""
from copy import deepcopy
from decimal import Decimal
import importlib
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest


@pytest.fixture(params=['modules.public_provider', 'modules.public_data'])
def provider(request):
    return importlib.import_module(request.param)


def quote(symbol='SPY'):
    return NS(instrument=NS(symbol=symbol+'261019C00500000'), bid=Decimal('1.20'), ask='1.40',
              option_details=NS(strike_price='500', mid_price='1.31', greeks=NS(
                  delta='.3', gamma='.01', theta='-.1', vega='.2', rho='.01', implied_volatility='.25')),
              volume=7, open_interest=23, bid_timestamp='2026-10-16T15:00:00Z',
              ask_timestamp='2026-10-16T15:00:01Z')


@pytest.mark.parametrize('symbol', ['SPY', 'QQQ'])
def test_complete_sdk_row_preserves_fields_and_input(provider, symbol):
    q = quote(symbol)
    before = deepcopy(q)
    assert provider._option_quote_row(q, 'Call') == {
        'contract':symbol+'261019C00500000', 'type':'Call', 'strike':500.,
        'bid':1.2, 'ask':1.4, 'mid':1.31, 'delta':.3, 'gamma':.01,
        'theta':-.1, 'vega':.2, 'rho':.01, 'iv':.25, 'volume':7, 'open_interest':23,
        'bid_timestamp':'2026-10-16T15:00:00Z', 'ask_timestamp':'2026-10-16T15:00:01Z',
    }
    assert q == before


@pytest.mark.parametrize('bid,ask,expected', [(1,3,2), (None,3,None), (1,None,None), (3,1,2), (-1,1,0)])
def test_mid_fallback_does_not_validate_or_repair_observations(provider, bid, ask, expected):
    q = quote(); q.bid=bid; q.ask=ask; q.option_details.mid_price=None
    q.option_details.greeks=None
    del q.bid_timestamp; del q.ask_timestamp; del q.open_interest
    row = provider._option_quote_row(q,'Put')
    assert (row['bid'],row['ask'],row['mid']) == (bid,ask,expected)
    assert all(row[key] is None for key in ('delta','gamma','theta','vega','rho','iv','bid_timestamp','ask_timestamp','open_interest'))
    assert row['type']=='Put'  # Side remains the caller's label, as before.


@pytest.mark.parametrize('missing', ['details','strike'])
def test_incomplete_contract_is_omitted(provider, missing):
    q=quote()
    if missing=='details': q.option_details=None
    else: q.option_details.strike_price=None
    assert provider._option_quote_row(q,'Call') is None


@pytest.mark.parametrize('field', ['bid','strike_price','delta'])
def test_malformed_numbers_still_raise_instead_of_disappearing(provider, field):
    q=quote()
    target=q if field=='bid' else q.option_details if field=='strike_price' else q.option_details.greeks
    setattr(target,field,'invalid-observation')
    with pytest.raises(ValueError): provider._option_quote_row(q,'Call')


def test_compatibility_wrapper_keeps_local_conversion_hook(provider, monkeypatch):
    convert=Mock(wraps=provider._as_float)
    monkeypatch.setattr(provider,'_as_float',convert)
    assert provider._option_quote_row(quote(),'Call')['mid']==1.31
    assert convert.call_count==10


@pytest.mark.parametrize('symbol', ['SPY','QQQ'])
def test_chain_request_uses_shared_rows_without_changing_context_or_failures(provider, monkeypatch, symbol):
    client=Mock(); context=Mock(return_value=(client,'fixture-account'))
    monkeypatch.setattr(provider,'_public_context',context)
    good=quote(symbol); missing=quote(symbol); missing.option_details=None
    client.get_option_chain.return_value=NS(base_symbol=symbol,calls=[good,missing],puts=[good])
    # Bypass only the UI cache to inspect its existing request function directly.
    chain=getattr(provider.get_public_option_chain,'__wrapped__',provider.get_public_option_chain)
    result=chain(symbol,'2026-10-19')
    assert result == {'symbol':symbol,'expiration':'2026-10-19',
                      'calls':[provider._option_quote_row(good,'Call')],
                      'puts':[provider._option_quote_row(good,'Put')]}
    context.assert_called_once_with()
    request=client.get_option_chain.call_args.args[0]
    assert request.instrument.symbol==symbol
    assert request.instrument.type.value=='EQUITY'
    assert str(request.expiration_date)=='2026-10-19'
    assert client.get_option_chain.call_args.kwargs=={'account_id':'fixture-account'}
    failure=RuntimeError('fixture transport failure')
    client.get_option_chain.side_effect=failure
    with pytest.raises(RuntimeError) as caught: chain(symbol,'2026-10-19')
    assert caught.value is failure
    assert client.get_option_chain.call_count==2  # No alternate request/provider retry.
