"""Strict read-only gate for caller-selected verified historical option snapshots.

Selection and immutable-object SHA verification belong to the archive reader.
This module never selects an older snapshot after evidence rejection.
"""
from datetime import datetime, timezone
from modules.market_session_gate import regular_session_bounds
from modules.intraday_quoted_round_trip import EvidenceRejected, reconstruct_quoted_round_trip


def _instant(value):
    if isinstance(value, datetime):
        stamp = value
    elif isinstance(value, str):
        try:
            stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise EvidenceRejected("invalid_window_timestamp") from None
    else:
        raise EvidenceRejected("invalid_window_timestamp")
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise EvidenceRejected("timezone_required")
    return stamp.astimezone(timezone.utc)


def _window(value):
    if not isinstance(value, dict):
        raise EvidenceRejected("window_required")
    start, end = _instant(value.get("start")), _instant(value.get("end"))
    if not start < end:
        raise EvidenceRejected("invalid_window_order")
    bounds = regular_session_bounds(start)
    if bounds is None or not bounds[0] <= start < end <= bounds[1]:
        raise EvidenceRejected("window_outside_single_regular_session")
    return start, end


def evaluate_verified_historical_windows(entry, exit, legs, *,
                                         entry_window, exit_window,
                                         **quote_policy):
    """Evaluate explicit already-verified snapshots, never discover or backfill.

    The caller must supply envelopes obtained from the checksum-verifying
    reader. Their observation and availability times must belong to the
    corresponding window. Rejected evidence raises EvidenceRejected.
    """
    entry_start, entry_end = _window(entry_window)
    exit_start, exit_end = _window(exit_window)
    if entry_end >= exit_start:
        raise EvidenceRejected("overlapping_or_reversed_windows")
    for envelope, start, end in ((entry, entry_start, entry_end),
                                 (exit, exit_start, exit_end)):
        if not isinstance(envelope, dict):
            raise EvidenceRejected("verified_envelope_required")
        try:
            observed = _instant(envelope["payload"]["observed_at"])
            created = _instant(envelope["metadata"]["created_at"])
        except (KeyError, TypeError):
            raise EvidenceRejected("archive_provenance_incomplete") from None
        if not start <= observed <= created <= end:
            raise EvidenceRejected("archive_outside_requested_window")
    return reconstruct_quoted_round_trip(
        entry, exit, legs, entry_as_of=entry_end.isoformat(),
        exit_as_of=exit_end.isoformat(), **quote_policy)
