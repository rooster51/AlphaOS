import streamlit as st

from modules.market_data import symbol_analysis
from modules.options_income import build_income_spread, select_expiration_buckets
from modules.public_data import (
    get_public_option_chain,
    get_public_option_expirations,
)
from modules.strategies import primary_strategy_idea
from modules.ui import configure_page, empty_state, page_header


HORIZONS = [
    "Day trade (same day)",
    "Swing (2-8 weeks)",
    "Intermediate (2-6 months)",
    "Long term (6+ months)",
]


def load_spread_into_journal(symbol: str, spread: dict) -> None:
    for key in list(st.session_state):
        if key.startswith("journal_"):
            del st.session_state[key]
    st.session_state["journal_spread_draft"] = {
        "symbol": symbol,
        "strategy": spread["strategy"],
        "expiration": spread["expiration"],
        "side": "Short / Credit",
        "entry_price": spread["net_credit"],
        "legs": spread["legs"],
        "notes": (
            f"{spread['bucket']} income candidate; "
            f"target width ${spread['target_width']:,.2f}; "
            f"actual width ${spread['actual_width']:,.2f}; "
            f"estimated max profit ${spread['max_profit']:,.2f}; "
            f"estimated max loss ${spread['max_loss']:,.2f}; "
            f"breakeven {spread['breakeven']}."
        ),
    }
    st.switch_page("pages/6_Trade_Journal.py")


configure_page("Strategy Selector")
page_header(
    "Strategy Selector",
    "Symbol-driven stock and options research using Public market data.",
)

trade_tab, income_tab = st.tabs(["Trade Suggestion", "Income Options"])

