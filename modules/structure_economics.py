"""Trusted completed-session economics for explicit structure research.

Uses the existing archive reader, daily dataset builder and Phase 3 selector.
Date-only explicit requests mean completed-session historical scenarios, never
an implied intraday fill or a current quote. No writes or alternate providers.
"""
from datetime import date, timedelta
from math import isfinite

import pandas as pd
import pandas_market_calendars as mcal

from modules.historical_analogs import analog_research
from modules.market_state_research import build_research_dataset
from modules.market_outcomes import HORIZONS
from modules.historical_economics import evaluate_historical_economics
from modules.trusted_historical_adapter import build_scenario_evidence


def structure_historical_economics(position, *, as_of, now, read_snapshot, history_loader):
    trade = position['trade']
    result = evaluate_historical_economics(trade, as_of=as_of)
    result['integration_version'] = 'structure-historical-v1'
    result['temporal_basis'] = 'Explicit as_of completed NYSE session; historical, not live'
    result['provenance'] = {'verification': 'unavailable', 'pricing': 'caller-supplied scenario'}

    def unavailable(reason):
        result['missing_evidence'] = [reason]
        return result

    calendar = mcal.get_calendar('NYSE')
    day, expiration = date.fromisoformat(as_of), date.fromisoformat(trade['expiration'])
    schedule = calendar.schedule(start_date=day, end_date=expiration)
    if schedule.empty or schedule.index[0].date() != day:
        return unavailable('as_of_not_exchange_session')
    if schedule.index[-1].date() != expiration:
        return unavailable('expiration_not_exchange_session')
    cutoff = schedule.iloc[0]['market_close'].to_pydatetime()
    if now < cutoff:
        return unavailable('as_of_session_not_complete')
    horizon = len(schedule)-1
    if horizon not in HORIZONS:
        return unavailable('unsupported_expiration_session_horizon')
    try:
        record = read_snapshot(trade['symbol'], cutoff.isoformat())
        payload, metadata, freshness = record['payload'], record['metadata'], record['freshness']
        observed = pd.Timestamp(payload['observed_at'])
        maximum = float(freshness['max_age_seconds'])
        if (observed.tzinfo is None or not isfinite(maximum) or maximum < 0
                or not 0 <= (cutoff-observed).total_seconds() <= maximum
                or pd.Timestamp(freshness['as_of']) != cutoff
                or payload['symbol'] != trade['symbol'] or metadata['symbol'] != trade['symbol']
                or payload['provider'] != 'Public' or metadata['provider'] != 'Public'
                or payload['session'] != as_of or str(metadata['session_date']) != as_of
                or pd.Timestamp(metadata['observed_at']) != observed
                or pd.Timestamp(metadata['created_at']) > cutoff):
            return unavailable('archive_context_mismatch')
        archive_id, checksum, archive_path = str(metadata['id']), metadata['archive_sha256'], metadata['archive_path']
        if not archive_id or not isinstance(checksum,str) or len(checksum) != 64:
            return unavailable('archive_provenance_incomplete')
    except Exception:
        return unavailable('verified_archive_unavailable')
    # These provenance facts are supplied only by the server's verified reader.
    result['provenance'] = dict(verification='server_verified_archive_reader',
        archive_id=archive_id, archive_sha256=checksum, archive_path=archive_path,
        slot_time=payload.get('slot_time'), observed_at=observed.isoformat(),
        collection_finished_at=payload.get('collection_finished_at'),
        research_cutoff=cutoff.isoformat(), request_time=now.isoformat(),
        archive_age_at_cutoff_seconds=(cutoff-observed).total_seconds(),
        archive_age_at_request_seconds=(now-observed).total_seconds(),
        quote_age_seconds=None, pricing='caller-supplied spot and premium; not verified market quotes')
    try:
        history = history_loader(trade['symbol'])
        dates = pd.to_datetime(history['date'], utc=True).dt.date
        history = history.loc[dates <= day].copy()
        historical_schedule = calendar.schedule(start_date=dates.min(), end_date=day)
        dataset = build_research_dataset(history, day+timedelta(days=1),
            expected_sessions=historical_schedule.index)
        if dataset['features'].iloc[-1]['date'].date() != day:
            return unavailable('as_of_history_unavailable')
        # No silent reanchoring: the explicit spot must match the research close.
        if abs(float(dataset['features'].iloc[-1]['close'])-trade['spot']) > 1e-8:
            return unavailable('scenario_spot_differs_from_completed_close')
        analog = analog_research(dataset['features'], dataset['outcomes'],
            target_date=as_of, horizon=horizon, method='tolerance')
        if len(analog['analogs']) < 30:
            return unavailable('insufficient_analog_history')
        completion_times = {index.date().isoformat(): row['market_close'].isoformat()
                            for index,row in historical_schedule.iterrows()}
        evidence = build_scenario_evidence(analog, symbol=trade['symbol'],
            expiration=trade['expiration'], anchor_spot=trade['spot'],
            as_of=cutoff.isoformat(), observed_at=observed.isoformat(),
            max_age_seconds=maximum, archive_id=archive_id, archive_checksum=checksum,
            future_exchange_sessions=schedule.index[1:], completed_session_times=completion_times)
    except Exception:
        return unavailable('historical_evidence_validation_failed')
    economics = evaluate_historical_economics(trade, as_of=as_of, evidence=evidence)
    economics.update(integration_version=result['integration_version'],
        temporal_basis=result['temporal_basis'], provenance=result['provenance'])
    economics['provenance']['history_ohlc_sha256'] = dataset['metadata']['source_ohlc_sha256']
    economics['provenance']['history_completion_basis'] = 'Public completed daily bars; NYSE close bounds, not quote timestamps'
    economics['provenance']['history_cutoff'] = cutoff.isoformat()
    return economics
