"""Deterministic fail-closed tests: synthetic quotes, not real archive results."""
from copy import deepcopy

import pytest

from modules.intraday_quoted_round_trip import EvidenceRejected, reconstruct_quoted_round_trip

CONTRACT = "SPY261009C00750000"
SECOND = "SPY261009C00755000"


def snapshot(*, exit=False):
    start = "14:09:00+00:00" if exit else "14:04:00+00:00"
    generated = "14:09:40+00:00" if exit else "14:04:40+00:00"
    finished = "14:09:50+00:00" if exit else "14:04:50+00:00"
    created = "14:09:55+00:00" if exit else "14:04:55+00:00"
    quoted = "14:09:30+00:00" if exit else "14:04:30+00:00"
    def stamp(t):
        return "2026-10-09T" + t
    def row(contract, strike, bid, ask):
        return {
            "contract": contract, "symbol": "SPY", "expiration": "2026-10-09",
            "type": "call", "strike": strike, "bid": bid, "ask": ask,
            "quote_outcome": "SUCCESS", "quality_warnings": [], "rejection_reasons": [],
            "bid_timestamp": stamp(quoted), "ask_timestamp": stamp(quoted),
            "observed_at": stamp(generated),
        }
    return {
        "metadata": {
            "provider": "Public", "symbol": "SPY", "session_date": "2026-10-09",
            "quality_status": "complete", "observed_at": stamp(start),
            "created_at": stamp(created), "archive_sha256": "a" * 64,
        },
        "payload": {
            "provider": "Public", "symbol": "SPY", "session": "2026-10-09",
            "observed_at": stamp(start), "collection_finished_at": stamp(finished),
            "options": {
                "provider": "Public", "symbol": "SPY", "snapshot_date": "2026-10-09",
                "generated_at": stamp(generated), "status": "complete",
                "valid_contracts": [
                    row(CONTRACT, 750, 1.45 if exit else 1.10, 1.55 if exit else 1.20),
                    row(SECOND, 755, .70 if exit else .50, .80 if exit else .60),
                ],
                "questionable_contracts": [], "rejected_contracts": [],
            },
        },
    }


def compute(entry=None, exit=None, legs=None, **kwargs):
    return reconstruct_quoted_round_trip(
        entry or snapshot(), exit or snapshot(exit=True),
        legs or [{"contract": CONTRACT, "side": "long", "quantity": 1}],
        entry_as_of="2026-10-09T14:05:00Z",
        exit_as_of="2026-10-09T14:10:00Z", **kwargs,
    )


def test_long_buy_ask_sell_bid_fees():
    result = compute(fee_per_contract_per_side=.65)
    assert result["hypothetical_pnl_usd"] == 23.70
    assert result["entry_cashflow_usd"] == -120
    assert result["exit_cashflow_usd"] == 145
    assert result["status"] == "descriptive_quoted_round_trip_only"


def test_short_sell_bid_buy_ask():
    result = compute(legs=[{"contract": CONTRACT, "side": "short", "quantity": 1}])
    assert result["hypothetical_pnl_usd"] == -45


def test_two_leg_vertical_conservative_quotes():
    result = compute(legs=[
        {"contract": CONTRACT, "side": "long", "quantity": 1},
        {"contract": SECOND, "side": "short", "quantity": 1},
    ], fee_per_contract_per_side=.65)
    assert result["hypothetical_pnl_usd"] == -7.60
    assert len(result["legs"]) == 2


@pytest.mark.parametrize("mutation", [
    lambda s: s["payload"]["options"].update(status="partial"),
    lambda s: s["metadata"].update(symbol="QQQ"),
    lambda s: s["metadata"].update(archive_sha256="not-a-sha"),
    lambda s: s["metadata"].update(created_at="2026-10-09T14:11:00Z"),
    lambda s: s["payload"].update(collection_finished_at="2026-10-09T14:11:00Z"),
])
def test_rejects_invalid_or_unavailable_snapshot(mutation):
    entry = snapshot()
    mutation(entry)
    with pytest.raises(EvidenceRejected):
        compute(entry=entry)


@pytest.mark.parametrize("mutation", [
    lambda s: s["payload"]["options"]["valid_contracts"][0].update(bid_timestamp=None),
    lambda s: s["payload"]["options"]["valid_contracts"][0].update(bid_timestamp="2026-10-09T14:00:00Z"),
    lambda s: s["payload"]["options"]["valid_contracts"][0].update(ask=.50),
    lambda s: s["payload"]["options"]["valid_contracts"][0].update(quality_warnings=["bid_timestamp_missing"]),
    lambda s: s["payload"]["options"]["valid_contracts"][0].update(symbol="QQQ"),
])
def test_rejects_unusable_quote(mutation):
    entry = snapshot()
    mutation(entry)
    with pytest.raises(EvidenceRejected):
        compute(entry=entry)


def test_rejects_missing_contract_in_exit():
    closed = snapshot(exit=True)
    closed["payload"]["options"]["valid_contracts"].pop(0)
    with pytest.raises(EvidenceRejected, match="contract_missing"):
        compute(exit=closed)


def test_rejects_duplicate_leg():
    legs = [{"contract": CONTRACT, "side": "long", "quantity": 1}] * 2
    with pytest.raises(EvidenceRejected, match="duplicate_leg"):
        compute(legs=legs)


def test_rejects_unchanged_quote_timestamp():
    closed = snapshot(exit=True)
    closed["payload"]["options"]["valid_contracts"][0]["bid_timestamp"] = "2026-10-09T14:04:30Z"
    closed["payload"]["options"]["valid_contracts"][0]["ask_timestamp"] = "2026-10-09T14:04:30Z"
    with pytest.raises(EvidenceRejected):
        compute(exit=closed)


def test_rejects_quote_skew_across_legs():
    entry = snapshot()
    entry["payload"]["options"]["valid_contracts"][1]["bid_timestamp"] = "2026-10-09T14:01:00Z"
    entry["payload"]["options"]["valid_contracts"][1]["ask_timestamp"] = "2026-10-09T14:01:00Z"
    with pytest.raises(EvidenceRejected):
        compute(entry=entry, legs=[
            {"contract": CONTRACT, "side": "long", "quantity": 1},
            {"contract": SECOND, "side": "short", "quantity": 1},
        ], max_quote_age_seconds=300, max_leg_skew_seconds=120)


def test_rejects_unsupported_leg_and_invalid_policy():
    with pytest.raises(EvidenceRejected):
        compute(legs=[{"contract": CONTRACT, "side": "hold", "quantity": 1}])
    with pytest.raises(EvidenceRejected):
        compute(max_quote_age_seconds=float("inf"))