with trade_tab:
    with st.form("symbol_strategy_form"):
        c1, c2 = st.columns(2)
        symbol = c1.text_input("Symbol", value="SPY").strip().upper()
        horizon = c2.selectbox("Time horizon", HORIZONS)
        c3, c4 = st.columns(2)
        risk_tolerance = c3.selectbox(
            "Risk tolerance",
            ["Conservative", "Moderate", "Aggressive"],
        )
        objective = c4.selectbox(
            "Objective",
            ["Directional", "Income", "Hedging"],
        )
        submitted = st.form_submit_button(
            "Analyze Symbol",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        st.session_state["strategy_analysis_request"] = {
            "symbol": symbol,
            "horizon": horizon,
            "risk_tolerance": risk_tolerance,
            "objective": objective,
        }

    request = st.session_state.get("strategy_analysis_request")
    if request:
        analysis, source = symbol_analysis(request["symbol"])
        st.caption(f"Data source: {source}")

        if analysis is None:
            empty_state(
                "Symbol analysis is unavailable.",
                "Verify the ticker and Public API connection in Settings.",
            )
        else:
            metrics = st.columns(6)
            metrics[0].metric("Last", f"${analysis['last']:,.2f}")
            metrics[1].metric(
                "Today",
                (
                    f"{analysis['change_pct']:+.2f}%"
                    if analysis["change_pct"] is not None
                    else "N/A"
                ),
            )
            metrics[2].metric("5-Day", f"{analysis['return_5d']:+.2f}%")
            metrics[3].metric("20-Day", f"{analysis['return_20d']:+.2f}%")
            metrics[4].metric("ATR", f"{analysis['atr_pct']:.2f}%")
            metrics[5].metric("Trend Score", analysis["trend_score"])

            primary, alternatives = primary_strategy_idea(
                analysis["outlook"],
                analysis["volatility"],
                request["risk_tolerance"],
                request["objective"],
                request["horizon"],
            )

            st.subheader(f"{analysis['symbol']} Research Suggestion")
            st.markdown(f"### {primary['strategy']}")
            st.dataframe(
                [
                    {
                        "Market view": analysis["outlook"],
                        "Volatility regime": analysis["volatility"],
                        "Vehicle": primary["vehicle"],
                        "Structure": primary["structure"],
                        "Why it fits": primary["fit"],
                        "Defined risk": primary["risk"],
                    }
                ],
                use_container_width=True,
                hide_index=True,
            )

            st.subheader("Alternatives")
            st.dataframe(alternatives, use_container_width=True, hide_index=True)

            st.subheader("Risk Budget")
            b1, b2, b3 = st.columns(3)
            capital = b1.number_input(
                "Account capital",
                min_value=0.0,
                value=10000.0,
                step=500.0,
            )
            risk_pct = b2.slider(
                "Risk per trade (%)",
                0.1,
                5.0,
                1.0,
                0.1,
            )
            max_option_loss = b3.number_input(
                "Maximum loss per option position",
                min_value=1.0,
                value=200.0,
                step=25.0,
            )
            risk_dollars = capital * (risk_pct / 100)
            stop_distance = analysis["last"] * (analysis["atr_pct"] / 100) * 2
            share_count = int(risk_dollars / stop_distance) if stop_distance else 0
            option_count = (
                int(risk_dollars / max_option_loss) if max_option_loss else 0
            )

            sizes = st.columns(3)
            sizes[0].metric("Risk Budget", f"${risk_dollars:,.2f}")
            sizes[1].metric("Stock Size at 2 ATR", f"{share_count:,} shares")
            sizes[2].metric(
                "Defined-Risk Option Size",
                f"{option_count:,} positions",
            )

with income_tab:
    with st.form("income_options_form"):
        i1, i2, i3 = st.columns(3)
        income_symbol = i1.text_input(
            "Income ticker",
            value="SPY",
            help="Works with optionable ETFs/stocks such as SPY, QQQ, DIA, IWM, and index symbols such as SPX when supported by Public.",
        ).strip().upper()
        spread_bias = i2.selectbox(
            "Spread bias",
            ["Auto from trend", "Bullish", "Neutral", "Bearish"],
        )
        width_choice = i3.selectbox(
            "Spread width",
            ["Auto", "$1 wide", "$2 wide", "$3 wide", "$5 wide", "$10 wide"],
            index=2,
        )
        income_submitted = st.form_submit_button(
            "Build Income Spreads",
            type="primary",
            use_container_width=True,
        )

    if income_submitted:
        st.session_state["income_options_request"] = {
            "symbol": income_symbol,
            "bias": spread_bias,
            "width": None
            if width_choice == "Auto"
            else float(width_choice.replace("$", "").replace(" wide", "")),
            "width_label": width_choice,
        }

    income_request = st.session_state.get("income_options_request")
    if income_request:
        analysis, source = symbol_analysis(income_request["symbol"])
        st.caption(f"Data source: {source} + Public option chain")

        if analysis is None:
            empty_state(
                "Income analysis is unavailable.",
                "Verify the ticker is optionable and the Public connection is active.",
            )
        else:
            outlook = (
                analysis["outlook"]
                if income_request["bias"] == "Auto from trend"
                else income_request["bias"]
            )
            try:
                expirations = get_public_option_expirations(
                    income_request["symbol"]
                )
                buckets = select_expiration_buckets(expirations)
                candidates = {}
                for bucket, expiration in buckets.items():
                    chain = get_public_option_chain(
                        income_request["symbol"],
                        expiration,
                    )
                    candidates[bucket] = build_income_spread(
                        chain,
                        float(analysis["last"]),
                        outlook,
                        bucket,
                        spread_width=income_request["width"],
                    )
            except Exception:
                candidates = {}

            header_metrics = st.columns(4)
            header_metrics[0].metric(
                "Underlying",
                f"${analysis['last']:,.2f}",
            )
            header_metrics[1].metric("Trend", outlook)
            header_metrics[2].metric(
                "20-Day Return",
                f"{analysis['return_20d']:+.2f}%",
            )
            header_metrics[3].metric(
                "Realized Volatility",
                analysis["volatility"],
            )
            st.caption(
                f"Requested width: {income_request.get('width_label', 'Auto')}. "
                "If the exact strike width is not listed, AlphaOS uses the nearest available protection leg."
            )

            if not candidates or not any(candidates.values()):
                empty_state(
                    "No viable income spread was found.",
                    "The selected chain may lack liquid contracts with valid bid and ask prices.",
                )
            else:
                bucket_tabs = st.tabs(["Day Trade", "Weekly", "Monthly"])
                for tab, bucket in zip(
                    bucket_tabs,
                    ["Day Trade", "Weekly", "Monthly"],
                ):
                    with tab:
                        spread = candidates.get(bucket)
                        if spread is None:
                            empty_state(
                                f"No {bucket.lower()} spread is available.",
                                "Try another ticker or directional bias.",
                            )
                            continue

                        st.subheader(spread["strategy"])
                        st.caption(
                            f"Expiration: {spread['expiration']} - "
                            f"{spread['expiration_note']}"
                        )
                        spread_metrics = st.columns(4)
                        spread_metrics[0].metric(
                            "Estimated Credit",
                            f"${spread['net_credit']:,.2f}",
                        )
                        spread_metrics[1].metric(
                            "Actual Width",
                            f"${spread['actual_width']:,.2f}",
                        )
                        spread_metrics[2].metric(
                            "Max Profit",
                            f"${spread['max_profit']:,.2f}",
                        )
                        spread_metrics[3].metric(
                            "Max Loss",
                            f"${spread['max_loss']:,.2f}",
                        )
                        st.metric(
                            "Breakeven",
                            spread["breakeven"],
                        )
                        st.dataframe(
                            spread["legs"],
                            use_container_width=True,
                            hide_index=True,
                        )
                        if st.button(
                            "Load into Trade Journal",
                            key=f"load_{bucket}",
                            use_container_width=True,
                        ):
                            load_spread_into_journal(
                                income_request["symbol"],
                                spread,
                            )

st.caption(
    "Research only. Option estimates use current midpoint data and may not be fillable. Day-trade candidates use same-day expiration when listed; otherwise the nearest available expiration is shown. AlphaOS does not place orders."
)
