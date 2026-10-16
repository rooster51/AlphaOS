"""Collector-produced fixtures through the real read-only checksum boundary.

These are synthetic observations, never claims about private production payloads.
"""
from copy import deepcopy
from datetime import datetime, timedelta
import gzip
import hashlib
import json

import pytest

from modules.intraday_archive import collect_symbol, load_config
from modules.intraday_quoted_round_trip import EvidenceRejected, reconstruct_quoted_round_trip
from modules.supabase_archive import ArchiveUnavailable, read_latest_option_snapshot
from tests.test_archive_read_path import ReadOnlyClient


class Provider:
    name = 'Public'

    def __init__(self, symbol, stamp, closing=False, kind='call'):
        self.symbol, self.stamp, self.closing, self.kind = symbol, stamp, closing, kind
        self.expiry = stamp.date().isoformat()
        self.contract = symbol + stamp.strftime('%y%m%d') + ('C' if kind == 'call' else 'P') + '00750000'

    def now(self):
        return self.stamp

    def underlying(self, symbol):
        return dict(instrument=dict(symbol=symbol, type='EQUITY'), outcome='SUCCESS',
                    last=750, lastTimestamp=self.stamp.isoformat())

    def expirations(self, symbol):
        return [self.expiry]

    def chain(self, symbol, expiry):
        row = dict(instrument=dict(symbol=self.contract, type='OPTION'), outcome='SUCCESS',
                   optionDetails=dict(strikePrice=750), bid=1.45 if self.closing else 1.10,
                   ask=1.55 if self.closing else 1.20,
                   bidTimestamp=(self.stamp-timedelta(seconds=5)).isoformat(),
                   askTimestamp=(self.stamp-timedelta(seconds=5)).isoformat())
        return dict(calls=[row] if self.kind == 'call' else [],
                    puts=[row] if self.kind == 'put' else [])


def stored(symbol='SPY', closing=False, kind='call'):
    stamp = datetime.fromisoformat('2026-10-09T14:09:00+00:00' if closing else '2026-10-09T14:04:00+00:00')
    provider = Provider(symbol, stamp, closing, kind)
    payload = collect_symbol(provider, symbol, load_config())
    payload['slot_time'] = stamp.replace(minute=stamp.minute//5*5).isoformat()
    payload['collection_finished_at'] = (stamp+timedelta(seconds=1)).isoformat()
    db = ReadOnlyClient()
    db.payload = payload
    db.row = dict(id='exit' if closing else 'entry', provider='Public', symbol=symbol,
                  session_date=payload['session'], observed_at=payload['observed_at'],
                  slot_time=payload['slot_time'], created_at=(stamp+timedelta(seconds=2)).isoformat(),
                  quality_status=payload['options']['status'],
                  archive_path=f'options/symbol={symbol}/date={payload["session"]}/{"exit" if closing else "entry"}.json.gz')
    seal(db)
    return db, provider.contract, (stamp+timedelta(seconds=30)).isoformat()


def seal(db):
    # Same serialization as persistence; never invoke a write-capable client.
    db.raw = gzip.compress(json.dumps(db.payload, separators=(',', ':'), sort_keys=True).encode(), mtime=0)
    db.row['archive_sha256'] = hashlib.sha256(db.raw).hexdigest()


@pytest.mark.parametrize('symbol', ['SPY', 'QQQ'])
@pytest.mark.parametrize('kind', ['call', 'put'])
@pytest.mark.parametrize('side,expected', [('long', 23.70), ('short', -46.30)])
def test_collector_reader_evaluator_exact_envelope(symbol, kind, side, expected):
    opening, contract, entry_at = stored(symbol, kind=kind)
    closing, _, exit_at = stored(symbol, closing=True, kind=kind)
    entry = read_latest_option_snapshot(opening, symbol, entry_at, max_age_seconds=120)
    exit = read_latest_option_snapshot(closing, symbol, exit_at, max_age_seconds=120)
    before = deepcopy((entry, exit))
    result = reconstruct_quoted_round_trip(entry, exit, [dict(contract=contract, side=side, quantity=1)],
        entry_as_of=entry_at, exit_as_of=exit_at, fee_per_contract_per_side=.65)
    assert set(entry) == {'payload', 'metadata', 'freshness'}
    assert entry['freshness']['age_seconds'] == 30
    assert entry['metadata']['archive_sha256'] == hashlib.sha256(opening.raw).hexdigest()
    assert entry['payload']['observed_at'] != entry['payload']['slot_time']
    assert result['hypothetical_pnl_usd'] == expected
    assert result['status'] == 'descriptive_quoted_round_trip_only'
    assert (entry, exit) == before  # Immutable evidence is not rewritten by evaluation.
    assert ('lte', 'observed_at', entry_at) in opening.calls
    assert ('lte', 'created_at', entry_at) in opening.calls
    assert ('lte', 'created_at', exit_at) in closing.calls
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize('defect', ['partial', 'missing_quote', 'contract_mismatch'])
def test_verified_bytes_do_not_imply_usable_quotes(defect):
    opening, contract, entry_at = stored()
    closing, _, exit_at = stored(closing=True)
    if defect == 'partial':
        opening.payload['options']['status'] = opening.row['quality_status'] = 'partial'
    elif defect == 'missing_quote':
        opening.payload['options']['valid_contracts'][0]['bid_timestamp'] = None
    else:
        opening.payload['options']['valid_contracts'][0]['strike'] = 751
    seal(opening)
    entry = read_latest_option_snapshot(opening, 'SPY', entry_at, max_age_seconds=120)
    exit = read_latest_option_snapshot(closing, 'SPY', exit_at, max_age_seconds=120)
    with pytest.raises(EvidenceRejected):
        reconstruct_quoted_round_trip(entry, exit, [dict(contract=contract, side='long', quantity=1)],
                                     entry_as_of=entry_at, exit_as_of=exit_at)


@pytest.mark.parametrize('defect', ['late_insert', 'future_finish', 'slot', 'checksum', 'stale'])
def test_collector_payload_reader_cutoff_and_integrity(defect):
    db, _, cutoff = stored()
    if defect == 'late_insert':
        db.row['created_at'] = '2026-10-09T14:05:00Z'
    elif defect == 'future_finish':
        db.payload['collection_finished_at'] = '2026-10-09T14:05:00Z'
        seal(db)
    elif defect == 'slot':
        db.row['slot_time'] = '2026-10-09T14:05:00Z'
    elif defect == 'checksum':
        db.raw += b'corruption'
    else:
        cutoff = '2026-10-09T14:10:00Z'
    with pytest.raises(ArchiveUnavailable):
        read_latest_option_snapshot(db, 'SPY', cutoff, max_age_seconds=120)
