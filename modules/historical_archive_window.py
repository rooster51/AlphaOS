"""Bounded read-only historical evidence coverage; never prices or replays trades."""
from collections import Counter
from datetime import date, timedelta
import gzip
import hashlib
import json
from math import isfinite
import re

from modules.market_session_gate import regular_session_bounds, regular_session_slot
from modules.options_archive import timestamp
from modules.supabase_archive import _verify_snapshot_row

VERSION = 'historical-archive-window-v1'
CADENCE_MINUTES = 5
MAX_ROWS = 500
OSI = re.compile(r'([A-Z]{1,6})(\d{6})([CP])(\d{8})')


class EvidenceError(ValueError):
    pass


def _require(condition, reason):
    if not condition:
        raise EvidenceError(reason)


def _finite(value):
    return type(value) in (int, float) and isfinite(value)


def _schedule(start, end):
    bounds = regular_session_bounds(start)
    _require(bounds is not None, 'outside_regular_session')
    opened, closed = bounds
    _require(opened <= start < end <= closed, 'outside_regular_session')
    _require(regular_session_slot(start) == start and
             end.second == end.microsecond == 0 and end.minute % CADENCE_MINUTES == 0,
             'unaligned_window')
    slots = []
    cursor = start
    while cursor < end:
        slots.append(cursor)
        cursor += timedelta(minutes=CADENCE_MINUTES)
    return slots, opened, closed


def _selected_quotes(payload, expiration, contracts, opened, closed, quote_age):
    options = payload['options']
    _require(expiration in options.get('requested_expirations', []), 'selected_expiration_missing')
    failures = options.get('expiration_failures')
    _require(isinstance(failures, list) and all(isinstance(f, dict) for f in failures),
             'expiration_evidence_invalid')
    _require(not any(f.get('expiration') == expiration for f in failures), 'selected_expiration_failed')
    requests = options.get('requests')
    _require(isinstance(requests, list), 'expiration_evidence_unavailable')
    selected = [r for r in requests if isinstance(r, dict) and r.get('expiration') == expiration]
    _require(len(selected) == 1, 'expiration_evidence_unavailable')
    begin = timestamp(options['collection_started_at'])
    generated = timestamp(options['generated_at'])
    request_start, received = timestamp(selected[0]['started_at']), timestamp(selected[0]['received_at'])
    _require(begin <= request_start <= received <= generated, 'out_of_order_timestamps')
    indexed = {}
    for bucket in ('valid_contracts', 'questionable_contracts', 'rejected_contracts'):
        rows = options.get(bucket)
        _require(isinstance(rows, list) and all(isinstance(r, dict) for r in rows), 'invalid_contract_evidence')
        for row in rows:
            indexed.setdefault(row.get('contract'), []).append((bucket, row))
    quotes = []
    for contract in contracts:
        matches = indexed.get(contract, [])
        _require(bool(matches), 'missing_contract_leg')
        _require(len(matches) == 1, 'duplicate_contract_evidence')
        bucket, row = matches[0]
        _require(bucket != 'rejected_contracts' and not row.get('rejection_reasons'), 'invalid_contract_evidence')
        match = OSI.fullmatch(contract)
        _require(row.get('contract') == contract and row.get('symbol') == payload['symbol'] and
                 row.get('expiration') == expiration and row.get('type') == ('call' if match[3] == 'C' else 'put') and
                 _finite(row.get('strike')) and row['strike'] == int(match[4]) / 1000,
                 'contract_identity_mismatch')
        bid, ask = row.get('bid'), row.get('ask')
        _require(row.get('quote_outcome') == 'SUCCESS' and _finite(bid) and _finite(ask) and
                 0 <= bid <= ask and ask > 0, 'invalid_bid_ask_evidence')
        observed = timestamp(row['observed_at'])
        _require(request_start <= observed == received, 'out_of_order_timestamps')
        quotes_at = [timestamp(row[side + '_timestamp']) for side in ('bid', 'ask')]
        _require(all(opened <= t < closed and t <= observed for t in quotes_at), 'invalid_quote_chronology')
        _require(all((observed-t).total_seconds() <= quote_age for t in quotes_at), 'stale_quote')
        # Preserve actual observations and provenance only. No size/price defaults.
        quotes.append(dict(contract=contract, symbol=payload['symbol'], expiration=expiration,
            quote_outcome=row['quote_outcome'], type=row['type'], strike=row['strike'],
            bid=bid, ask=ask, bid_timestamp=row['bid_timestamp'], ask_timestamp=row['ask_timestamp'],
            observed_at=row['observed_at'], archive_quality=bucket,
            quality_warnings=row.get('quality_warnings', []),
            **{key: row[key] for key in ('bid_size', 'ask_size') if key in row}))
    return quotes


