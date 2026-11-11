"""Synthetic immutable storage/metadata failures; no provider or archive writes."""
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import hashlib
import json
from types import SimpleNamespace
import urllib.error

import pytest
from modules import supabase_archive as archive
from modules.intraday_archive import collect_symbol, load_config
from scripts import run_intraday_snapshot as runner

NOW = datetime(2026, 11, 3, 16, 1, tzinfo=timezone.utc)
SLOT = '2026-11-03T16:00:00+00:00'


def payload(symbol='SPY', status='complete'):
    return dict(provider='Public', symbol=symbol, session='2026-11-03',
        observed_at=NOW.isoformat(), slot_time=SLOT, underlying={'last':500},
        options=dict(status=status, received_contract_count=2540,
                     expiration_failures=[{'expiration':'2026-11-06'}] if status=='partial' else [],
                     invalid_expiration_count=0))


class Store:
    """Model immutable object POST, metadata uniqueness and lost acknowledgements."""
    def __init__(self):
        self.objects = {}; self.rows = []; self.uploads = []; self.storage = self
        self.lose_insert_ack = False
        self.fail_insert = False
    def from_(self, bucket):
        assert bucket == 'market-archive'
        return self
    def download(self, path): return self.objects[path]
    def table(self, name):
        assert name == 'option_snapshots'
        self.filters = {}; self.pending = None
        return self
    def select(self, *args): return self
    def eq(self, key, value): self.filters[key] = value; return self
    def upsert(self, row, **kwargs):
        assert kwargs == dict(on_conflict='provider,symbol,observed_at', ignore_duplicates=True)
        self.pending = deepcopy(row)
        return self
    def execute(self):
        if self.pending is not None:
            if self.fail_insert:
                self.fail_insert = False
                raise TimeoutError("private error body")
            keys = ('provider','symbol','observed_at')
            if not any(all(row[k] == self.pending[k] for k in keys) for row in self.rows):
                self.rows.append(dict(self.pending, id=len(self.rows)+1))
            if self.lose_insert_ack:
                self.lose_insert_ack = False
                raise TimeoutError('private error body')
        return SimpleNamespace(data=[deepcopy(row) for row in self.rows
            if all(row.get(k) == v for k,v in self.filters.items())])
    def post(self, request, **kwargs):
        assert request.method == 'POST' and request.get_header('X-upsert') == 'false'
        path = request.full_url.split('/market-archive/')[1]
        self.uploads.append(path)
        if path in self.objects:
            raise urllib.error.HTTPError('private-url', 400, 'already exists', {}, None)
        self.objects[path] = request.data
        return SimpleNamespaceContext()


class SimpleNamespaceContext:
    status = 200
    def __enter__(self): return self
    def __exit__(self, *args): pass


@pytest.fixture
def store(monkeypatch):
    db = Store()
    monkeypatch.setenv('SUPABASE_URL','https://example.invalid')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY','synthetic-secret')
    monkeypatch.setattr(archive.urllib.request,'urlopen',db.post)
    return db


def wire_runner(monkeypatch, db, collect):
    monkeypatch.setattr(runner.DailyPublicProvider,'from_environment',lambda:SimpleNamespace(name='Public'))
    monkeypatch.setattr(runner,'archive_client',lambda:db)
    monkeypatch.setattr(runner,'fetch_intraday_bars',lambda *args:[])
    monkeypatch.setattr(runner,'persist_candles',lambda *args:0)
    monkeypatch.setattr(runner,'collect_symbol',collect)


