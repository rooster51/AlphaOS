"""Resolve selected contracts from a server-verified archive, never client quotes.

Verification is point-in-time archive/identity/quote integrity, not a firm fill,
future price guarantee, probability model or broker buying-power assessment.
"""
from copy import deepcopy
from decimal import Decimal
from math import isclose, isfinite
import re
from zoneinfo import ZoneInfo

from modules.market_archive_adapter import normalize_archive_snapshot
from modules.opportunity_classifier import aware_time

VERSION = 'structure-market-data-v1'
QUOTE_MAX_AGE_SECONDS = 900


class ProvenanceError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def hypothetical_evidence():
    return dict(version=VERSION, kind='hypothetical', verified=False,
        verified_for_trading=False, reason='user_supplied_cashflow', legs=[])


def resolve_structure(request, record, now):
    """Only call with the trusted read_latest_option_snapshot result.

    References pin the latest snapshot; rollover rejects rather than reprices.
    A strategy uses a single snapshot, underlying and expiration. Both sides of
    every selected quote must be usable at request time. Partial archives are
    allowed only when all selected legs pass; rejected rows are never eligible.
    """
    def require(condition, code='market_data_integrity_error'):
        if not condition:
            raise ProvenanceError(code)

    meta, payload = record['metadata'], record['payload']
    reference = request.market_data
    require(meta['id'] == reference.snapshot_id and
        meta['archive_sha256'] == reference.archive_sha256, 'archive_snapshot_mismatch')
    require(meta['symbol'] == request.symbol and payload['symbol'] == request.symbol)
    require(request.as_of == now.astimezone(ZoneInfo('America/New_York')).date(), 'market_data_date_mismatch')
    require(meta['session_date'] == request.as_of.isoformat(), 'market_data_date_mismatch')
    normalized = normalize_archive_snapshot(payload, request.expiration.isoformat())
    spot = normalized['market_research']['spot']
    require(isclose(request.spot, spot, rel_tol=0, abs_tol=1e-8), 'market_data_spot_mismatch')
    underlying_at = aware_time(payload['underlying'].get('last_timestamp'))
    collection_end = aware_time(payload.get('collection_finished_at') or payload['observed_at'])
    require(underlying_at is not None and
        underlying_at <= collection_end and
        0 <= (now-underlying_at).total_seconds() <= QUOTE_MAX_AGE_SECONDS, 'market_quote_stale')
    all_rows = [row for bucket in ('valid_contracts','questionable_contracts','rejected_contracts')
        for row in payload['options'].get(bucket, []) if isinstance(row, dict)]
    rows = normalized['chain']['calls'] + normalized['chain']['puts']
    selected, identifiers = [], set()
    total = Decimal(0)
    for leg in request.legs:
        require(leg.contract not in identifiers, 'market_contract_mismatch')
        identifiers.add(leg.contract)
        require(sum(row.get('contract') == leg.contract for row in all_rows) == 1, 'market_contract_mismatch')
        matches = [row for row in rows if row.get('contract') == leg.contract]
        require(len(matches) == 1, 'market_contract_mismatch')
        row = matches[0]
        match = re.fullmatch(r'([A-Z]{1,6})\s*(\d{6})([CP])(\d{8})', leg.contract)
        require(match is not None, 'market_contract_mismatch')
        require(match[1] == request.symbol and match[2] == request.expiration.strftime('%y%m%d') and
            match[3] == leg.type[0] and int(match[4])/1000 == leg.strike and
            row['type'] == leg.type and row['strike'] == leg.strike and
            row['expiration'] == request.expiration.isoformat(), 'market_contract_mismatch')
        bid, ask = row.get('bid'), row.get('ask')
        require(all(isinstance(x, (int,float)) and not isinstance(x,bool) and isfinite(x) for x in (bid,ask))
            and 0 <= bid <= ask and ask > 0, 'market_quote_invalid')
        ages = {}
        for side in ('bid','ask'):
            timestamp = aware_time(row.get(side+'_timestamp'))
            require(timestamp is not None, 'market_quote_invalid')
            age = (now-timestamp).total_seconds()
            require(0 <= age <= QUOTE_MAX_AGE_SECONDS, 'market_quote_stale')
            ages[side+'_age_seconds'] = age
        price = ask if leg.qty > 0 else bid
        total -= Decimal(str(price))*leg.qty
        selected.append(dict(type=leg.type, strike=leg.strike, qty=leg.qty,
            symbol=request.symbol, expiration=request.expiration.isoformat(), contract=leg.contract,
            bid=bid, ask=ask, bid_timestamp=row['bid_timestamp'], ask_timestamp=row['ask_timestamp'],
            observation_timestamp=row.get('observation_timestamp'), archive_quality=row['archive_quality'],
            quality_warnings=deepcopy(row.get('quality_warnings') or []),
            entry_side='ask' if leg.qty > 0 else 'bid', entry_price=price,
            snapshot_id=meta['id'], freshness=dict(evaluated_at=now.isoformat(),
                max_age_seconds=QUOTE_MAX_AGE_SECONDS, **ages)))
    credit = float(total)
    require(isclose(credit, request.credit, rel_tol=0, abs_tol=1e-8), 'market_data_cashflow_mismatch')
    snapshot = {key:meta.get(key) for key in ('id','provider','symbol','observed_at','session_date',
        'archive_path','archive_sha256','quality_status','slot_time','created_at')}
    evidence = dict(version=VERSION, kind='verified_archive', verified=True, verified_for_trading=False,
        snapshot=snapshot, archive_freshness=deepcopy(record['freshness']),
        evaluated_at=now.isoformat(), underlying=dict(spot=spot, timestamp=underlying_at.isoformat()),
        pricing='natural_bid_ask', signed_package_cashflow=credit, fees=request.fees,
        legs=selected, caveats=['Archived observations are not executable fills.',
            'Provider quote delay and broker margin are not certified.',
            'Fees are user-supplied total package dollars.'])
    return selected, evidence
