"""Versioned transport projection; never filters, ranks or recomputes economics.

Details are recomputed against the verified latest archive, not cached. A pinned
archive checksum and whole-candidate digest prevent substituting newer evidence.
"""
from collections import Counter
from hashlib import sha256
import json
import orjson

from modules.research_control import checkpoint
from .contracts import APIError

FORMAT = 'summary-v1'
MAX_SUMMARY_BYTES = 2 * 1024 * 1024


def candidate_digest(value):
    # Internal canonical hash input only, never response bytes. Standard JSON
    # distinguishes infinity from None without another recursive object copy.
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, default=_date).encode()).hexdigest()


def _date(value):
    from datetime import date, datetime
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError('Unsupported candidate value')


def candidate_summary(entry):
    result = dict(entry)
    research = entry.get('research')
    if not isinstance(research, dict):
        return result
    research = dict(research)
    position, trade = research.pop('position', {}), research.pop('trade', {})
    research['legs'] = position.get('legs', research.get('legs', trade.get('legs', [])))
    research.setdefault('expiration', position.get('expiration', trade.get('expiration')))
    research.setdefault('strategy_family', trade.get('strategy_family', trade.get('strategy')))
    research.setdefault('entry_debit', research.get('premium_per_share'))
    # Full payoff samples, repeated trade/position identities and supporting
    # economics are available through detail. Keep gate inputs in the summary.
    research.pop('payoff', None)
    research.pop('caveats', None)
    economics = research.get('historical_economics')
    if isinstance(economics, dict):
        research['historical_economics'] = {key: value for key, value in economics.items()
            if key in ('version', 'capital_requirement', 'capital_eligibility',
                'eligible_for_consideration', 'eligibility', 'missing_evidence',
                'research_only_reasons', 'historical_evidence_status', 'holding_period',
                'temporal_basis', 'provenance')}
    result['research'] = research
    return result


def summarize(envelope):
    research = envelope['research']
    session = research['research_session']
    checksum = research['archive']['storage']['archive_sha256']
    projected = dict(session)
    for bucket in ('candidates', 'excluded'):
        entries = []
        for index, entry in enumerate(session[bucket]):
            checkpoint()
            row = candidate_summary(entry) if bucket == 'candidates' else {
                key: value for key, value in entry.items() if key != 'research'}
            if bucket == 'excluded' and isinstance(entry.get('research'), dict):
                row['strategy_family'] = entry['research'].get('strategy_family')
            row['detail'] = dict(bucket=bucket, index=index,
                candidate_sha256=candidate_digest(entry), archive_sha256=checksum)
            entries.append(row)
        projected[bucket] = entries
    projected['transport'] = dict(format=FORMAT, complete=True,
        candidate_count=len(session['candidates']), excluded_count=len(session['excluded']),
        exclusion_counts=dict(Counter(row.get('reason', 'unspecified') for row in session['excluded'])),
        detail_fields=['complete candidate', 'payoff grid', 'trade and position',
            'candidate caveats', 'complete historical economics', 'excluded candidate evidence'],
        detail_policy='Recomputed verified evidence; changed archive or candidate returns 409. No cached research.')
    result = dict(envelope, response_format=FORMAT,
        research=dict(research, research_session=projected))
    # Bound the wire response, never silently discard a qualifying candidate.
    if len(orjson.dumps(result, default=_date)) > MAX_SUMMARY_BYTES:
        raise APIError('research_summary_too_large', 503)
    return result


def select_detail(envelope, reference):
    if envelope['research']['archive']['storage']['archive_sha256'] != reference.archive_sha256:
        raise APIError('research_evidence_changed', 409)
    entries = envelope['research']['research_session'][reference.bucket]
    if reference.index >= len(entries) or candidate_digest(entries[reference.index]) != reference.candidate_sha256:
        raise APIError('research_evidence_changed', 409)
    return dict(schema_version='alphaos-candidate-detail-v1', read_only=True,
        verified_for_trading=False, request=envelope['request'],
        archive=envelope['research']['archive'],
        reference=reference.model_dump(), candidate=entries[reference.index],
        caveats=envelope['caveats'])
