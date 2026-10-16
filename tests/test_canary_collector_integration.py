from unittest.mock import Mock
import pytest
from scripts import run_intraday_snapshot as runner
from tests.test_intraday_execution import setup, NOW
from modules.intraday_archive import collect_symbol, load_config

@pytest.mark.parametrize('symbol',['NVDA','IWM'])
def test_opt_in_preserves_core_then_canary(monkeypatch,symbol):
    setup(monkeypatch)
    monkeypatch.setenv('ALPHAOS_INTRADAY_CANARY',symbol)
    collected=[]
    monkeypatch.setattr(runner,'collect_symbol',lambda p,s,c: collected.append(s) or dict(observed_at=NOW.isoformat()))
    monkeypatch.setattr(runner,'persist_option_snapshot',lambda d,p,c:dict(p,quality_status='complete'))
    assert runner.main(clock=lambda:NOW,sleep=lambda _:None)==0
    assert collected==['SPY','QQQ',symbol]

@pytest.mark.parametrize('mode',['failure','partial','duplicate'])
def test_canary_failure_retry_and_duplicate(monkeypatch,mode,capsys):
    setup(monkeypatch);monkeypatch.setenv('ALPHAOS_INTRADAY_CANARY','NVDA')
    collected=[]
    def collect(p,s,c):
        collected.append(s)
        if s=='NVDA' and mode=='failure':raise RuntimeError('SENSITIVE')
        return dict(symbol=s,observed_at=NOW.isoformat())
    monkeypatch.setattr(runner,'collect_symbol',collect)
    monkeypatch.setattr(runner,'persist_option_snapshot',lambda d,p,c:dict(p,
        quality_status='partial' if p['symbol']=='NVDA' and mode=='partial' else 'complete'))
    if mode=='duplicate':monkeypatch.setattr(runner,'find_slot_snapshot',lambda d,p,s,t:dict(quality_status='complete') if s=='NVDA' else None)
    assert runner.main(clock=lambda:NOW,sleep=lambda _:None)==(0 if mode=='duplicate' else 1)
    assert collected[:2]==['SPY','QQQ']
    assert collected.count('NVDA')==(0 if mode=='duplicate' else 2)
    assert 'SENSITIVE' not in capsys.readouterr().err

def test_bad_config_stops_before_provider(monkeypatch):
    monkeypatch.setenv('ALPHAOS_INTRADAY_CANARY','NVDA,IWM')
    auth=Mock();monkeypatch.setattr(runner.DailyPublicProvider,'from_environment',auth)
    assert runner.main(clock=lambda:NOW)==1
    auth.assert_not_called()

@pytest.mark.parametrize('symbol',['NVDA','IWM'])
def test_actual_archive_constructor_provider_contracts(symbol):
    class Provider:
        name='Public'
        def now(self):return NOW
        stale=False
        def underlying(self,s):return dict(instrument=dict(symbol=s,type='EQUITY'),outcome='SUCCESS',last=100,lastTimestamp=('2026-10-05T13:00:00Z' if self.stale else NOW.isoformat()))
        def expirations(self,s):return ['2026-10-09']
        def chain(self,s,e):return dict(calls=[dict(instrument=dict(symbol=s+'261009C00100000',type='OPTION'),optionDetails=dict(strikePrice=100),outcome='SUCCESS',bid=2,ask=2.1,
            bidTimestamp=NOW.isoformat(),askTimestamp=NOW.isoformat())],puts=[])
    config=dict(load_config(),canary_symbol=symbol)
    result=collect_symbol(Provider(),symbol,config)
    assert result['symbol']==symbol
    assert result['options']['status']=='complete'
    assert result['options']['received_contract_count']==1
    assert not result['options']['rejected_contracts']
    with pytest.raises(ValueError):collect_symbol(Provider(),symbol,load_config())
    stale=Provider();stale.stale=True
    with pytest.raises(ValueError):collect_symbol(stale,symbol,config)
