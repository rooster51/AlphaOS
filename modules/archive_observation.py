"""Observation-only projection; never claim candidate or historical research ran."""
from datetime import date
from zoneinfo import ZoneInfo

from modules.market_archive_adapter import normalize_archive_snapshot
from modules.market_session_gate import regular_session_bounds
from modules.opportunity_classifier import aware_time

VERSION = 'alphaos-observation-v1'


def archive_observation(record, *, symbol, now, mode, expiration=None):
    # Same trusted reader and adapter as full research: checksum, identity,
    # timestamp/contract exclusions and exact expiration selection still apply.
    payload = record['payload']
    if payload.get('symbol') != symbol:
        raise ValueError('Archive symbol mismatch.')
    archived = normalize_archive_snapshot(payload, expiration)
    observed = aware_time(archived['observed_at'])
    finished = aware_time(payload.get('collection_finished_at') or payload.get('options',{}).get('generated_at'))
    if observed > now or (finished and finished > now):
        raise ValueError('Future archive evidence.')
    bounds = regular_session_bounds(observed)
    if bounds is None or not bounds[0] <= observed < bounds[1]:
        raise ValueError('Archive observation outside exchange session.')
    if mode == 'current' and date.fromisoformat(archived['expiration']) < now.astimezone(ZoneInfo('America/New_York')).date():
        raise ValueError('Expired current archive.')
    return dict(schema_version=VERSION, read_only=True, verified_for_trading=False,
        research_performed=False, evidence_scope='archive_observation_only',
        symbol=symbol, research_mode=mode, as_of=archived['observed_at'],
        requested_as_of=now.isoformat(), expiration=archived['expiration'],
        spot=archived['market_research']['spot'],
        session=dict(open=bounds[0].isoformat(), close=bounds[1].isoformat()),
        archive=dict(provider=archived['provider'], session_date=archived['session_date'],
            observation={k:v for k,v in archived['market_research']['archive_observation'].items()
                if k in ('provider','options_status','observed_at','slot_time','collection_finished_at',
                    'underlying_last_timestamp','quote_timing','quality_warnings','expiration_failures')},
            storage=record.get('metadata'), freshness=record.get('freshness'),
            diagnostics=archived['diagnostics']),
        caveats=['Archive underlying observation, not an executable quote or current-price guarantee.',
                 'No history, classifications, candidates, payoff economics, capital eligibility, POP or EV were calculated.',
                 'Historical mode retains the original observation time; it is not current market evidence.'])
