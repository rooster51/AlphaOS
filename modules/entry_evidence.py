"""Deterministic entry-evidence record for verified archive-backed structures.

Trust boundary: `modules.structure_provenance` (PR #68) owns archive verification
— the snapshot read, checksum comparison, OSI/snapshot identity, bid/ask
usability and quote ages. This module never opens the archive, never fetches
anything and never re-derives a quote, so it cannot weaken those checks. It
validates that the verified payload is internally consistent, binds it to the
already-researched trade, and emits one immutable record for later outcome work.

The module is pure: no network, database, filesystem or clock access, and no
mutation of its arguments. The reference instant is the payload's own
`evaluated_at`, supplied by the verifying server, never read locally.

This is an entry record only. It contains no exit, settlement, probability,
expected value, ranking or persistence, and it cannot promote evidence to
trade-ready: `verified_for_trading` is required to remain false.
"""
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
from math import isclose, isfinite
import re
from zoneinfo import ZoneInfo

VERSION = 'entry-evidence-v1'
EVIDENCE_VERSION = 'structure-market-data-v1'
MULTIPLIER = 100
QUOTE_MAX_AGE_SECONDS = 900
NEW_YORK = ZoneInfo('America/New_York')
OSI = re.compile(r'([A-Z]{1,6})\s*(\d{6})([CP])(\d{8})')


class EntryEvidenceError(ValueError):
    """Stable, quotable rejection reason. Never carries payload contents."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _require(condition, code):
    if not condition:
        raise EntryEvidenceError(code)


def _number(value, code):
    _require(isinstance(value, (int, float)) and not isinstance(value, bool)
        and isfinite(value), code)
    return float(value)


def _instant(value, code):
    _require(isinstance(value, str) and value, code)
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise EntryEvidenceError(code) from None
    _require(parsed.tzinfo is not None and parsed.utcoffset() is not None, code)
    return parsed


def _decimal(value):
    return Decimal(str(value))


def _fingerprint(record):
    canonical = json.dumps(record, sort_keys=True, allow_nan=False, separators=(',', ':'))
    return sha256(canonical.encode('utf-8')).hexdigest()


def _quote_ceiling(evidence):
    """The verifier's own age policy, never a wider default of our own."""
    ceiling = QUOTE_MAX_AGE_SECONDS
    legs = evidence.get('legs')
    if isinstance(legs, list) and legs and isinstance(legs[0], dict):
        freshness = legs[0].get('freshness')
        if isinstance(freshness, dict):
            reported = freshness.get('max_age_seconds')
            if isinstance(reported, (int, float)) and not isinstance(reported, bool):
                ceiling = float(reported)
    _require(isfinite(ceiling) and 0 < ceiling <= QUOTE_MAX_AGE_SECONDS,
        'entry_quote_invalid')
    return ceiling


def _validated_snapshot(evidence, trade, now):
    snapshot = evidence.get('snapshot')
    _require(isinstance(snapshot, dict), 'entry_snapshot_incomplete')
    for key in ('id', 'provider', 'symbol', 'observed_at', 'session_date',
                'archive_path', 'archive_sha256', 'quality_status', 'created_at'):
        _require(isinstance(snapshot.get(key), str) and snapshot[key], 'entry_snapshot_incomplete')
    _require(re.fullmatch(r'[a-f0-9]{64}', snapshot['archive_sha256']) is not None,
        'entry_snapshot_mismatch')
    _require(snapshot['symbol'] == trade['symbol'], 'entry_snapshot_mismatch')
    try:
        session = datetime.fromisoformat(snapshot['session_date']).date().isoformat()
    except ValueError:
        raise EntryEvidenceError('entry_snapshot_mismatch') from None
    _require(session == snapshot['session_date'], 'entry_snapshot_mismatch')
    # An entry cannot post-date the expiration it belongs to.
    _require(session <= trade['expiration'], 'entry_snapshot_mismatch')
    observed = _instant(snapshot['observed_at'], 'entry_timestamp_invalid')
    created = _instant(snapshot['created_at'], 'entry_timestamp_invalid')
    if snapshot.get('slot_time') is not None:
        slot = _instant(snapshot['slot_time'], 'entry_timestamp_invalid')
        _require(slot <= observed, 'entry_timestamp_invalid')
    _require(observed <= created <= now, 'entry_timestamp_invalid')
    _require(observed.astimezone(NEW_YORK).date().isoformat() == session,
        'entry_snapshot_mismatch')
    return snapshot, observed, created