def _observation(client, row, symbol, slot, start, end, as_of, expiration, contracts,
                 opened, closed, quote_age, observation_age):
    outcome = dict(slot_time=slot.isoformat(), status='invalid_observation', reasons=[],
                   integrity_verified=False, selected_expiration_verified=False,
                   sufficient_evidence=False, observation=None)
    try:
        _require(isinstance(row.get('id'), str) and bool(row['id']), 'snapshot_identity_mismatch')
        path = row['archive_path']
        day = opened.date().isoformat()
        _require(row['provider'] == 'Public' and row['symbol'] == symbol and row['session_date'] == day,
                 'snapshot_identity_mismatch')
        _require(isinstance(path, str) and path.startswith(f'options/symbol={symbol}/date={day}/') and
                 path.endswith('.json.gz') and '..' not in path, 'invalid_archive_path')
        try:
            raw = client.storage.from_('market-archive').download(path)
        except Exception:
            raise EvidenceError('payload_unavailable') from None
        _require(hashlib.sha256(raw).hexdigest() == row['archive_sha256'], 'checksum_mismatch')
        try:
            payload = json.loads(gzip.decompress(raw))
        except Exception:
            raise EvidenceError('payload_invalid') from None
        _require(payload.get('schema_version') == 'intraday-archive-v1' and
                 payload['options'].get('schema_version') == 'options-archive-v1', 'payload_schema_invalid')
        try:
            _verify_snapshot_row(row, payload, path, hashlib.sha256(raw).hexdigest())
        except Exception:
            raise EvidenceError('snapshot_metadata_invalid') from None
        options = payload['options']
        _require(options.get('provider') == 'Public' and options.get('symbol') == symbol and
                 options.get('snapshot_date') == day, 'snapshot_identity_mismatch')
        observed, finished = timestamp(payload['observed_at']), timestamp(payload['collection_finished_at'])
        begin, generated = timestamp(options['collection_started_at']), timestamp(options['generated_at'])
        created = timestamp(row['created_at'])
        _require(timestamp(payload['slot_time']) == slot and start <= observed < end and
                 slot <= observed <= begin <= generated <= finished < closed and finished <= end and
                 finished <= created <= as_of, 'out_of_order_timestamps')
        _require((observed-slot).total_seconds() <= observation_age, 'stale_observation')
        underlying = payload['underlying']
        last_time = timestamp(underlying['last_timestamp'])
        _require(underlying.get('symbol') == symbol and _finite(underlying.get('last')) and underlying['last'] > 0,
                 'underlying_evidence_invalid')
        _require(opened <= last_time <= finished and (finished-last_time).total_seconds() <= quote_age,
                 'stale_underlying_observation')
        outcome.update(integrity_verified=True, observation=dict(metadata=row, quotes=[]))
        if options['status'] != 'complete':
            outcome['reasons'].append('snapshot_incomplete')
        try:
            quotes = _selected_quotes(payload, expiration, contracts, opened, closed, quote_age)
            outcome['observation']['quotes'] = quotes
            outcome['selected_expiration_verified'] = True
        except EvidenceError as exc:
            outcome['reasons'].append(str(exc))
        except Exception:
            outcome['reasons'].append('invalid_contract_evidence')
        if not outcome['reasons']:
            outcome.update(status='verified_observation', sufficient_evidence=True)
        else:
            outcome['status'] = 'partial_observation' if options['status'] != 'complete' else 'invalid_observation'
    except EvidenceError as exc:
        outcome['reasons'].append(str(exc))
        if str(exc) == 'payload_unavailable': outcome['status'] = 'unknown_observation'
        if str(exc) == 'stale_observation': outcome['status'] = 'stale_observation'
    except Exception:
        outcome['reasons'].append('invalid_snapshot_evidence')
    return outcome


