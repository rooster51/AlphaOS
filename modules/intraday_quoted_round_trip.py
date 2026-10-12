"""Descriptive intraday option round trips from caller-verified archive envelopes.

No provider access, trading, historical frequency, POP, or executable fill claim.
The caller MUST verify immutable storage SHA-256 before passing an envelope;
shape validation here does not independently establish provenance.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
import re
from zoneinfo import ZoneInfo

from modules.market_session_gate import regular_session_bounds


class EvidenceRejected(ValueError):
    """An archive observation is not suitable for a quoted round trip."""


def _time(value):
    if not isinstance(value, str):
        raise EvidenceRejected("timestamp_missing")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise EvidenceRejected("timestamp_invalid") from None
    if stamp.tzinfo is None:
        raise EvidenceRejected("timestamp_not_aware")
    return stamp.astimezone(timezone.utc)


def _number(value, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceRejected("non_numeric_value")
    result = float(value)
    if not math.isfinite(result) or (result <= 0 if positive else result < 0):
        raise EvidenceRejected("invalid_numeric_value")
    return result


def _envelope(verified, as_of):
    if not isinstance(verified, dict):
        raise EvidenceRejected("verified_envelope_required")
    payload, meta = verified.get("payload"), verified.get("metadata")
    if not isinstance(payload, dict) or not isinstance(meta, dict):
        raise EvidenceRejected("verified_envelope_required")
    options = payload.get("options")
    if not isinstance(options, dict):
        raise EvidenceRejected("options_missing")
    if (meta.get("quality_status") != "complete" or options.get("status") != "complete"
            or meta.get("symbol") != payload.get("symbol")
            or meta.get("provider") != payload.get("provider")
            or meta.get("session_date") != payload.get("session")
            or options.get("symbol") != payload.get("symbol")
            or options.get("provider") != payload.get("provider")
            or options.get("snapshot_date") != payload.get("session")):
        raise EvidenceRejected("archive_metadata_mismatch_or_partial")
    sha = meta.get("archive_sha256")
    if not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{64}", sha) is None:
        raise EvidenceRejected("archive_checksum_metadata_missing")
    observed = _time(payload.get("observed_at"))
    if observed != _time(meta.get("observed_at")):
        raise EvidenceRejected("archive_observation_mismatch")
    completed = _time(payload.get("collection_finished_at"))
    generated = _time(options.get("generated_at"))
    inserted = _time(meta.get("created_at"))
    bounds = regular_session_bounds(observed)
    if (bounds is None or not bounds[0] <= observed <= generated <= completed <= as_of <= bounds[1]
            or observed.astimezone(ZoneInfo("America/New_York")).date().isoformat() != payload.get("session")):
        raise EvidenceRejected("outside_regular_session")
    if not observed <= generated <= completed <= inserted <= as_of:
        raise EvidenceRejected("snapshot_not_available_as_of")
    return payload, completed


def _quotes(payload, contract, as_of, *, max_quote_age_seconds, max_spread_fraction):
    options = payload["options"]
    buckets = ("valid_contracts", "questionable_contracts", "rejected_contracts")
    if any(not isinstance(options.get(bucket), list) for bucket in buckets):
        raise EvidenceRejected("contract_buckets_missing_or_invalid")
    rows = [r for bucket in buckets
            for r in options.get(bucket, []) if isinstance(r, dict) and r.get("contract") == contract]
    if len(rows) != 1 or rows[0] not in options.get("valid_contracts", []):
        raise EvidenceRejected("contract_missing_duplicate_or_unusable")
    row = rows[0]
    if (row.get("quality_warnings") != [] or row.get("rejection_reasons") != []
            or row.get("quote_outcome") != "SUCCESS"):
        raise EvidenceRejected("contract_quality_unusable")
    match = re.fullmatch(r"([A-Z]{1,6})\s*(\d{6})([CP])(\d{8})", contract)
    if match is None or match.group(1) != payload["symbol"]:
        raise EvidenceRejected("contract_identifier_mismatch")
    try:
        expiry = datetime.strptime(match.group(2), "%y%m%d").date().isoformat()
    except ValueError:
        raise EvidenceRejected("contract_expiry_invalid") from None
    if (row.get("symbol") != payload["symbol"] or row.get("expiration") != expiry
            or row.get("type") != ("call" if match.group(3) == "C" else "put")
            or _number(row.get("strike"), positive=True) != int(match.group(4)) / 1000):
        raise EvidenceRejected("contract_terms_mismatch")
    bid = _number(row.get("bid"))
    ask = _number(row.get("ask"), positive=True)
    if bid > ask:
        raise EvidenceRejected("crossed_market")
    mid = (bid + ask) / 2
    if (ask - bid) / mid > max_spread_fraction:
        raise EvidenceRejected("spread_too_wide")
    bid_at, ask_at = _time(row.get("bid_timestamp")), _time(row.get("ask_timestamp"))
    row_at = _time(row.get("observed_at"))
    bounds = regular_session_bounds(row_at)
    if (bounds is None or not bounds[0] <= bid_at <= row_at <= bounds[1]
            or not bounds[0] <= ask_at <= row_at
            or not _time(payload["observed_at"]) <= row_at <= _time(options["generated_at"])):
        raise EvidenceRejected("quote_outside_collection_or_session")
    if row_at > as_of or bid_at > row_at or ask_at > row_at:
        raise EvidenceRejected("future_quote")
    for quote_at in (bid_at, ask_at):
        if not 0 <= (as_of - quote_at).total_seconds() <= max_quote_age_seconds:
            raise EvidenceRejected("stale_or_future_quote")
    if as_of.astimezone(ZoneInfo("America/New_York")).date().isoformat() > expiry:
        raise EvidenceRejected("contract_expired")
    return {"bid": bid, "ask": ask, "bid_at": bid_at, "ask_at": ask_at,
            "contract": contract, "expiry": expiry}


def reconstruct_quoted_round_trip(entry, exit, legs, *, entry_as_of, exit_as_of,
                                  max_quote_age_seconds=120,
                                  max_leg_skew_seconds=120,
                                  max_spread_fraction=0.5,
                                  fee_per_contract_per_side=0):
    """Reconstruct hypothetical bid/ask cash flows for 1–4 identical-contract legs.

    Each input must be an envelope returned by a checksum-verifying archive reader.
    Entry buys at ask/sells at bid; exits reverse at bid/ask. No intrabar touch,
    executable fill, POP, slippage, early exit optimization, or predictive EV.
    """
    entry_at, exit_at = _time(entry_as_of), _time(exit_as_of)
    if entry_at >= exit_at:
        raise EvidenceRejected("non_forward_round_trip")
    age = _number(max_quote_age_seconds)
    skew = _number(max_leg_skew_seconds)
    spread = _number(max_spread_fraction)
    fee = _number(fee_per_contract_per_side)
    if age <= 0 or skew <= 0 or spread > 2:
        raise EvidenceRejected("invalid_quote_policy")
    if not isinstance(legs, list) or not 1 <= len(legs) <= 4:
        raise EvidenceRejected("one_to_four_legs_required")
    entry_payload, entry_complete = _envelope(entry, entry_at)
    exit_payload, exit_complete = _envelope(exit, exit_at)
    if (entry_payload.get("symbol") != exit_payload.get("symbol")
            or entry_payload.get("provider") != exit_payload.get("provider")
            or entry_payload.get("session") != exit_payload.get("session")
            or not entry_complete < exit_complete):
        raise EvidenceRejected("snapshot_sequence_mismatch")
    seen = set()
    entry_cash, exit_cash, contracts = 0.0, 0.0, 0
    entry_quote_times, exit_quote_times = [], []
    leg_results = []
    for leg in legs:
        if not isinstance(leg, dict):
            raise EvidenceRejected("invalid_leg")
        contract, side, quantity = leg.get("contract"), leg.get("side"), leg.get("quantity")
        if (not isinstance(contract, str) or contract in seen or side not in ("long", "short")
                or type(quantity) is not int or not 1 <= quantity <= 100):
            raise EvidenceRejected("invalid_or_duplicate_leg")
        seen.add(contract)
        opened = _quotes(entry_payload, contract, entry_at,
                         max_quote_age_seconds=age, max_spread_fraction=spread)
        closed = _quotes(exit_payload, contract, exit_at,
                         max_quote_age_seconds=age, max_spread_fraction=spread)
        if opened["expiry"] != closed["expiry"]:
            raise EvidenceRejected("contract_changed")
        if opened["bid_at"] >= closed["bid_at"] or opened["ask_at"] >= closed["ask_at"]:
            raise EvidenceRejected("quote_did_not_advance")
        if closed["bid_at"] <= entry_at or closed["ask_at"] <= entry_at:
            raise EvidenceRejected("exit_quote_not_after_entry")
        entry_quote_times.extend((opened["bid_at"], opened["ask_at"]))
        exit_quote_times.extend((closed["bid_at"], closed["ask_at"]))
        opening = opened["ask"] if side == "long" else opened["bid"]
        closing = closed["bid"] if side == "long" else closed["ask"]
        signed_entry = -opening if side == "long" else opening
        signed_exit = closing if side == "long" else -closing
        entry_cash += signed_entry * quantity * 100
        exit_cash += signed_exit * quantity * 100
        contracts += quantity
        leg_results.append({"contract": contract, "side": side, "quantity": quantity,
                            "entry_quote": opening, "exit_quote": closing,
                            "gross_pnl_usd": round((signed_entry + signed_exit) * quantity * 100, 2)})
    if ((max(entry_quote_times) - min(entry_quote_times)).total_seconds() > skew
            or (max(exit_quote_times) - min(exit_quote_times)).total_seconds() > skew):
        raise EvidenceRejected("asynchronous_leg_quotes")
    fees = 2 * contracts * fee
    return {
        "status": "descriptive_quoted_round_trip_only",
        "symbol": entry_payload["symbol"],
        "provider": entry_payload["provider"],
        "entry_as_of": entry_at.isoformat(),
        "exit_as_of": exit_at.isoformat(),
        "entry_cashflow_usd": round(entry_cash, 2),
        "exit_cashflow_usd": round(exit_cash, 2),
        "round_trip_fees_usd": round(fees, 2),
        "hypothetical_pnl_usd": round(entry_cash + exit_cash - fees, 2),
        "legs": leg_results,
        "limitations": ["caller_must_verify_archive_checksum", "bid_ask_quotes_not_executable_fills",
                        "quote_sampling_misses_intrabar_paths", "not_pop_ev_or_trading_recommendation"],
    }
