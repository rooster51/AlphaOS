"""Deterministic trade-intelligence fixtures; no market or execution claims."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from modules.data_entitlements import PRIVATE_RESEARCH, check_data_use
from modules.market_data_contracts import CandleBar, CandleBatch
from modules.market_data_gateway import PUBLIC_CAPABILITIES, build_snapshot
from modules.trade_intelligence import (
    ConfirmedSession,
    VERSION,
    _vwap_setup,
    build_trade_intelligence,
    evaluate_exit_early,
    evaluate_option_candidate,
)

OPEN = datetime(2026, 11, 13, 14, 30, tzinfo=timezone.utc)
STEP = timedelta(minutes=5)


def daily_bars():
    return [{
        "date": "2026-11-12",
        "symbol": "SPY",
        "open": 100.0,
        "high": 110.0,
        "low": 100.0,
        "close": 106.0,
    }]


def snapshot(
    closes,
    *,
    start=OPEN,
    retrieved=None,
    complete=True,
    volumes=None,
    highs=None,
    lows=None,
    now=None,
):
    bars = []
    for index, close in enumerate(closes):
        open_price = close - 0.05
        high = highs[index] if highs is not None else max(open_price, close) + 0.5
        low = lows[index] if lows is not None else min(open_price, close) - 0.5
        bars.append(CandleBar(
            time=(start + index * STEP).isoformat(),
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume=(volumes[index] if volumes is not None else 1000.0),
        ))
    at = retrieved or (start + len(bars) * STEP)
    batch = CandleBatch(
        provider="Public", symbol="SPY", interval="5m", session="regular",
        retrieved_at=at.isoformat(), bars=tuple(bars),
        expected_bars=len(bars), received_bars=len(bars),
        last_bar_complete=True if complete else None,
        warnings=(), capabilities=PUBLIC_CAPABILITIES,
    )
    return build_snapshot(batch, now=now or at, entitlement=check_data_use(
        PRIVATE_RESEARCH, "Public"))


def contract(closes, *, now=None, **kwargs):
    return build_trade_intelligence(
        symbol="SPY",
        now=now or (OPEN + len(closes) * STEP),
        daily_bars=daily_bars(),
        intraday_snapshot=snapshot(closes, now=now, **kwargs),
        atr=1.0,
    )


def setup(result, setup_id):
    return next(item for item in result["setups"] if item["id"] == setup_id)


def test_traditional_pivots_and_prior_session_are_exact():
    result = contract([100.0, 100.2, 100.1])
    levels = result["levels"]
    assert levels["previous_session"] == {
        "date": "2026-11-12", "open": 100.0, "high": 110.0,
        "low": 100.0, "close": 106.0,
    }
    assert levels["pivots"]["pivot"] == pytest.approx(105.3333333333)
    assert levels["pivots"]["r1"] == pytest.approx(110.6666666667)
    assert levels["pivots"]["s1"] == pytest.approx(100.6666666667)
    assert levels["pivots"]["r2"] == pytest.approx(115.3333333333)
    assert levels["pivots"]["s2"] == pytest.approx(95.3333333333)
    assert result["schema_version"] == VERSION


def test_opening_range_uses_the_first_three_confirmed_five_minute_bars():
    result = contract([100.0, 100.2, 100.1, 100.4])
    opening = result["levels"]["opening_range"]
    assert opening["status"] == "complete"
    assert opening["bar_count"] == 3
    assert opening["high"] == pytest.approx(100.7)
    assert opening["low"] == pytest.approx(99.45)
    assert result["levels"]["current_session"]["high"] == pytest.approx(100.9)
    assert result["levels"]["current_session"]["low"] == pytest.approx(99.45)


def test_vwap_and_ema9_are_calculated_only_from_confirmed_bars():
    closes = [100.0, 100.1, 100.2, 100.3, 100.4, 100.5, 100.6, 100.7, 100.8, 100.9]
    result = contract(closes)
    assert result["data"]["confirmed_bars"] == 10
    assert result["levels"]["vwap"]["price"] == pytest.approx(100.4333333333)
    assert result["levels"]["ema9"]["price"] == pytest.approx(100.5)


def test_confirmed_breakout_produces_buy_with_entry_invalidation_stop_and_target():
    result = contract([100.0, 100.2, 100.1, 101.2])
    breakout = setup(result, "opening_range_breakout")
    assert breakout["state"] == "BUY"
    assert breakout["direction"] == "bullish"
    assert breakout["entry_trigger"]["price"] == pytest.approx(100.7)
    assert breakout["invalidation"]["price"] == pytest.approx(100.7)
    assert breakout["stop_reference"]["price"] == pytest.approx(99.45)
    assert breakout["target_reference"]["price"] > breakout["entry_trigger"]["price"]
    assert breakout["risk"]["reward_to_risk"] > 0
    assert result["state"] == "BUY"
    assert "candles" not in result["data"]
    assert "bars" not in result


def test_confirmed_breakdown_produces_sell():
    result = contract([100.0, 100.2, 100.1, 98.8])
    breakout = setup(result, "opening_range_breakout")
    assert breakout["state"] == "SELL"
    assert breakout["direction"] == "bearish"
    assert breakout["entry_trigger"]["price"] == pytest.approx(99.45)
    assert breakout["invalidation"]["price"] == pytest.approx(99.45)
    assert breakout["stop_reference"]["price"] == pytest.approx(100.7)
    assert result["state"] == "SELL"


def test_unverified_final_bar_is_excluded_and_does_not_create_a_signal():
    # The fourth close would be outside the range, but the provider has not
    # confirmed it. Only the three opening bars are confirmed, so no breakout.
    result = contract([100.0, 100.2, 100.1, 101.2], complete=False)
    breakout = setup(result, "opening_range_breakout")
    assert result["data"]["confirmed_bars"] == 3
    assert "last_bar_excluded_unconfirmed" in result["data"]["reasons"]
    assert result["levels"]["opening_range"]["status"] == "complete"
    assert breakout["state"] == "WAIT"
    assert "later confirmed close" in breakout["wait_reason"]
    assert breakout["entry_trigger"]["price"] == pytest.approx(100.7)


def test_unverified_tail_still_allows_an_earlier_confirmed_breakout():
    result = contract([100.0, 100.2, 100.1, 101.2, 101.4], complete=False)
    breakout = setup(result, "opening_range_breakout")
    assert result["data"]["confirmed_bars"] == 4
    assert breakout["state"] == "BUY"


def test_false_breakout_returns_inside_and_stays_wait():
    result = contract([100.0, 100.2, 100.1, 101.2, 100.3])
    breakout = setup(result, "opening_range_breakout")
    assert breakout["state"] == "WAIT"
    assert "False breakout" in breakout["wait_reason"]
    assert result["state"] == "WAIT"


def test_two_sided_opening_range_is_chop_not_a_directional_signal():
    result = contract([100.0, 100.2, 100.1, 101.2, 98.8])
    breakout = setup(result, "opening_range_breakout")
    assert breakout["state"] == "WAIT"
    assert "both sides" in breakout["wait_reason"]
    assert result["state"] == "WAIT"


def test_incomplete_session_grid_fails_closed_for_intraday_setups():
    # 14:40 is missing between the second and third bars.
    snap = snapshot([100.0, 100.2, 100.1, 100.4], highs=None)
    # Rebuild with an explicit gap rather than relying on a provider warning.
    bars = list(snap.candles)
    bars.pop(2)
    batch = CandleBatch(
        provider="Public", symbol="SPY", interval="5m", session="regular",
        retrieved_at=snap.retrieved_at, bars=tuple(bars),
        expected_bars=4, received_bars=3, last_bar_complete=True,
        warnings=(), capabilities=PUBLIC_CAPABILITIES,
    )
    gapped = build_snapshot(batch, now=OPEN + 4 * STEP,
                            entitlement=check_data_use(PRIVATE_RESEARCH, "Public"))
    result = build_trade_intelligence(
        symbol="SPY", now=OPEN + 4 * STEP, daily_bars=daily_bars(),
        intraday_snapshot=gapped, atr=1.0,
    )
    assert result["data"]["status"] == "incomplete"
    assert "session_grid_incomplete" in result["data"]["reasons"]
    assert all(item["state"] == "WAIT" for item in result["setups"])


def test_stale_intraday_data_keeps_all_setups_wait():
    result = contract(
        [100.0, 100.2, 100.1, 101.2],
        now=OPEN + timedelta(minutes=60),
        retrieved=OPEN + timedelta(minutes=60),
    )
    assert result["data"]["status"] == "stale"
    assert result["state"] == "WAIT"
    assert any("stale" in warning.lower() for warning in result["warnings"])


def test_closed_session_displays_levels_but_never_asserts_a_live_entry():
    result = contract(
        [100.0, 100.2, 100.1, 101.2],
        now=datetime(2026, 11, 13, 21, 30, tzinfo=timezone.utc),
        retrieved=datetime(2026, 11, 13, 21, 1, tzinfo=timezone.utc),
    )
    assert result["session"]["state"] == "closed"
    assert result["levels"]["previous_session"]["high"] == 110.0
    assert result["state"] == "WAIT"
    assert "closed" in setup(result, "opening_range_breakout")["wait_reason"]


def test_preopen_returns_prior_levels_and_no_current_session_signal():
    result = build_trade_intelligence(
        symbol="SPY",
        now=datetime(2026, 11, 13, 13, 0, tzinfo=timezone.utc),
        daily_bars=daily_bars(),
        intraday_snapshot=None,
        atr=1.0,
    )
    assert result["session"]["state"] == "preopen"
    assert result["levels"]["previous_session"]["close"] == 106.0
    assert result["state"] == "WAIT"
    assert all(item["state"] == "WAIT" for item in result["setups"])


def test_vwap_ema9_continuation_requires_alignment_pullback_and_follow_through():
    bars = tuple(
        CandleBar((OPEN + index * STEP).isoformat(), close - 0.05,
                  close + 0.1, close - 0.2, close, 1000.0)
        for index, close in enumerate([100.0, 100.5, 100.6, 101.0])
    )
    session = ConfirmedSession(
        bars=bars, status="verified", reasons=(), session_state="open",
        session_date="2026-11-13", open_time=OPEN, close_time=OPEN + timedelta(hours=6),
        latest_confirmed_at=OPEN + 4 * STEP, opening_range={"high": 100.7, "low": 99.5},
        vwap=100.4, ema9=100.2, current_high=101.1, current_low=99.8,
        last_change=None,
    )
    levels = [{"id": "r1", "label": "R1", "price": 102.0, "kind": "resistance", "source": "test"}]
    result = _vwap_setup(session, levels, 1.0)
    assert result["state"] == "BUY"
    assert result["entry_trigger"]["price"] == pytest.approx(101.0)
    assert result["invalidation"]["price"] == pytest.approx(100.4)
    assert result["risk"]["reward_to_risk"] > 0


def test_support_reclaim_needs_follow_through_and_avoids_a_single_wick():
    # A verified support at 100 is tested at 99.9 and reclaimed with two
    # consecutive closes above it.
    result = build_trade_intelligence(
        symbol="SPY", now=OPEN + 7 * STEP, daily_bars=daily_bars(),
        intraday_snapshot=snapshot([100.2, 100.3, 100.1, 99.9, 100.1, 100.2, 100.3]),
        atr=1.0,
        structure_levels=[{"label": "Verified support", "price": 100.0, "kind": "support"}],
    )
    reversal = setup(result, "support_resistance_reversal")
    assert reversal["state"] == "BUY"
    assert reversal["invalidation"]["price"] == pytest.approx(100.0)
    assert reversal["stop_reference"]["price"] < 100.0
    assert result["state"] == "BUY"

    one_close = build_trade_intelligence(
        symbol="SPY", now=OPEN + 5 * STEP, daily_bars=daily_bars(),
        intraday_snapshot=snapshot([100.2, 100.3, 100.1, 99.9, 100.2]),
        atr=1.0,
        structure_levels=[{"label": "Verified support", "price": 100.0, "kind": "support"}],
    )
    assert setup(one_close, "support_resistance_reversal")["state"] == "WAIT"
    assert "Only one close" in setup(one_close, "support_resistance_reversal")["wait_reason"]


def test_options_gate_requires_a_contract_quote_and_budget_and_never_claims_profit():
    assert evaluate_option_candidate(
        strategy_family="long_call", max_modeled_loss=150,
        small_account_budget=300, quote_available=False,
    )["status"] == "unavailable"
    evaluated = evaluate_option_candidate(
        strategy_family="long_call", max_modeled_loss=150,
        small_account_budget=300, quote_available=True,
    )
    assert evaluated["status"] == "evaluated"
    assert evaluated["fits_small_account_budget"] is True
    assert "profitability" in evaluated["reason"]


def test_exit_early_is_unavailable_without_a_modeled_position_or_exit_quote():
    assert evaluate_exit_early(
        position=None, current_spot=99, confirmed_at=OPEN.isoformat(),
        exit_quote_available=True,
    )["state"] == "UNAVAILABLE"
    position = {"direction": "bullish", "invalidation": 100.0, "max_modeled_loss": 150}
    assert evaluate_exit_early(
        position=position, current_spot=99, confirmed_at=OPEN.isoformat(),
        exit_quote_available=False,
    )["state"] == "UNAVAILABLE"
    assert evaluate_exit_early(
        position=position, current_spot=99, confirmed_at=OPEN.isoformat(),
        exit_quote_available=True,
    )["state"] == "EXIT EARLY"