@pytest.mark.parametrize('status',['partial','empty'])
def test_partial_first_attempt_and_repeated_run_preserve_evidence_and_qqq(monkeypatch, store, capsys, status):
    calls = []; sleeps = []
    def collect(provider, symbol, config):
        calls.append(symbol)
        result = payload(symbol, status if symbol=='SPY' else 'complete')
        if status=='empty' and symbol=='SPY': result['options']['received_contract_count'] = 0
        return result
    wire_runner(monkeypatch, store, collect)
    assert runner.main(clock=lambda:NOW,sleep=sleeps.append) == 1
    assert calls == ['SPY','QQQ'] and sleeps == []
    saved = deepcopy(store.objects); rows = deepcopy(store.rows)
    assert runner.main(clock=lambda:NOW,sleep=sleeps.append) == 1
    assert calls == ['SPY','QQQ'] and len(store.uploads) == 2
    assert saved == store.objects and rows == store.rows
    logs = capsys.readouterr()
    assert 'archived SPY' not in logs.out and 'duplicate SPY' not in logs.out
    assert 'archived QQQ' in logs.out and 'duplicate QQQ' in logs.out
    assert 'error=IncompleteSlot' in logs.err


@pytest.mark.parametrize('status',['complete','partial'])
def test_retry_after_lost_metadata_ack_uses_verified_slot(monkeypatch, store, status):
    store.lose_insert_ack = True
    calls = []; sleeps = []
    def collect(provider, symbol, config):
        calls.append(symbol)
        return payload(symbol,status if symbol=='SPY' else 'complete')
    wire_runner(monkeypatch, store, collect)
    assert runner.main(clock=lambda:NOW,sleep=sleeps.append) == (0 if status=='complete' else 1)
    assert calls == ['SPY','QQQ'] and sleeps == [10]
    assert len(store.objects) == len(store.rows) == len(store.uploads) == 2


@pytest.mark.parametrize('winner',['complete','partial','empty'])
def test_immutable_storage_conflict_recovers_exact_winner(store, winner):
    first = payload(status=winner)
    if winner=='empty': first['options']['received_contract_count'] = 0
    row = archive.persist_option_snapshot(store,first)
    original = deepcopy(store.objects)
    # Simulate object committed but metadata absent, followed by a better response.
    store.rows = []
    second = payload()
    second['observed_at'] = '2026-11-03T16:02:00+00:00'
    result = archive.persist_option_snapshot(store,second)
    assert result == row
    assert result['quality_status'] == winner
    assert store.objects == original
    assert result['archive_sha256'] == hashlib.sha256(next(iter(original.values()))).hexdigest()


@pytest.mark.parametrize('defect',['checksum','quality','count','slot','identity','multiple','corrupt'])
def test_duplicate_verification_fails_closed(store, defect):
    row = archive.persist_option_snapshot(store,payload())
    if defect=='checksum': store.rows[0]['archive_sha256'] = '0'*64
    elif defect=='quality': store.rows[0]['quality_status'] = 'partial'
    elif defect=='count': store.rows[0]['contract_count'] += 1
    elif defect=='slot':
        obj = payload(); obj['slot_time'] = '2026-11-03T15:55:00+00:00'
        raw = gzip.compress(json.dumps(obj).encode())
        store.objects[row['archive_path']] = raw
        store.rows[0]['archive_sha256'] = hashlib.sha256(raw).hexdigest()
    elif defect=='identity': store.rows[0]['provider'] = 'Other'
    elif defect=='multiple': store.rows.append(deepcopy(store.rows[0]))
    else: store.objects[row['archive_path']] = b'corrupt'
    # Identity test queries the changed metadata identity to reach validation.
    with pytest.raises(archive.ArchiveUnavailable):
        archive.find_slot_snapshot(store,'Other' if defect=='identity' else 'Public','SPY',SLOT)


def test_metadata_conflict_cannot_turn_partial_object_into_success(store):
    row = archive.persist_option_snapshot(store,payload(status='partial'))
    store.rows[0]['quality_status'] = 'complete'
    with pytest.raises(archive.ArchiveUnavailable,match='metadata verification'):
        archive.persist_option_snapshot(store,payload())
    assert store.objects[row['archive_path']]


