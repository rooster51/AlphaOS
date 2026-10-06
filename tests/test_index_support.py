from copy import deepcopy
from datetime import datetime,timezone
from unittest.mock import Mock
from types import SimpleNamespace as NS
import pytest
from test_api_hardening import env,dataset
from test_public_history import response,client_for
from alphaos_api.service import symbol_value,APIError
from modules.symbol_registry import instrument,SYMBOLS
from modules.market_state_research import build_research_dataset
from modules.public_history import fetch_research_bars
from modules.history_diagnostics import HistoryError
from modules.public_provider import get_public_quotes,get_public_option_expirations,get_public_option_chain,PublicProviderError


def index_fixture(p,symbol,expiry='2026-09-24'):
    spec=instrument(symbol);step=spec.default_wing_width;spot=7500 if symbol=='SPX' else 750
    p.quote.return_value[0].update(symbol=symbol,last=spot,bid=None,ask=None)
    p.expirations.return_value=[expiry]
    chain=p.chain.return_value;chain.update(symbol=symbol,expiration=expiry)
    for side in ('puts','calls'):
        for l in chain[side]:
            l['strike']=spot+(l['strike']-100)*step;l['bid']*=step;l['ask']*=step
            l['contract']=f"{spec.option_roots[0]}{expiry[2:].replace('-','')}{'P' if side=='puts' else 'C'}{round(l['strike']*1000):08d}"
    bars=dataset()['features'][['date','symbol','open','high','low','close']].copy();bars['symbol']=symbol
    for col in ('open','high','low','close'):bars[col]*=spot/100
    p.history.return_value=build_research_dataset(bars,'2022-01-01',dict(source='direct index fixture'))


@pytest.mark.parametrize('symbol,width,root',[('SPY',1,'SPY'),('QQQ',1,'QQQ'),('SPX',5,'SPXW'),('XSP',1,'XSP')])
def test_registry(symbol,width,root):
    assert symbol_value(' '+symbol.lower()+' ')==symbol
    s=instrument(symbol);assert s.default_wing_width==width and s.option_roots==(root,)
    assert s.contract_multiplier==100 and not s.research_proxy_used


@pytest.mark.parametrize('symbol',['SPX','XSP'])
@pytest.mark.parametrize('dte',[0,1,2])
def test_index_run_direct_evidence_economics(env,symbol,dte):
    c,p,s,clock=env;expiry=f'2026-09-{24+dte}';index_fixture(p,symbol,expiry)
    out=c.get('/v1/research/'+symbol+'/run',params=dict(dte_min=dte,dte_max=dte,maximum_candidates=2)).json()
    assert out['status']=='complete',out
    assert out['defaults']['wing_width']==instrument(symbol).default_wing_width
    state=out['live_trade_state'];assert state['usable_for_live_research'] and not state['usable_for_execution_analysis']
    assert state['current_spot']!=out['market_snapshot']['research_close']
    assert out['market_snapshot']['analog_N']>0
    rows=out['qualifying_candidates'];assert len(rows)==2
    for i,r in enumerate(rows):
        t=r['trade_snapshot'];width=instrument(symbol).default_wing_width
        assert t['symbol']==symbol and t['width']==width
        assert t['credit']==pytest.approx(.35*width)
        assert t['max_profit']==pytest.approx(35*width)
        assert t['max_loss']==pytest.approx(65*width)
        assert t['return_on_risk']==pytest.approx(35/65)
        assert t['breakeven']==pytest.approx(t['short_strike']+(-t['credit'] if i==0 else t['credit']))
        assert [v['price'] for v in r['historical_analog_behavior']['levels']]==[t['short_strike'],t['breakeven'],t['long_strike']]
        assert r['historical_scenario_payoff']['summary']['n']>0
        assert all(v['price']>state['current_spot']*.5 for v in r['market_structure']['price_ladder'])
    assert [x['DTE'] for x in out['candidate_scan']['candidates']]==[dte,dte]
    p.history.assert_called_once_with(symbol,clock.value.date())
    for kind,r in zip(('put','call'),rows):
        t=r['trade_snapshot'];v=c.get('/v1/research/'+symbol+'/vertical',params=dict(expiration=expiry,option_type=kind,short_strike=t['short_strike'],long_strike=t['long_strike']))
        assert v.status_code==200,v.text


@pytest.mark.parametrize('symbol',['SPX','XSP'])
def test_stale_index_stops_before_history_and_scan(env,symbol):
    c,p,s,clock=env;index_fixture(p,symbol);p.quote.return_value[0]['updated_at']='2026-09-23T15:00:00Z'
    r=c.get('/v1/research/'+symbol+'/run').json()
    assert r['status']=='live_research_stopped';p.chain.assert_not_called();p.history.assert_not_called()


