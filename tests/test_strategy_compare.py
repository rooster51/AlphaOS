import pytest

from modules.long_option_research import research_long_option
from modules.structure_research import research_structure
from modules.strategy_compare import compare_strategy_research


def structure(legs, credit, **extra):
    candidate = dict(
        symbol="QQQ",
        expiration="2030-01-18",
        spot=100,
        credit=credit,
        shares=0,
        fees=0,
        legs=[dict(type=kind, strike=strike, qty=qty) for kind, strike, qty in legs],
    )
    candidate.update(extra)
    return research_structure(candidate, as_of="2030-01-17", expected_move=3)


def test_compares_long_option_and_defined_risk_structure_without_ranking():
    long_call = research_long_option(
        "QQQ", "2030-01-18", "Call", 100, 2, 100,
        as_of="2030-01-17", expected_move=3,
    )
    debit = structure([("Call", 100, 1), ("Call", 105, -1)], -2)

    result = compare_strategy_research([debit, long_call], thesis={"direction": "bullish"})

    assert [x["input_index"] for x in result["candidates"]] == [0, 1]
    assert result["candidates"][0]["strategy_family"] == "call_debit_spread"
    assert result["candidates"][1]["strategy_family"] == "long_call"
    assert result["candidates"][1]["max_profit"] == "unlimited"
    assert result["winner"] is None
    assert result["recommendation"] is None
    assert "not a ranking" in result["candidate_order"]
    assert result["thesis"] == {"direction": "bullish"}


def test_common_economics_and_expected_move_are_preserved():
    debit = structure([("Call", 100, 1), ("Call", 105, -1)], -2)
    item = compare_strategy_research([debit])["candidates"][0]

    assert item["capital_at_risk"] == 200
    assert item["max_profit"] == 300
    assert item["breakevens"] == [102]
    assert item["breakeven_moves"] == [2]
    assert item["breakeven_move_pcts"] == pytest.approx([.02])
    assert item["expected_move"] == 3
    assert item["breakeven_distances_in_expected_moves"] == pytest.approx([2 / 3])
    assert item["dte"] == 1


def test_missing_market_evidence_stays_missing():
    debit = structure([("Call", 100, 1), ("Call", 105, -1)], -2)
    item = compare_strategy_research([debit])["candidates"][0]

    assert item["market_evidence_available"]["delta"] is False
    assert item["market_evidence_available"]["iv"] is False
    assert item["market_evidence_available"]["volume"] is False
    assert item["market_evidence_available"]["open_interest"] is False


def test_observed_market_evidence_is_marked_available_not_scored():
    candidate = dict(
        symbol="QQQ",
        expiration="2030-01-18",
        spot=100,
        credit=-2,
        shares=0,
        fees=0,
        legs=[
            dict(type="Call", strike=100, qty=1, bid=2.9, ask=3.1, delta=.5, iv=.2),
            dict(type="Call", strike=105, qty=-1, bid=.9, ask=1.1, delta=.2, iv=.22),
        ],
    )
    researched = research_structure(candidate)
    item = compare_strategy_research([researched])["candidates"][0]

    assert item["market_evidence_available"]["bid"] is True
    assert item["market_evidence_available"]["ask"] is True
    assert item["market_evidence_available"]["delta"] is True
    assert item["market_evidence_available"]["iv"] is True
    assert "score" not in item


def test_invalid_candidates_fail_closed_without_reordering_valid_candidates():
    debit = structure([("Call", 100, 1), ("Call", 105, -1)], -2)
    condor = structure([
        ("Put", 90, 1), ("Put", 95, -1),
        ("Call", 105, -1), ("Call", 115, 1),
    ], 2)

    result = compare_strategy_research([{}, debit, "bad", condor])

    assert [x["input_index"] for x in result["candidates"]] == [1, 3]
    assert [x["input_index"] for x in result["excluded"]] == [0, 2]
    assert all(x["reason"] == "invalid_or_insufficient_research" for x in result["excluded"])


def test_empty_and_invalid_inputs():
    empty = compare_strategy_research([])
    assert empty["no_candidate"] is True
    assert empty["candidates"] == []
    with pytest.raises(ValueError):
        compare_strategy_research(None)