def _validated_legs(evidence, trade, now, max_age, snapshot_id):
    legs = evidence.get('legs')
    trade_legs = trade.get('legs')
    _require(isinstance(legs, list) and 1 <= len(legs) <= 4, 'entry_leg_count_mismatch')
    _require(isinstance(trade_legs, list) and len(trade_legs) == len(legs),
        'entry_leg_count_mismatch')
    osi_date = trade['expiration'][2:4] + trade['expiration'][5:7] + trade['expiration'][8:10]
    contracts, normalized = set(), []
    for index, (leg, expected) in enumerate(zip(legs, trade_legs)):
        _require(isinstance(leg, dict) and isinstance(expected, dict), 'entry_leg_count_mismatch')
        contract = leg.get('contract')
        _require(isinstance(contract, str) and contract, 'entry_contract_missing')
        match = OSI.fullmatch(contract)
        _require(match is not None, 'entry_contract_invalid')
        _require(contract not in contracts, 'entry_contract_duplicate')
        contracts.add(contract)
        _require(match[1] == trade['symbol'], 'entry_contract_mismatch')
        _require(match[2] == osi_date, 'entry_contract_mismatch')
        # One package, one snapshot: a leg citing another snapshot would silently
        # mix two observations into a record that claims to be point-in-time.
        _require(leg.get('snapshot_id') == snapshot_id, 'entry_snapshot_mismatch')
        _require(leg.get('symbol') == trade['symbol'], 'entry_contract_mismatch')
        _require(leg.get('expiration') == trade['expiration'], 'entry_contract_mismatch')
        leg_type = leg.get('type')
        strike = _number(leg.get('strike'), 'entry_contract_mismatch')
        qty = leg.get('qty')
        _require(leg_type in ('Call', 'Put') and type(qty) is int and qty != 0
            and abs(qty) <= 100, 'entry_leg_count_mismatch')
        _require(match[3] == leg_type[0] and int(match[4]) / 1000 == strike,
            'entry_contract_mismatch')
        _require(leg_type == expected.get('type'), 'entry_leg_mismatch')
        _require(isclose(strike, _number(expected.get('strike'), 'entry_leg_mismatch'),
            rel_tol=0, abs_tol=1e-9), 'entry_leg_mismatch')
        _require(qty == expected.get('qty'), 'entry_leg_mismatch')
        _require(leg.get('archive_quality') in ('valid_contracts', 'questionable_contracts'),
            'entry_contract_invalid')
        bid = _number(leg.get('bid'), 'entry_quote_invalid')
        ask = _number(leg.get('ask'), 'entry_quote_invalid')
        _require(0 <= bid <= ask and ask > 0, 'entry_quote_invalid')
        side, price = ('ask', ask) if qty > 0 else ('bid', bid)
        _require(leg.get('entry_side') == side, 'entry_quote_invalid')
        _require(isclose(_number(leg.get('entry_price'), 'entry_quote_invalid'), price,
            rel_tol=0, abs_tol=1e-9), 'entry_quote_invalid')
        freshness = leg.get('freshness')
        _require(isinstance(freshness, dict), 'entry_quote_invalid')
        ages = {}
        for name in ('bid', 'ask'):
            stamp = _instant(leg.get(name + '_timestamp'), 'entry_quote_invalid')
            _require(stamp <= now, 'entry_timestamp_invalid')
            age = (now - stamp).total_seconds()
            _require(age <= max_age, 'entry_quote_stale')
            reported = freshness.get(name + '_age_seconds')
            _require(isinstance(reported, (int, float)) and not isinstance(reported, bool)
                and abs(float(reported) - age) <= 1e-6, 'entry_quote_invalid')
            ages[name + '_age_seconds'] = age
        normalized.append(dict(index=index, type=leg_type, strike=strike, qty=qty,
            contract=contract, entry_side=side, entry_price=price, bid=bid, ask=ask,
            bid_timestamp=leg['bid_timestamp'], ask_timestamp=leg['ask_timestamp'],
            archive_quality=leg['archive_quality'],
            quality_warnings=list(leg.get('quality_warnings') or []), **ages))
    return normalized