def read_archive_window(client, symbol, start, end, *, expiration, contracts, as_of,
                        max_quote_age_seconds=120, max_observation_age_seconds=600):
    """Verify [start,end) slot coverage for explicit contracts in one NYSE session.

    Supports the injected Supabase SDK read interface only. Historical freshness
    is measured at observation time, never the wall clock. No fallback, prices,
    P&L, fill eligibility, portfolio state, or writes are provided.
    """
    start, end, as_of = timestamp(start), timestamp(end), timestamp(as_of)
    if symbol not in ('SPY', 'QQQ') or not start < end <= as_of:
        raise ValueError('Explicit SPY/QQQ historical window required.')
    expiration = date.fromisoformat(expiration).isoformat()
    if (not isinstance(contracts, (list, tuple)) or not 1 <= len(contracts) <= 100 or
            any(not isinstance(c, str) or not OSI.fullmatch(c) for c in contracts) or
            len(set(contracts)) != len(contracts)):
        raise ValueError('Explicit unique OSI contracts required.')
    for c in contracts:
        match = OSI.fullmatch(c)
        if match[1] != symbol or match[2] != date.fromisoformat(expiration).strftime('%y%m%d') or int(match[4]) <= 0:
            raise ValueError('Requested contract identity/expiration mismatch.')
    for value in (max_quote_age_seconds, max_observation_age_seconds):
        if not _finite(value) or not 0 < value <= 900:
            raise ValueError('Finite positive freshness policies up to 900 seconds required.')
    result = dict(version=VERSION, symbol=symbol, provider='Public', expiration=expiration,
        contracts=list(contracts), requested_start=start.isoformat(), requested_end=end.isoformat(),
        as_of=as_of.isoformat(), read_only=True, eligible_for_pnl=False, slots=[],
        policy=dict(cadence_minutes=CADENCE_MINUTES, window='[start,end)',
            max_quote_age_seconds=max_quote_age_seconds, max_observation_age_seconds=max_observation_age_seconds),
        coverage=dict(status='unknown_coverage', expected_slot_count=None, verified_slot_count=0,
            missing_slot_count=None, partial_slot_count=0, invalid_slot_count=0, unknown_slot_count=0,
            selected_expiration=dict(status='unknown_evidence', verified_slot_count=0), reasons=[]),
        lifecycle=dict(sufficient=False, reason='reader_does_not_validate_fills_or_lifecycle'))
    coverage = result['coverage']
    try:
        slots, opened, closed = _schedule(start, end)
        from modules.expiration_coverage import classify_expiration
        _require(classify_expiration(opened.date().isoformat(), expiration)['eligible_date'],
                 'expiration_outside_exchange_calendar')
    except EvidenceError as exc:
        coverage['reasons'] = [str(exc)]
        return result
    except Exception:
        coverage['reasons'] = ['session_schedule_unavailable']
        return result
    coverage['expected_slot_count'] = len(slots)
    try:
        response = (client.table('option_snapshots').select('*', count='exact').eq('provider', 'Public').eq('symbol', symbol)
            .gte('slot_time', start.isoformat()).lt('slot_time', end.isoformat())
            .order('slot_time').order('observed_at').order('id').limit(MAX_ROWS+1).execute())
        rows = response.data
        _require(type(response.count) is int and response.count == len(rows), 'metadata_response_truncated')
        _require(isinstance(rows, list) and len(rows) <= MAX_ROWS and all(isinstance(r, dict) for r in rows),
                 'metadata_response_invalid_or_truncated')
        indexed = {s: [] for s in slots}
        for row in rows:
            slot = timestamp(row['slot_time'])
            _require(slot in indexed, 'unexpected_slot')
            indexed[slot].append(row)
    except Exception:
        coverage['reasons'] = ['archive_metadata_unavailable_or_invalid']
        return result
    for slot in slots:
        matches = indexed[slot]
        if len(matches) != 1:
            outcome = dict(slot_time=slot.isoformat(), status='missing_observation' if not matches else 'invalid_observation',
                reasons=['missing_observation' if not matches else 'duplicate_observation'],
                integrity_verified=False, selected_expiration_verified=False, sufficient_evidence=False, observation=None)
        else:
            outcome = _observation(client, matches[0], symbol, slot, start, end, as_of, expiration, contracts,
                                   opened, closed, max_quote_age_seconds, max_observation_age_seconds)
        result['slots'].append(outcome)
    # Database response order is irrelevant; actual evidence must advance with slots.
    previous = None
    ids = Counter(s['observation']['metadata']['id'] for s in result['slots'] if s['observation'])
    for outcome in result['slots']:
        if not outcome['observation']:
            continue
        row = outcome['observation']['metadata']
        observed = timestamp(row['observed_at'])
        if ids[row['id']] > 1 or (previous is not None and observed <= previous):
            outcome.update(status='invalid_observation', sufficient_evidence=False,
                           selected_expiration_verified=False)
            outcome['reasons'].append('duplicate_or_out_of_order_observation')
        previous = max(previous, observed) if previous is not None else observed
    counts = Counter(s['status'] for s in result['slots'])
    verified = sum(s['sufficient_evidence'] for s in result['slots'])
    selected = sum(s['selected_expiration_verified'] for s in result['slots'])
    reasons = sorted({r for s in result['slots'] for r in s['reasons']})
    coverage.update(status='complete_window' if verified == len(slots) else
        'unknown_coverage' if counts['unknown_observation'] else 'incomplete_window',
        verified_slot_count=verified, missing_slot_count=counts['missing_observation'],
        partial_slot_count=counts['partial_observation'], unknown_slot_count=counts['unknown_observation'],
        invalid_slot_count=counts['invalid_observation']+counts['stale_observation'], reasons=reasons,
        selected_expiration=dict(status='complete_expiration_coverage' if selected == len(slots) else
            'partial_expiration_coverage' if any(r.startswith('selected_expiration') for r in reasons) or selected else
            'unknown_evidence', verified_slot_count=selected))
    return result
