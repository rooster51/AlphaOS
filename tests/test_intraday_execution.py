from datetime import datetime, timezone
from types import SimpleNamespace
import gzip
import json
import urllib.error
import pytest
from modules.market_session_gate import regular_session_slot
from scripts import run_intraday_snapshot as runner
from modules import supabase_archive as archive

NOW=datetime(2026,10,5,14,32,tzinfo=timezone.utc)

@pytest.mark.parametrize('stamp,opened', [('2026-10-05T14:32:00+00:00',True),('2026-10-04T14:30:00+00:00',False),
 ('2026-12-25T15:00:00+00:00',False),('2026-11-27T18:00:00+00:00',False),('2026-10-05T20:00:00+00:00',False),('2026-10-05T12:00:00+00:00',False)])
def test_calendar(stamp,opened):
    assert (regular_session_slot(datetime.fromisoformat(stamp)) is not None)==opened


def setup(monkeypatch):
    monkeypatch.setattr(runner.DailyPublicProvider,'from_environment',lambda:SimpleNamespace(name='Public'))
    monkeypatch.setattr(runner,'archive_client',lambda:object())
    monkeypatch.setattr(runner,'fetch_intraday_bars',lambda *a:[])
    monkeypatch.setattr(runner,'persist_candles',lambda *a:0)
    monkeypatch.setattr(runner,'find_slot_snapshot',lambda *a:None)
    monkeypatch.setattr(runner,'collect_symbol',lambda *a:dict(observed_at=NOW.isoformat()))


def test_actual_time_and_slot(monkeypatch):
    setup(monkeypatch)
    rows=[]
    def persist(db,payload,config):
        rows.append(payload)
        return dict(payload,quality_status='complete')
    monkeypatch.setattr(runner,'persist_option_snapshot',persist)
    assert runner.main(clock=lambda:NOW,sleep=lambda s:None)==0
    assert len(rows)==2
    assert rows[0]['observed_at']!=rows[0]['slot_time']
    assert rows[0]['slot_time'].endswith('14:30:00+00:00')


def test_failure_retry_continues_other_symbol_and_safe_logs(monkeypatch,capsys):
    setup(monkeypatch)
    calls=[]
    def collect(provider,symbol,config):
        calls.append(symbol)
        if symbol=='SPY':raise ValueError('SECRET SENTINEL')
        return dict(observed_at=NOW.isoformat())
    monkeypatch.setattr(runner,'collect_symbol',collect)
    monkeypatch.setattr(runner,'persist_option_snapshot',lambda db,p,c:dict(p,quality_status='complete'))
    assert runner.main(clock=lambda:NOW,sleep=lambda s:None)==1
    assert calls==['SPY','SPY','QQQ']
    assert 'SECRET SENTINEL' not in capsys.readouterr().err


def test_duplicate_skips_provider_and_incomplete_fails(monkeypatch):
    setup(monkeypatch)
    monkeypatch.setattr(runner,'collect_symbol',lambda *a:pytest.fail('duplicate collection'))
    monkeypatch.setattr(runner,'find_slot_snapshot',lambda *a:dict(quality_status='complete'))
    assert runner.main(clock=lambda:NOW,sleep=lambda s:None)==0
    monkeypatch.setattr(runner,'find_slot_snapshot',lambda *a:dict(quality_status='partial'))
    assert runner.main(clock=lambda:NOW,sleep=lambda s:None)==1


def test_closed_does_not_authenticate(monkeypatch):
    monkeypatch.setattr(runner.DailyPublicProvider,'from_environment',lambda:pytest.fail('closed authentication'))
    assert runner.main(clock=lambda:datetime(2026,10,4,tzinfo=timezone.utc))==0


class DB:
    def __init__(self,saved):self.saved=saved;self.row=None;self.storage=self
    def from_(self,*a):return self
    def download(self,*a):return self.saved
    def table(self,*a):return self
    def upsert(self,row,**kwargs):self.row=row;return self
    def select(self,*a,**kw):return self
    def eq(self,*a):return self
    def execute(self):return SimpleNamespace(data=[self.row])


def test_upload_collision_recovers_first_payload_and_metadata(monkeypatch):
    payload=dict(provider='Public',symbol='SPY',session='2026-10-05',slot_time='2026-10-05T14:30:00+00:00',
                 observed_at='2026-10-05T14:31:00+00:00',underlying={'last':500},options={'received_contract_count':2100,'status':'complete'})
    original=gzip.compress(json.dumps(payload).encode(),mtime=0)
    db=DB(original)
    monkeypatch.setenv('SUPABASE_URL','https://example.invalid')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY','secret')
    def collide(*a,**kw):raise urllib.error.HTTPError('url',409,'duplicate',{},None)
    monkeypatch.setattr(archive.urllib.request,'urlopen',collide)
    result=archive.persist_option_snapshot(db,dict(payload,observed_at='2026-10-05T14:33:00+00:00'))
    assert result['observed_at']==payload['observed_at']
    assert result['contract_count']==2100
    assert result['slot_time']==payload['slot_time']
    assert '143000' in result['archive_path']


def test_workflows_remain_manual_only():
    from pathlib import Path
    for name in ('daily-quant','intraday-archive'):
        assert '  schedule:' not in Path(f'.github/workflows/{name}.yml').read_text()
