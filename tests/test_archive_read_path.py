"""Read-only persisted-archive contract; no live provider or Supabase credentials."""
from copy import deepcopy
from functools import partial
from types import SimpleNamespace
import gzip
import hashlib
import json

import pytest

from modules.supabase_archive import ArchiveUnavailable, read_latest_option_snapshot
from modules.run_market import run_latest_market
from tests.test_market_archive_adapter import payload
from tests.test_run_market import history

AS_OF = '2030-01-02T20:33:00+00:00'


class ReadOnlyClient:
    # No write/auth/provider methods: unexpected writes fail the test.
    def __init__(self):
        self.payload = payload()
        self.payload.update(slot_time='2030-01-02T20:25:00+00:00',
                            collection_finished_at='2030-01-02T20:32:00+00:00')
        self.raw = gzip.compress(json.dumps(self.payload).encode(), mtime=0)
        self.row = dict(id='fixture', provider='Public', symbol='QQQ',
            observed_at=self.payload['observed_at'], session_date=self.payload['session'],
            slot_time=self.payload['slot_time'], created_at='2030-01-02T20:32:30+00:00',
            quality_status='complete', archive_path='options/symbol=QQQ/date=2030-01-02/fixture.json.gz',
            archive_sha256=hashlib.sha256(self.raw).hexdigest())
        self.storage = self
        self.calls = []
    def table(self, name):
        assert name == 'option_snapshots'
        return self
    def select(self, fields): return self
    def eq(self, *args): self.calls.append(('eq', *args)); return self
    def lte(self, *args): self.calls.append(('lte', *args)); return self
    def order(self, name, **kwargs): self.calls.append(('order', name, kwargs)); return self
    def limit(self, value): assert value == 1; return self
    def execute(self): return SimpleNamespace(data=[deepcopy(self.row)] if self.row else [])
    def from_(self, bucket): assert bucket == 'market-archive'; return self
    def download(self, path): assert path == self.row['archive_path']; return self.raw


def test_latest_storage_to_run_qqq_read_only():
    client = ReadOnlyClient()
    reader = partial(read_latest_option_snapshot, client, max_age_seconds=300)
    result = run_latest_market('QQQ', as_of=AS_OF, read_snapshot=reader,
                               history=history(), available_capital=150)
    assert result['status'] == 'complete'
    assert result['read_only'] is True
    assert result['archive']['storage']['archive_sha256'] == client.row['archive_sha256']
    assert result['archive']['freshness']['age_seconds'] == 180
    assert result['as_of'] == client.payload['observed_at']  # Not request time or slot time.
    assert result['requested_as_of'] == AS_OF
    assert ('eq', 'symbol', 'QQQ') in client.calls
    assert ('lte', 'created_at', AS_OF) in client.calls
    assert result['research_session']['comparison']['winner'] is None
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize('defect', ['checksum', 'future_observed', 'future_created', 'slot', 'symbol', 'path', 'empty'])
def test_invalid_storage_evidence_fails_closed(defect):
    client = ReadOnlyClient()
    if defect == 'checksum': client.row['archive_sha256'] = 'bad'
    if defect == 'future_observed': client.row['observed_at'] = '2030-01-03T20:30:00+00:00'
    if defect == 'future_created': client.row['created_at'] = '2030-01-03T20:30:00+00:00'
    if defect == 'slot': client.row['slot_time'] = None
    if defect == 'symbol': client.payload['symbol'] = 'SPY'; client.raw = gzip.compress(json.dumps(client.payload).encode()); client.row['archive_sha256'] = hashlib.sha256(client.raw).hexdigest()
    if defect == 'path': client.row['archive_path'] = 'other-bucket/secret'
    if defect == 'empty': client.row = None
    with pytest.raises(ArchiveUnavailable):
        read_latest_option_snapshot(client, 'QQQ', AS_OF, max_age_seconds=300)


def test_stale_snapshot_not_silently_used():
    with pytest.raises(ArchiveUnavailable):
        read_latest_option_snapshot(ReadOnlyClient(), 'QQQ', AS_OF, max_age_seconds=60)


def test_latest_partial_is_not_replaced_or_hidden():
    client = ReadOnlyClient()
    client.payload['options']['status'] = client.row['quality_status'] = 'partial'
    client.payload['options']['expiration_failures'] = [{'expiration': '2030-01-02', 'reason': 'chain_retrieval_failed'}]
    client.raw = gzip.compress(json.dumps(client.payload).encode())
    client.row['archive_sha256'] = hashlib.sha256(client.raw).hexdigest()
    result = run_latest_market('QQQ', as_of=AS_OF,
        read_snapshot=partial(read_latest_option_snapshot, client, max_age_seconds=300), history=history())
    assert result['status'] == 'no_candidate'
    assert result['archive']['observation']['options_status'] == 'partial'
    assert result['archive']['observation']['expiration_failures']


def test_legacy_null_slots_remain_readable():
    client = ReadOnlyClient()
    client.row['slot_time'] = None
    client.payload.pop('slot_time')
    client.raw = gzip.compress(json.dumps(client.payload).encode())
    client.row['archive_sha256'] = hashlib.sha256(client.raw).hexdigest()
    assert read_latest_option_snapshot(client, 'QQQ', AS_OF, max_age_seconds=300)['payload'].get('slot_time') is None


def test_latest_does_not_research_expired_contract_as_current():
    client = ReadOnlyClient()
    with pytest.raises(ValueError, match='expiration precedes'):
        run_latest_market('QQQ', as_of='2030-01-03T15:00:00+00:00',
            read_snapshot=partial(read_latest_option_snapshot, client, max_age_seconds=86400), history=history())