def test_unavailable_spx_one_point_wing_not_substituted(env):
    c,p,s,clock=env;index_fixture(p,'SPX')
    r=c.get('/v1/research/SPX/run',params=dict(dte_min=0,dte_max=0,wing_width=1)).json()
    assert r['status']=='complete' and r['qualifying_candidates']==[]


@pytest.mark.parametrize('symbol,badroot',[('SPX','SPX'),('SPX','SPY'),('XSP','SPXW'),('XSP','QQQ')])
def test_contract_root_stays_strict(env,symbol,badroot):
    c,p,s,clock=env;index_fixture(p,symbol)
    a,b=deepcopy(p.chain.return_value['puts'][-2:]);short,long=b,a
    short['contract']=short['contract'].replace(instrument(symbol).option_roots[0],badroot,1)
    with pytest.raises(APIError) as exc:s.validate_legs(short,long,'put',symbol,'2026-09-24')
    assert exc.value.code=='unsupported_contract_root'


@pytest.mark.parametrize('symbol',['SPX','XSP'])
def test_market_local_dte_at_utc_midnight(env,symbol):
    c,p,s,clock=env;clock.value=datetime(2026,9,25,0,30,tzinfo=timezone.utc)
    assert s.today().isoformat()=='2026-09-24'
    assert s.expiration('2026-09-24')=='2026-09-24'


@pytest.mark.parametrize('symbol',['SPX','XSP'])
def test_provider_quote_expirations_chain_mapping(symbol):
    from public_api_sdk import InstrumentType
    client=Mock();ctx=lambda:(client,'fixture-account')
    client.get_quotes.return_value=[NS(instrument=NS(symbol=symbol),last=750,bid=None,ask=None,previous_close=749,one_day_change=None,volume=0,last_timestamp='2026-09-24T15:00:00Z')]
    assert get_public_quotes((symbol,),ctx)[0]['symbol']==symbol
    assert client.get_quotes.call_args.args[0][0].type==InstrumentType.INDEX
    client.get_option_expirations.return_value=NS(base_symbol=symbol+'-INDEX',expirations=['2026-09-24','2026-09-25','2026-09-26'])
    assert len(get_public_option_expirations(symbol,ctx))==3
    assert client.get_option_expirations.call_args.args[0].instrument.type==InstrumentType.INDEX
    greek=NS(delta=.3,gamma=.01,theta=-.1,vega=.2,rho=.01,implied_volatility=.2)
    q=NS(instrument=NS(symbol=instrument(symbol).option_roots[0]+'260924C00750000'),bid=1,ask=1.1,option_details=NS(strike_price=750,mid_price=None,greeks=greek),volume=10,bid_timestamp='2026-09-24T15:00:00Z',ask_timestamp='2026-09-24T15:00:00Z')
    client.get_option_chain.return_value=NS(base_symbol=symbol+'-INDEX',calls=[q],puts=[q])
    out=get_public_option_chain(symbol,'2026-09-24',ctx)
    assert out['symbol']==symbol and out['calls'][0]['delta']==.3 and out['puts'][0]['type']=='Put'
    assert out['calls'][0]['mid']==1.05 and out['calls'][0]['bid_timestamp']
    assert client.get_option_chain.call_args.args[0].instrument.type==InstrumentType.INDEX
    client.get_option_chain.return_value.base_symbol='SPY'
    with pytest.raises(PublicProviderError):get_public_option_chain(symbol,'2026-09-24',ctx)


@pytest.mark.parametrize('symbol',['SPX','XSP'])
def test_direct_history_normalization_completed_sessions(symbol):
    raw=response(symbol=symbol+'-INDEX',period='FIVE_YEARS',start='2021-09-22')
    client=client_for(raw)
    bars=fetch_research_bars(client,symbol,'FIVE_YEARS','INDEX','2026-09-22')
    result=build_research_dataset(bars.assign(symbol=symbol),'2026-09-22')
    assert result['metadata']['symbol']==symbol and result['metadata']['end']<'2026-09-22'
    assert bars.attrs['provider_diagnostics']['provider_symbol']==symbol+'-INDEX'
    client.api_client.get.assert_called_once_with(f'/userapigateway/historicdata/INDEX/{symbol}/FIVE_YEARS/ONE_DAY',params=None)
    raw['symbol']='SPY'
    with pytest.raises(HistoryError):fetch_research_bars(client_for(raw),symbol,'FIVE_YEARS','INDEX','2026-09-22')
