"""Read-only AlphaOS 2.0 orchestration for one persisted market snapshot."""
from copy import deepcopy

from modules.market_archive_adapter import normalize_archive_snapshot
from modules.opportunity_classifier import classify_opportunity, expected_move_context, history_evidence
from modules.opportunity_session import research_market_opportunities

VERSION = "alphaos-run-market-v1"


def run_market(payload, *, expiration=None, history=None, session_context=None,
               expected_move=None, expected_move_horizon=None,
               available_capital=None, objective=None, width=5, late_minutes=60):
    """Research one archive snapshot without provider calls, persistence or execution."""
    archived = normalize_archive_snapshot(payload, expiration)
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
