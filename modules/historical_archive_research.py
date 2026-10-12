"""Read-only option mark-to-market research from checksum-verified archives."""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from math import isfinite
import re
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal

from modules.options_payoff import validate_trade
from modules.quote_freshness import configured_limit

NY = ZoneInfo("America/New_York")
QUOTE_AGE_ENV = "ALPHAOS_MAX_QUOTE_AGE_SECONDS"
VERSION = "historical-option-archive-v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _timestamp(value):
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(
            str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _window(value):
    if not isinstance(value, dict):
        return None
    start, end = _timestamp(value.get("start")), _timestamp(value.get("end"))
    if start is None or end is None or end < start:
        return None
    return start, end


def _window_session(window):
    start, end = window
    local_start, local_end = start.astimezone(NY), end.astimezone(NY)
    if local_start.date() != local_end.date():
        return None
    day = local_start.date()
    schedule = mcal.get_calendar("NYSE").schedule(start_date=day, end_date=day)
    if schedule.empty:
        return None
    opening = schedule.iloc[0]["market_open"].to_pydatetime()
    closing = schedule.iloc[0]["market_close"].to_pydatetime()
    if not opening <= start < closing or not opening <= end <= closing:
        return None
    return day, opening, closing


def _contract_id(symbol, expiration, kind, strike):
    try:
        strike_mills = Decimal(str(strike)) * 1000
        if strike_mills != strike_mills.to_integral_value() or strike_mills <= 0:
            return None
        encoded = int(strike_mills)
        if encoded > 99_999_999:
            return None
        option_type = {"Call": "C", "Put": "P"}[kind]
        expiry = date.fromisoformat(expiration).strftime("%y%m%d")
        return f"{symbol}{expiry}{option_type}{encoded:08d}"
    except (InvalidOperation, KeyError, TypeError, ValueError, OverflowError):
        return None


def _same_contract(value, expected):
    return isinstance(value, str) and value.replace(" ", "").upper() == expected


def _archive_snapshot(record, *, symbol, window, session_day):
    start, end = window
    try:
        payload, metadata, freshness = (
            record["payload"], record["metadata"], record["freshness"])
        options = payload["options"]
        observed = _timestamp(payload["observed_at"])
        created = _timestamp(metadata["created_at"])
        metadata_observed = _timestamp(metadata["observed_at"])
        freshness_as_of = _timestamp(freshness["as_of"])
        max_age = freshness["max_age_seconds"]
        age = freshness["age_seconds"]
        archive_path = metadata["archive_path"]
        digest = metadata["archive_sha256"]
        archive_id = metadata["id"]
    except (KeyError, TypeError):
        return None, "archive_provenance_incomplete"

    if (not isinstance(payload, dict) or not isinstance(options, dict)
            or not isinstance(metadata, dict) or not isinstance(freshness, dict)):
        return None, "archive_record_invalid"
    if (payload.get("symbol") != symbol or metadata.get("symbol") != symbol
            or payload.get("provider") != "Public" or metadata.get("provider") != "Public"):
        return None, "archive_identity_mismatch"
    if (payload.get("session") != session_day.isoformat()
            or str(metadata.get("session_date")) != session_day.isoformat()):
        return None, "archive_session_mismatch"
    if (observed is None or metadata_observed != observed
            or created is None or created > end
            or freshness_as_of != end or not start <= observed <= end):
        return None, "archive_outside_requested_window"
    if (isinstance(max_age, bool) or not isinstance(max_age, (int, float))
            or not isfinite(max_age) or max_age < 0
            or isinstance(age, bool) or not isinstance(age, (int, float))
            or not isfinite(age) or age < 0 or age > max_age
            or abs(age - (end - observed).total_seconds()) > 1):
        return None, "archive_freshness_mismatch"
    expected_prefix = f"options/symbol={symbol}/date={session_day.isoformat()}/"
    if (not isinstance(archive_path, str) or not archive_path.startswith(expected_prefix)
            or ".." in archive_path or not archive_path.endswith(".json.gz")
            or not isinstance(archive_id, str) or not archive_id.strip()
            or not isinstance(digest, str) or not _SHA256.fullmatch(digest.lower())):
        return None, "archive_provenance_incomplete"
    if options.get("symbol") != symbol or options.get("snapshot_date") != session_day.isoformat():
        return None, "archive_option_identity_mismatch"
    if options.get("status") not in ("complete", "partial", "empty"):
        return None, "archive_quality_status_invalid"
    if metadata.get("quality_status") != options.get("status"):
        return None, "archive_quality_status_mismatch"

    generated = _timestamp(options.get("generated_at"))
    started = _timestamp(options.get("collection_started_at"))
    finished = _timestamp(payload.get("collection_finished_at") or options.get("generated_at"))
    if (generated is None or started is None or finished is None
            or started > generated or generated > finished or finished > end
            or generated.astimezone(NY).date() != session_day
            or finished.astimezone(NY).date() != session_day):
        return None, "archive_collection_session_mismatch"
    return dict(payload=payload, metadata=metadata, options=options,
                observed_at=observed, collection_finished_at=finished,
                status=options["status"]), None


def _quote_row(snapshot, leg, *, symbol, expiration, window, session, max_quote_age):
    expected = _contract_id(symbol, expiration, leg["type"], leg["strike"])
    if expected is None:
        return None, dict(code="unsupported_contract_strike", contract=None)

    options = snapshot["options"]
    matches = []
    rejected_matches = []
    for field in ("valid_contracts", "questionable_contracts", "rejected_contracts"):
        rows = options.get(field, [])
        if not isinstance(rows, list):
            return None, dict(code="archive_contracts_invalid", contract=expected)
        for row in rows:
            if isinstance(row, dict) and _same_contract(row.get("contract"), expected):
                (rejected_matches if field == "rejected_contracts" else matches).append((field, row))
    if rejected_matches:
        reasons = sorted({reason for _, row in rejected_matches
                          for reason in row.get("rejection_reasons", [])})
        return None, dict(code="archived_contract_rejected", contract=expected,
                          reasons=reasons or ["archive_rejected_contract"])
    if len(matches) > 1:
        return None, dict(code="duplicate_contract_identity", contract=expected)
    if not matches:
        return None, dict(code="contract_not_archived", contract=expected)

    group, row = matches[0]
    try:
        strike = float(row["strike"])
        bid, ask = float(row["bid"]), float(row["ask"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None, dict(code="contract_quote_incomplete", contract=expected)
    if (row.get("symbol") != symbol or row.get("expiration") != expiration
            or row.get("type") != leg["type"] or not isfinite(strike)
            or abs(strike - float(leg["strike"])) > 1e-9
            or not _same_contract(row.get("contract"), expected)):
        return None, dict(code="contract_identity_mismatch", contract=expected)
    if row.get("quote_outcome") != "SUCCESS":
        return None, dict(code="quote_outcome_not_success", contract=expected)
    if not isfinite(bid) or not isfinite(ask) or bid < 0 or ask <= 0 or ask < bid:
        return None, dict(code="invalid_bid_ask", contract=expected)

    captured = _timestamp(row.get("observed_at"))
    if (captured is None or not window[0] <= captured <= window[1]
            or captured > snapshot["collection_finished_at"]
            or captured.astimezone(NY).date() != session[0]):
        return None, dict(code="contract_observation_outside_window", contract=expected)
    timestamps = {}
    for side in ("bid", "ask"):
        stamp = _timestamp(row.get(f"{side}_timestamp"))
        if stamp is None:
            return None, dict(code=f"missing_{side}_timestamp", contract=expected)
        if stamp > captured:
            return None, dict(code=f"future_{side}_timestamp", contract=expected)
        if not window[0] <= stamp <= window[1]:
            return None, dict(code=f"{side}_timestamp_outside_window", contract=expected)
        if stamp.astimezone(NY).date() != session[0] or not session[1] <= stamp < session[2]:
            return None, dict(code=f"{side}_timestamp_outside_session", contract=expected)
        age = (captured - stamp).total_seconds()
        if age < 0 or age > max_quote_age:
            return None, dict(code=f"stale_{side}_quote", contract=expected,
                              age_seconds=age, max_age_seconds=max_quote_age)
        timestamps[side] = stamp.isoformat()

    return dict(contract=expected, bid=bid, ask=ask, timestamps=timestamps,
                observed_at=captured.isoformat(), source_group=group,
                quality_warnings=list(row.get("quality_warnings", []))), None


def evaluate_historical_archive_research(
    candidate, *, entry_window, exit_window, read_snapshots, now=None,
):
    """Estimate conservative option mark-to-market between explicit NYSE windows.

    The injected reader must verify the immutable archive object's checksum and
    storage metadata. The latest snapshot with all requested contracts and fresh
    quotes is selected from each window; skipped candidates remain in the report.
    """
    result = dict(version=VERSION, status="rejected", strategy_family=None,
        entry_window=None, exit_window=None, entry_cash_flow_dollars=None,
        exit_cash_flow_dollars=None, fees_dollars=None, pnl_dollars=None,
        contracts=[], provenance={}, warnings=[], missing_evidence=[],
        rejection_report={"entry": [], "exit": [], "global": []},
        eligible_for_consideration=False,
        assumptions=dict(multiplier=100, entry="buy at ask; sell at bid",
            exit="sell at bid; buy to close at ask",
            prices="conservative archived quote sides; not guaranteed fills",
            fees="total package fees charged once"))

    entry, exit_ = _window(entry_window), _window(exit_window)
    if entry is None:
        result["rejection_report"]["entry"].append({"code": "invalid_entry_window"})
    if exit_ is None:
        result["rejection_report"]["exit"].append({"code": "invalid_exit_window"})
    if entry is None or exit_ is None:
        result["missing_evidence"] = ["invalid_time_window"]
        return result
    result["entry_window"] = dict(start=entry[0].isoformat(), end=entry[1].isoformat())
    result["exit_window"] = dict(start=exit_[0].isoformat(), end=exit_[1].isoformat())
    if exit_[0] <= entry[1]:
        result["rejection_report"]["global"].append({"code": "windows_not_chronological"})

    try:
        trade = validate_trade(candidate)
        result["strategy_family"] = candidate.get("strategy_family", candidate.get("strategy"))
        max_quote_age = configured_limit(QUOTE_AGE_ENV, 120.0, 900.0)
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        result["rejection_report"]["global"].append({"code": "invalid_structure"})
        result["missing_evidence"] = ["invalid_structure"]
        return result
    if not callable(read_snapshots):
        result["rejection_report"]["global"].append({"code": "archive_reader_unavailable"})
        result["missing_evidence"] = ["archive_reader_unavailable"]
        return result
    current = _timestamp(now or datetime.now(timezone.utc))
    if current is None:
        result["rejection_report"]["global"].append({"code": "invalid_research_clock"})
    elif entry[1] > current or exit_[1] > current:
        result["rejection_report"]["global"].append({"code": "future_time_window"})

    sessions = []
    for name, window in (("entry", entry), ("exit", exit_)):
        try:
            session = _window_session(window)
        except Exception:
            session = None
        if session is None:
            result["rejection_report"][name].append({"code": "window_outside_regular_nyse_session"})
        sessions.append(session)
    if sessions[0] and sessions[1]:
        expiration = date.fromisoformat(trade["expiration"])
        if sessions[1][0] > expiration:
            result["rejection_report"]["global"].append({"code": "exit_after_expiration"})

    if result["rejection_report"]["global"] or any(
            result["rejection_report"][name] for name in ("entry", "exit")):
        result["missing_evidence"] = sorted({item["code"]
            for rows in result["rejection_report"].values() for item in rows})
        return result

    archives, snapshots, quotes_by_window = {}, {}, {}
    for name, window, session in zip(("entry", "exit"), (entry, exit_), sessions):
        try:
            candidates = read_snapshots(trade["symbol"],
                window[0].isoformat(), window[1].isoformat())
        except Exception:
            result["rejection_report"][name].append({"code": "archive_unavailable"})
            continue
        if (not isinstance(candidates, dict)
                or not isinstance(candidates.get("snapshots"), list)
                or not isinstance(candidates.get("rejected", []), list)):
            result["rejection_report"][name].append({"code": "archive_reader_response_invalid"})
            continue
        rejected_candidates = candidates.get("rejected", [])
        if isinstance(rejected_candidates, list):
            for rejected in rejected_candidates:
                if isinstance(rejected, dict):
                    result["rejection_report"][name].append(dict(
                        code=rejected.get("reason", "archive_candidate_rejected"),
                        observed_at=rejected.get("observed_at")))
        records = candidates["snapshots"]
        if any(not isinstance(record, dict) for record in records):
            result["rejection_report"][name].append({"code": "archive_reader_response_invalid"})
            continue
        def observed_at(record):
            metadata = record.get("metadata")
            if not isinstance(metadata, dict):
                return datetime.min.replace(tzinfo=timezone.utc)
            return (_timestamp(metadata.get("observed_at"))
                    or datetime.min.replace(tzinfo=timezone.utc))

        records.sort(key=observed_at, reverse=True)
        for record in records:
            snapshot, reason = _archive_snapshot(record, symbol=trade["symbol"],
                window=window, session_day=session[0])
            if reason:
                result["rejection_report"][name].append(dict(code=reason))
                continue
            quotes, quote_rejections = [], []
            for leg in trade["legs"]:
                quote, rejection = _quote_row(snapshot, leg, symbol=trade["symbol"],
                    expiration=trade["expiration"], window=window, session=session,
                    max_quote_age=max_quote_age)
                if rejection:
                    quote_rejections.append(rejection)
                else:
                    quotes.append(quote)
            if quote_rejections:
                result["rejection_report"][name].extend(quote_rejections)
                continue
            archives[name] = dict(archive_id=snapshot["metadata"]["id"],
                archive_sha256=snapshot["metadata"]["archive_sha256"],
                archive_path=snapshot["metadata"]["archive_path"],
                observed_at=snapshot["observed_at"].isoformat(),
                collection_finished_at=snapshot["collection_finished_at"].isoformat(),
                quality_status=snapshot["status"])
            snapshots[name], quotes_by_window[name] = snapshot, quotes
            if snapshot["status"] != "complete":
                result["warnings"].append(f"{name}_archive_{snapshot['status']}")
            break
        if name not in snapshots and not result["rejection_report"][name]:
            result["rejection_report"][name].append({"code": "no_snapshot_in_window"})

    result["provenance"] = archives
    if any(name not in snapshots for name in ("entry", "exit")):
        result["missing_evidence"] = sorted({item["code"]
            for rows in result["rejection_report"].values() for item in rows})
        return result
    if any(result["rejection_report"][name] for name in ("entry", "exit")):
        result["warnings"].append("ineligible_snapshots_skipped")

    fees = trade["fees"]
    entry_cash, exit_cash, contracts = 0.0, 0.0, []
    for leg, entry_quote, exit_quote in zip(
            trade["legs"], quotes_by_window["entry"], quotes_by_window["exit"]):
        entry_price = entry_quote["ask"] if leg["qty"] > 0 else entry_quote["bid"]
        exit_price = exit_quote["bid"] if leg["qty"] > 0 else exit_quote["ask"]
        entry_cashflow = -leg["qty"] * entry_price * 100
        exit_cashflow = leg["qty"] * exit_price * 100
        entry_cash += entry_cashflow
        exit_cash += exit_cashflow
        contracts.append(dict(contract=entry_quote["contract"], type=leg["type"],
            strike=leg["strike"], quantity=leg["qty"],
            entry_quote=entry_quote, exit_quote=exit_quote,
            entry_cash_flow_dollars=entry_cashflow,
            exit_cash_flow_dollars=exit_cashflow,
            pnl_dollars=entry_cashflow + exit_cashflow))
    result.update(status="complete", contracts=contracts,
        entry_cash_flow_dollars=entry_cash, exit_cash_flow_dollars=exit_cash,
        fees_dollars=fees, pnl_dollars=entry_cash + exit_cash - fees,
        missing_evidence=[], eligible_for_consideration=False)
    return result
