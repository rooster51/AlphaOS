"""Fail-closed bridge from Phase 3 analogs to internal expiration scenarios.

This module does not authenticate archive provenance. A trusted caller must
supply verified archive metadata, timestamps, and an exchange-session schedule.
It never generates or guesses missing provenance.
"""
from datetime import date, datetime, timezone
from math import isfinite
import json
from zoneinfo import ZoneInfo

import pandas as pd
import pandas_market_calendars as mcal

from modules.historical_economics import HistoricalScenario, ScenarioEvidence
from modules.market_outcomes import HORIZONS
from modules.phase6_sample import prepared_outcomes


def _day(value):
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        raise ValueError("Invalid session date.")
    return stamp.date()


def _aware(value):
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("Trusted timestamps must include a timezone.")
    return stamp


def build_scenario_evidence(
    analog_result, *, symbol, expiration, anchor_spot, as_of,
    observed_at, max_age_seconds, archive_id, archive_checksum,
    future_exchange_sessions, completed_session_times, minimum_samples=30,
):
    """Adapt maturity-safe analogs with externally verified provenance.

    future_exchange_sessions is the *authoritative* ordered sequence of exchange
    session dates strictly after the research session, through expiration.
    completed_session_times maps historical session dates to actual timezone-aware
    completed observation timestamps; timestamps are never inferred from dates.
    The archive identifiers remain caller assertions; the calendar is rechecked.
    """
    config = analog_result["config"]
    target = analog_result["target"]
    if not all(isinstance(v, str) and v.strip() for v in
               (symbol, archive_id, archive_checksum, observed_at, as_of)):
        raise ValueError("Verified identity, archive provenance and timestamps required.")
    if not isinstance(completed_session_times, dict) or not completed_session_times:
        raise ValueError("Verified historical completion timestamps required.")
    if type(minimum_samples) is not int or minimum_samples < 2:
        raise ValueError("Invalid sample coverage policy.")
    if type(max_age_seconds) not in (int, float) or not isfinite(max_age_seconds) or max_age_seconds < 0:
        raise ValueError("Invalid archive freshness policy.")
    cutoff = _aware(as_of)
    observed = _aware(observed_at)
    if not 0 <= (cutoff - observed).total_seconds() <= max_age_seconds:
        raise ValueError("Stale or future archive observation.")
    if symbol != config["symbol"] or symbol != target["symbol"]:
        raise ValueError("Analog symbol mismatch.")
    if not isfinite(float(anchor_spot)) or float(anchor_spot) <= 0:
        raise ValueError("Positive anchor spot required.")
    if abs(float(target["close"]) - float(anchor_spot)) > 1e-8:
        raise ValueError("Analog anchor spot mismatch.")
    horizon = config["horizon"]
    if horizon not in HORIZONS:
        raise ValueError("Unsupported analog horizon.")
    target_day = _day(target["date"])
    if target_day > observed.astimezone(timezone.utc).date():
        raise ValueError("Analog target is after archive observation.")
    if target_day > cutoff.astimezone(timezone.utc).date():
        raise ValueError("Analog target is after research cutoff.")
    if "target_date" in config and _day(config["target_date"]) != target_day:
        raise ValueError("Analog selection target mismatch.")
    expiry = date.fromisoformat(expiration)
    calendar = mcal.get_calendar('NYSE')
    schedule = calendar.schedule(start_date=target_day, end_date=expiry)
    if schedule.empty or schedule.index[0].date() != target_day:
        raise ValueError('Target is not an exchange session.')
    if (target_day != cutoff.astimezone(ZoneInfo('America/New_York')).date()
            or cutoff < schedule.iloc[0]['market_close'].to_pydatetime()):
        raise ValueError('Completed-session expiration alignment required.')
    future = tuple(_day(s) for s in future_exchange_sessions)
    if not future or len(set(future)) != len(future) or tuple(sorted(future)) != future:
        raise ValueError("Authoritative future exchange sessions required.")
    if future[0] <= cutoff.date() or future[-1] != expiry:
        raise ValueError("Session calendar does not end at expiration.")
    if len(future) != horizon:
        raise ValueError("Expiration and analog trading-session horizons differ.")
    if future != tuple(x.date() for x in schedule.index[1:]):
        raise ValueError('Future sessions disagree with NYSE calendar.')

    frame = prepared_outcomes(analog_result, horizon)
    sessions = tuple(_day(s) for s in analog_result["session_dates"])
    if len(set(sessions)) != len(sessions) or tuple(sorted(sessions)) != sessions:
        raise ValueError("Historical session sequence must be unique and chronological.")
    positions = {day: i for i, day in enumerate(sessions)}
    history_schedule = calendar.schedule(start_date=sessions[0], end_date=sessions[-1])
    if sessions != tuple(x.date() for x in history_schedule.index):
        raise ValueError('Historical session sequence has exchange gaps or non-session dates.')
    scenarios = []
    for row in frame.itertuples(index=False):
        value = row.terminal_return
        if pd.isna(value):
            continue
        origin = _day(row.date)
        end_position = positions[origin] + horizon
        if end_position >= len(sessions):
            raise ValueError("Missing historical outcome completion session.")
        completion_day = sessions[end_position]
        timestamp = completed_session_times.get(completion_day.isoformat())
        if not timestamp:
            raise ValueError("Missing verified outcome completion timestamp.")
        completed = _aware(timestamp)
        market_close = history_schedule.loc[str(completion_day), 'market_close'].to_pydatetime()
        if (completed.astimezone(timezone.utc).date() != completion_day
                or completed < market_close or completed > cutoff):
            raise ValueError("Historical outcome not matured at observed cutoff.")
        scenarios.append(HistoricalScenario(
            observation_id=origin.isoformat(),
            terminal_return=float(value),
            completed_at=completed.isoformat(),
        ))
    if len(scenarios) < minimum_samples:
        raise ValueError("Insufficient maturity-safe historical analogs.")
    return ScenarioEvidence(
        symbol=symbol, expiration=expiration, anchor_spot=float(anchor_spot),
        observed_at=observed.isoformat(), as_of=cutoff.isoformat(),
        max_age_seconds=float(max_age_seconds), horizon_sessions=horizon,
        expiration_sessions=len(future),
        source="caller-supplied-archive:" + archive_id + ":" + archive_checksum,
        selection_method="phase3:" + json.dumps(config, sort_keys=True, default=str),
        scenarios=tuple(scenarios),
        history_as_of=cutoff.isoformat(),
    )