def build_entry_record(trade, evidence):
    """Bind verified archive evidence to one researched trade as an entry record.

    `trade` is the already-normalized option trade (symbol, expiration, spot,
    signed package credit, fees, legs with type/strike/qty/contract). `evidence`
    is the `market_data` object produced by the trusted verifier. Prices, fees
    and cashflow are echoed unchanged so the existing payoff economics remain the
    only source of economics; nothing is repriced or reconstructed here.
    """
    _require(isinstance(trade, dict) and isinstance(evidence, dict), 'entry_payload_invalid')
    _require(evidence.get('version') == EVIDENCE_VERSION
        and evidence.get('kind') == 'verified_archive', 'entry_evidence_not_verified')
    _require(evidence.get('verified') is True, 'entry_evidence_not_verified')
    # A record must never become a claim of executable or trade-ready evidence.
    _require(evidence.get('verified_for_trading') is False, 'entry_trade_ready_claim')
    _require(evidence.get('pricing') == 'natural_bid_ask', 'entry_pricing_unsupported')

    _require(trade.get('shares', 0) in (0, None), 'entry_shares_unsupported')
    _require(trade.get('multiplier', MULTIPLIER) == MULTIPLIER, 'entry_multiplier_unsupported')
    symbol = trade.get('symbol')
    expiration = trade.get('expiration')
    _require(isinstance(symbol, str) and symbol, 'entry_snapshot_mismatch')
    _require(isinstance(expiration, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', expiration),
        'entry_snapshot_mismatch')
    spot = _number(trade.get('spot'), 'entry_snapshot_mismatch')
    _require(spot > 0, 'entry_snapshot_mismatch')

    now = _instant(evidence.get('evaluated_at'), 'entry_timestamp_invalid')
    max_age = _quote_ceiling(evidence)

    snapshot, _observed, collection_end = _validated_snapshot(evidence, trade, now)
    underlying = evidence.get('underlying')
    _require(isinstance(underlying, dict), 'entry_snapshot_mismatch')
    underlying_spot = _number(underlying.get('spot'), 'entry_snapshot_mismatch')
    _require(isclose(underlying_spot, spot, rel_tol=0, abs_tol=1e-8), 'entry_spot_mismatch')
    underlying_at = _instant(underlying.get('timestamp'), 'entry_timestamp_invalid')
    _require(underlying_at <= now, 'entry_timestamp_invalid')
    # The spot may be captured after chain collection started; it may not post-date
    # collection completion, which is the bound the verifier itself uses.
    _require(underlying_at <= collection_end, 'entry_timestamp_invalid')
    underlying_age = (now - underlying_at).total_seconds()
    _require(underlying_age <= max_age, 'entry_quote_stale')

    legs = _validated_legs(evidence, trade, now, max_age, snapshot['id'])

    cashflow = sum(-_decimal(leg['entry_price']) * leg['qty'] for leg in legs)
    reported = _number(evidence.get('signed_package_cashflow'), 'entry_cashflow_mismatch')
    credit = _number(trade.get('credit'), 'entry_cashflow_mismatch')
    _require(abs(float(cashflow) - reported) <= 1e-8, 'entry_cashflow_mismatch')
    _require(abs(float(cashflow) - credit) <= 1e-8, 'entry_cashflow_mismatch')

    fees = _number(trade.get('fees', 0), 'entry_fees_invalid')
    _require(fees >= 0, 'entry_fees_invalid')
    _require(isclose(_number(evidence.get('fees', 0), 'entry_fees_invalid'), fees,
        rel_tol=0, abs_tol=1e-8), 'entry_fees_invalid')

    freshness = evidence.get('archive_freshness')
    archive_age = None
    if isinstance(freshness, dict) and isinstance(freshness.get('age_seconds'), (int, float)):
        archive_age = float(freshness['age_seconds'])
        _require(isfinite(archive_age) and archive_age >= 0, 'entry_snapshot_incomplete')

    record = dict(
        version=VERSION, record_type='entry', evidence_version=EVIDENCE_VERSION,
        symbol=symbol, expiration=expiration, session_date=snapshot['session_date'],
        multiplier=MULTIPLIER, shares=0, spot=spot,
        underlying_timestamp=underlying_at.isoformat(),
        pricing='natural_bid_ask', signed_package_cashflow=float(cashflow), fees=fees,
        snapshot=dict(id=snapshot['id'], provider=snapshot['provider'],
            symbol=snapshot['symbol'], session_date=snapshot['session_date'],
            observed_at=snapshot['observed_at'], slot_time=snapshot.get('slot_time'),
            created_at=snapshot['created_at'], archive_path=snapshot['archive_path'],
            archive_sha256=snapshot['archive_sha256'],
            quality_status=snapshot['quality_status']),
        verification=dict(evaluated_at=now.isoformat(), quote_max_age_seconds=max_age,
            underlying_age_seconds=underlying_age, archive_age_seconds=archive_age),
        legs=legs,
        research_only=True, verified_for_trading=False,
        caveats=['Archived observations are not executable fills.',
            'Entry evidence only; no settlement, probability or expected value.',
            'Fees are user-supplied total package dollars, not certified costs.',
            'The existing payoff engine remains the only source of economics.'])
    record['fingerprint'] = _fingerprint(record)
    return record
