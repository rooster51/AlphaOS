import math

import pandas as pd
import streamlit as st

from modules.auth import get_current_user
from modules.data import get_account_snapshot, get_user_settings
from modules.income_risk import session_texture
from modules.market_data import price_history, symbol_analysis
from modules.options_income import select_expiration_buckets
from modules.options_suggestions import (
    STRATEGY_CATALOG,
    build_option_suggestions,
    rank_option_suggestions,
    strategy_catalog_rows,
    strategy_explanation,
    suggestion_management_plan,
)
from modules.public_data import get_public_option_chain, get_public_option_expirations
from modules.risk_guardrails import discipline_status
from modules.signal_quality import backtest_signal, reversal_diagnostics
from modules.trade_quality import evaluate_trade_quality, quality_badge_text
from modules.ui import configure_page, empty_state, page_header


DTE_ORDER = ["0DTE", "1DTE", "2DTE", "3DTE", "Weekly"]
DEFAULT_SYMBOLS = ["SPX", "SPY", "QQQ", "XSP", "DIA", "IWM"]


def render_quality_gate(quality: dict) -> None:
    status = quality["status"]
    if status == "Blocked":
        st.error(f"Trade Quality Gate: {quality_badge_text(quality)}")
    elif status == "Approved":
        st.success(f"Trade Quality Gate: {quality_badge_text(quality)}")
    else:
        st.warning(f"Trade Quality Gate: {quality_badge_text(quality)}")

    for blocker in quality["blockers"]:
        st.error(blocker)
    for warning in quality["warnings"]:
        st.warning(warning)

    st.dataframe(quality["checks"], use_container_width=True, hide_index=True)


def growth_rows(starting_balance: float, daily_rate: float, days: int) -> list[dict]:
    checkpoints = sorted({1, 5, 10, 20, 30, 60, 90, int(days)})
    rows = []
    for day in checkpoints:
        if day < 1 or day > days:
            continue
        projected = starting_balance * ((1 + daily_rate) ** day)
        rows.append(
            {
                "Day": day,
                "Projected Balance": round(projected, 2),
                "Total Gain": round(projected - starting_balance, 2),
            }
        )
    return rows


configure_page("Strategy Selector")
page_header(
    "Strategy Selector",
    "Barebones defined-risk spread suggestions and compounding growth math.",
)

user = get_current_user()
user_id = user.get("id") if user else None
settings = get_user_settings(user_id=user_id)
snapshot = get_account_snapshot(user_id=user_id)

suggestions_tab, growth_tab = st.tabs(["Spread Suggestions", "Growth Calculator"])

