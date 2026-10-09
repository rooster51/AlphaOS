"""Read-only AlphaOS 2.0 orchestration for one persisted market snapshot."""
from copy import deepcopy
from datetime import date
from zoneinfo import ZoneInfo

from modules.market_archive_adapter import normalize_archive_snapshot
from modules.opportunity_classifier import aware_time, classify_opportunity, expected_move_context, history_evidence
from modules.opportunity_session import research_market_opportunities
from modules.market_session_gate import regular_session_bounds
from modules.structure_economics import compare_historical_economics

VERSION = "alphaos-run-market-v1"


def run_market(payload, *, expiration=None, history=None, session_context=None,
               expected_move=None, expected_move_horizon=None,
               available_capital=None, objective=None, width=5, late_minutes=60):
    """Research one archive snapshot without provider calls, persistence or execution."""
    archived = normalize_archive_snapshot(payload, expiration)
    bounds = regular_session_bounds(aware_time(archived['observed_at']))
    if bounds is None:
        raise ValueError('Archive date is not an NYSE session.')
    authoritative_session = {'open': bounds[0].isoformat(), 'close': bounds[1].isoformat()}
    if not bounds[0] <= aware_time(archived['observed_at']) < bounds[1]:
        raise ValueError('Archive observation is outside the NYSE regular session.')
    if session_context is not None and any(
            aware_time(session_context.get(k)) != aware_time(v) for k, v in authoritative_session.items()):
        raise ValueError('Supplied session disagrees with the archive calendar.')
    session_context = authoritative_session
    evidence = {}
    if history is not None:
        try:
            evidence = history_evidence(history, archived["symbol"], archived["observed_at"])
        except (ValueError, RuntimeError):
            evidence = {"unavailable": "Completed market history unavailable or invalid."}
    else:
        evidence = {"unavailable": "Completed market history was not supplied."}

    state = classify_opportunity(
        evidence, observed_at=archived["observed_at"], expiration=archived["expiration"],
        session=session_context, late_minutes=late_minutes,
    )
    em_context, comparable_em = expected_move_context(
        expected_move, expected_move_horizon, archived["observed_at"], archived["expiration"],
    )
    market = deepcopy(archived["market_research"])
    market["opportunity_state"] = state
    market["classification_evidence"] = evidence
    market["classification_source"] = "classifier"
    market["expected_move_evidence"] = em_context
    market["expected_move"] = comparable_em

    research = research_market_opportunities(
        archived["symbol"], market, archived["chain"], as_of=archived["observed_at"],
        expiration=archived["expiration"], available_capital=available_capital,
        objective=objective, width=width,
    )
    attach_market_economics(research, observed_at=archived['observed_at'])
    return {
        "version": VERSION,
        "command": f"Run {archived['symbol']}",
        "symbol": archived["symbol"],
        "as_of": archived["observed_at"],
        "expiration": archived["expiration"],
        "archive": {
            "provider": archived["provider"],
            "session_date": archived["session_date"],
            "observation": archived["market_research"]["archive_observation"],
            "excluded": archived["excluded"],
            "caveats": archived["caveats"],
        },
        "research_session": research,
        "status": research["status"],
        "read_only": True,
        "caveats": [
            "This orchestration is research-only: no order, journal write, merge or deployment occurs.",
            "Strategy routes and candidate order are not rankings or recommendations.",
            "Unknown evidence remains unknown.",
        ],
    }


def run_latest_market(symbol, *, as_of, read_snapshot, **research_context):
    """Read-only I/O boundary; injected reader owns storage and freshness policy.

    Bind supabase_archive.read_latest_option_snapshot to a client and an explicit
    max_age_seconds outside this module. Completed daily history remains supplied:
    incomplete intraday candles are not silently aggregated into daily evidence.
    """
    symbol = str(symbol).strip().upper()
    now = aware_time(as_of)
    if now is None:
        raise ValueError('Timezone-aware request time required.')
    record = read_snapshot(symbol, as_of)
    payload = record['payload']
    if payload.get('symbol') != symbol:
        raise ValueError('Reader returned a different symbol.')
    observed = aware_time(payload.get('observed_at'))
    finished = aware_time(payload.get('collection_finished_at') or payload.get('options', {}).get('generated_at'))
    if observed is None or observed > now or (finished and finished > now):
        raise ValueError('Reader returned future observations.')
    result = run_market(payload, **research_context)
    if date.fromisoformat(result['expiration']) < now.astimezone(ZoneInfo('America/New_York')).date():
        raise ValueError('Latest archive expiration precedes the request date; use historical run_market explicitly.')
    result['requested_as_of'] = now.isoformat()
    result['archive']['storage'] = deepcopy(record.get('metadata'))
    result['archive']['freshness'] = deepcopy(record.get('freshness'))
    return result


def attach_market_economics(session, *, observed_at):
    """Annotate discovered structures without inventing close-aligned entry data.

    run_market accepts only regular-session observations before the close. Daily
    close-to-close analogs cannot describe those entries, even after the session
    ends. Reuse the shared context gate/evaluator; no extra provider reads occur.
    """
    observed = aware_time(observed_at)
    day = observed.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    positions = [candidate['research'] for candidate in session['candidates']]
    comparison = compare_historical_economics(positions, as_of_dates=[day]*len(positions),
        now=observed, read_snapshot=None, history_loader=None,
        entry_observed_at=observed.isoformat(), available_capital=session['available_capital'],
        holding_period='intraday', include_pairwise=False)
    session['historical_comparison'] = comparison
    session['holding_policy'] = dict(preference='avoid_overnight_exposure',
        intraday_exit_economics='unavailable', expiration_selection='unchanged',
        caveat='Expiration payoff does not establish the economics of exiting before close; no exit is scheduled or executed.')
    for position in positions:
        economics = position['historical_economics']
        economics['provenance'].update(pricing=position.get('evidence', {}).get('pricing_assumption',
            'Archived chain construction assumptions; not executable prices'),
            entry_observed_at=observed.isoformat(), quote_age_seconds=None)
        economics['temporal_basis'] = 'Intraday archive entry; completed-session distributions are not entry-aligned'
        economics['assumptions']['cost_validation'] = 'Constructor fees and zero slippage are assumptions, not verified execution costs'
        economics['intraday_economics'] = dict(status='unavailable', expected_value_dollars=None,
            reason='validated_intraday_option_outcomes_unavailable')
        economics['overnight_exposure'] = dict(
            required_to_hold_to_expiration=position['trade']['expiration'] > day,
            preferred=False, early_exit_economics_available=False)
        economics['research_only_reasons'].append('Default holding preference avoids overnight exposure; early-exit economics unavailable.')