@pytest.mark.parametrize('defect',['different_symbol','bad_gzip','unavailable'])
def test_conflict_recovery_rejects_unusable_object(store, defect):
    row = archive.persist_option_snapshot(store,payload())
    store.rows = []
    if defect=='different_symbol':
        store.objects[row['archive_path']] = gzip.compress(json.dumps(payload('QQQ')).encode())
    elif defect=='bad_gzip': store.objects[row['archive_path']] = b'not gzip'
    else: store.objects.clear()
    # Force a network error even if the object is absent.
    def fail(*args,**kwargs): raise urllib.error.URLError('private-body')
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(archive.urllib.request,'urlopen',fail)
        with pytest.raises(archive.ArchiveUnavailable,match='upload/recovery failed'):
            archive.persist_option_snapshot(store,payload())
    assert store.rows == []


@pytest.mark.parametrize('defect',['failed_chain','invalid_expiry','fewer_records'])
def test_provider_quality_and_contract_count_are_distinct(defect):
    class Provider:
        name = 'Public'
        def now(self): return NOW
        def underlying(self,symbol):
            return dict(instrument=dict(symbol=symbol,type='EQUITY'),outcome='SUCCESS',last=500)
        def expirations(self,symbol):
            return ['2026-11-03','2026-11-04'] + (['malformed'] if defect=='invalid_expiry' else [])
        def chain(self,symbol,expiry):
            if defect=='failed_chain' and symbol=='SPY' and expiry=='2026-11-04':
                raise TimeoutError('secret provider response')
            # Malformed observations are retained as rejected evidence, not lost.
            return dict(calls=[{}]*(1 if defect=='fewer_records' else 2),puts=[])
    spy = collect_symbol(Provider(),'SPY',load_config())['options']
    qqq = collect_symbol(Provider(),'QQQ',load_config())['options']
    assert spy['status'] == ('complete' if defect=='fewer_records' else 'partial')
    assert qqq['status'] == ('partial' if defect=='invalid_expiry' else 'complete')
    if defect=='failed_chain':
        assert spy['received_contract_count']==2 and qqq['received_contract_count']==4
        assert spy['expiration_failures']==[dict(expiration='2026-11-04',reason='chain_retrieval_failed')]
    if defect=='invalid_expiry': assert spy['invalid_expiration_count']==1


@pytest.mark.parametrize('status',['complete','partial'])
def test_retry_after_object_only_commit_recovers_first_attempt(monkeypatch, store, status, capsys):
    store.fail_insert = True
    calls = []; sleeps = []
    def collect(provider, symbol, config):
        calls.append(symbol)
        # The second response improves, but cannot replace the first evidence.
        result = payload(symbol,status if calls==['SPY'] else 'complete')
        if calls==['SPY','SPY']: result['observed_at'] = '2026-11-03T16:02:00+00:00'
        return result
    wire_runner(monkeypatch, store, collect)
    assert runner.main(clock=lambda:NOW,sleep=sleeps.append) == (0 if status=='complete' else 1)
    assert calls == ['SPY','SPY','QQQ'] and sleeps == [10]
    assert len(store.uploads)==3 and len(store.objects)==len(store.rows)==2
    spy = next(row for row in store.rows if row['symbol']=='SPY')
    assert spy['observed_at']==NOW.isoformat() and spy['quality_status']==status
    logs = capsys.readouterr()
    assert 'private error body' not in logs.err
    assert ('archived SPY' in logs.out) == (status=='complete')
    assert 'archived QQQ' in logs.out


@pytest.mark.parametrize('options',[
    dict(status='complete',received_contract_count=0),
    dict(status='complete',received_contract_count=2,expiration_failures=[{}]),
    dict(status='complete',received_contract_count=2,invalid_expiration_count=1),
    dict(status='unknown',received_contract_count=2),
])
def test_invalid_quality_is_rejected_before_upload(store, options):
    candidate = payload(); candidate['options'] = options
    with pytest.raises(archive.ArchiveUnavailable):
        archive.persist_option_snapshot(store,candidate)
    assert store.uploads==[] and store.rows==[]