with suggestions_tab:
    with st.form("spread_suggestion_form"):
        c1, c2, c3, c4 = st.columns(4)
        symbol = c1.selectbox(
            "Ticker",
            DEFAULT_SYMBOLS,
            index=1,
            help="SPX, XSP, SPY, QQQ, DIA, and IWM are the intended index/index-fund universe.",
        )
        bias = c2.selectbox("Bias", ["Auto from trend", "Bullish", "Neutral", "Bearish"])
        strategy_choice = c3.selectbox(
            "Strategy",
            ["Auto - best fit", *sorted(STRATEGY_CATALOG.keys())],
        )
        width_choice = c4.selectbox(
            "Spread width",
            ["Auto", "$1 wide", "$2 wide", "$3 wide", "$5 wide", "$10 wide"],
            index=2,
        )
        submitted = st.form_submit_button(
            "Build Spread Suggestions",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        st.session_state["spread_suggestion_request"] = {
            "symbol": symbol,
            "bias": bias,
            "strategy_choice": strategy_choice,
            "width": None
            if width_choice == "Auto"
            else float(width_choice.replace("$", "").replace(" wide", "")),
            "width_label": width_choice,
        }

    request = st.session_state.get("spread_suggestion_request")
    if not request:
        st.info("Choose a ticker, bias, strategy, and spread width to generate defined-risk ideas.")
    else:
        analysis, source = symbol_analysis(request["symbol"], "Day trade (same day)")
        st.caption(f"Data source: {source} + Public option chain")

        if analysis is None:
            empty_state(
                "Spread suggestions are unavailable.",
                "Verify the ticker is optionable and your Public API connection is active.",
            )
            st.stop()

        outlook = analysis["outlook"] if request["bias"] == "Auto from trend" else request["bias"]
        header = st.columns(5)
        header[0].metric("Underlying", f"${analysis['last']:,.2f}")
        header[1].metric("Bias", outlook)
        header[2].metric("Day Bias", analysis.get("day_bias", "N/A"))
        header[3].metric("20-Day Return", f"{analysis['return_20d']:+.2f}%")
        header[4].metric("Volatility", analysis["volatility"])

        history, history_source = price_history(request["symbol"])
        texture = session_texture(history, analysis)
        reversal_checks = reversal_diagnostics(history, outlook)
        hold_map = {"0DTE": 1, "1DTE": 1, "2DTE": 2, "3DTE": 3, "Weekly": 5}
        strategy_backtests = {
            bucket: backtest_signal(history, outlook, hold_days=hold_map.get(bucket, 5))
            for bucket in DTE_ORDER
        }
        discipline = discipline_status(
            snapshot.get("trades", []),
            settings,
            reversal_checks=reversal_checks,
            backtest=strategy_backtests.get("0DTE"),
        )

        texture_cols = st.columns(3)
        texture_cols[0].metric("Session Setup", texture["label"])
        texture_cols[1].metric("Status", texture["status"])
        texture_cols[2].metric("Chart Source", history_source)
        if texture["status"] in {"Caution", "Directional"}:
            st.warning(f"{texture['detail']} {texture['action']}")
        else:
            st.info(f"{texture['detail']} {texture['action']}")

        st.caption(
            "Allowed recommendations: call debit spreads, put debit spreads, bull put credit spreads, bear call credit spreads, and iron condors. "
            "If the exact strike width is unavailable, AlphaOS uses the nearest listed strike."
        )
        st.dataframe(
            [strategy_explanation(request["strategy_choice"])],
            use_container_width=True,
            hide_index=True,
        )

        try:
            expirations = get_public_option_expirations(request["symbol"])
            buckets = select_expiration_buckets(expirations)
            chains = {
                bucket: get_public_option_chain(request["symbol"], expiration)
                for bucket, expiration in buckets.items()
            }
            target_width = request["width"] or (float(analysis["last"]) * 0.01)
            candidates = build_option_suggestions(
                chains,
                float(analysis["last"]),
                outlook,
                target_width,
                expirations,
            )
            candidates = rank_option_suggestions(candidates, "Account Growth")
        except Exception as exc:
            st.error(f"Option chain lookup failed: {exc}")
            candidates = {}

        if not candidates or not any(candidates.values()):
            empty_state(
                "No viable spread suggestions were found.",
                "Try another ticker, DTE, spread width, or bias.",
            )
        else:
            ordered_buckets = [bucket for bucket in DTE_ORDER if candidates.get(bucket)]
            bucket_tabs = st.tabs(ordered_buckets)
            for tab, bucket in zip(bucket_tabs, ordered_buckets):
                with tab:
                    rows = candidates.get(bucket, [])
                    if request["strategy_choice"] != "Auto - best fit":
                        rows = [
                            row
                            for row in rows
                            if row.get("strategy") == request["strategy_choice"]
                        ]
                    if not rows:
                        empty_state(
                            f"No {bucket} suggestions match this filter.",
                            "Use Auto - best fit or change bias.",
                        )
                        continue

                    for index, spread in enumerate(rows):
                        title = (
                            f"{spread['strategy']} - {spread['side']} - "
                            f"Fit {spread.get('objective_score', 0)}/100"
                        )
                        with st.expander(title, expanded=index == 0):
                            st.caption(
                                f"Expiration: {spread['expiration']} - "
                                f"{spread['expiration_note']}"
                            )
                            st.write(spread.get("thesis", ""))
                            st.caption(spread.get("fit", ""))
                            st.caption(f"Fit: {spread.get('objective_reason', 'general fit')}")

                            quality = evaluate_trade_quality(
                                symbol=request["symbol"],
                                strategy=spread["strategy"],
                                side=spread.get("side", ""),
                                bucket=bucket,
                                legs=spread.get("legs", []),
                                entry_price=spread.get("entry_price"),
                                max_loss=spread.get("max_loss"),
                                analysis=analysis,
                                session=texture,
                                reversal_checks=reversal_checks,
                                backtest=strategy_backtests.get(bucket),
                                discipline=discipline,
                                settings=settings,
                            )
                            render_quality_gate(quality)

                            spread_metrics = st.columns(5)
                            entry = spread.get("entry_price")
                            spread_metrics[0].metric(
                                "Entry",
                                f"${entry:,.2f}" if entry is not None else "Unpriced",
                            )
                            spread_metrics[1].metric(
                                "Width",
                                f"${float(spread.get('actual_width') or 0):,.2f}",
                            )
                            max_profit = spread.get("max_profit")
                            max_loss = spread.get("max_loss")
                            spread_metrics[2].metric(
                                "Max Profit",
                                f"${max_profit:,.2f}" if max_profit is not None else "Open",
                            )
                            spread_metrics[3].metric(
                                "Max Loss",
                                f"${max_loss:,.2f}" if max_loss is not None else "Unknown",
                            )
                            spread_metrics[4].metric("Breakeven", spread["breakeven"])

                            if spread.get("legs"):
                                st.dataframe(
                                    spread["legs"],
                                    use_container_width=True,
                                    hide_index=True,
                                )
                            else:
                                empty_state(
                                    "Pricing is incomplete for this strategy.",
                                    "Do not place the trade until all legs are priced.",
                                )

                            st.subheader("Stop & Management Plan")
                            st.dataframe(
                                suggestion_management_plan(spread),
                                use_container_width=True,
                                hide_index=True,
                            )
                            st.caption(
                                "Planning only. AlphaOS does not place trades or send brokerage orders."
                            )

            priced_strategies = {
                item["strategy"]
                for bucket_rows in candidates.values()
                for item in bucket_rows
                if item.get("entry_price") is not None
            }
            with st.expander("Allowed Spread Strategies", expanded=False):
                st.dataframe(
                    strategy_catalog_rows("Account Growth", priced_strategies),
                    use_container_width=True,
                    hide_index=True,
                )

with growth_tab:
    st.subheader("Compounding Growth Calculator")
    g1, g2, g3 = st.columns(3)
    starting_balance = g1.number_input(
        "Starting balance",
        min_value=0.01,
        value=float(settings.get("default_account_size") or 100.0),
        step=25.0,
    )
    target_balance = g2.number_input(
        "Target balance",
        min_value=0.01,
        value=10000.0,
        step=100.0,
    )
    days = g3.number_input(
        "Days to achieve",
        min_value=1,
        value=120,
        step=1,
    )

    daily_rate = (target_balance / starting_balance) ** (1 / days) - 1
    total_gain = target_balance - starting_balance
    straight_line_daily = total_gain / days
    growth_multiple = target_balance / starting_balance

    metrics = st.columns(4)
    metrics[0].metric("Growth Needed", f"${total_gain:,.2f}")
    metrics[1].metric("Growth Multiple", f"{growth_multiple:,.2f}x")
    metrics[2].metric("Required Daily Compound", f"{daily_rate * 100:.2f}%")
    metrics[3].metric("Straight-Line Daily $", f"${straight_line_daily:,.2f}")

    if not math.isfinite(daily_rate) or daily_rate <= 0:
        st.success("Target is already met or below the starting balance.")
    elif daily_rate > 0.10:
        st.error(
            "This path requires more than 10% compounded per day. Treat that as a danger signal, not a green light to force trades."
        )
    elif daily_rate > 0.03:
        st.warning(
            "This path requires an aggressive daily compound rate. Only clean, rule-approved setups should qualify."
        )
    else:
        st.info("This target is mathematically calmer, but every trade still needs defined risk.")

    st.dataframe(
        pd.DataFrame(growth_rows(starting_balance, daily_rate, int(days))),
        use_container_width=True,
        hide_index=True,
    )
