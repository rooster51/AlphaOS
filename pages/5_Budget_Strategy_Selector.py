import streamlit as st

from modules.market_data import symbol_analysis
from modules.strategies import primary_strategy_idea
from modules.ui import configure_page, empty_state, page_header


configure_page("Strategy Suggestions")
page_header(
    "Strategy Suggestions",
    "Symbol-driven research using Public live and historical market data.",
)

with st.form("symbol_strategy_form"):
    c1, c2 = st.columns(2)
    symbol = c1.text_input("Symbol", value="SPY").strip().upper()
    horizon = c2.selectbox(
        "Time horizon",
        [
            "Swing (2-8 weeks)",
            "Intermediate (2-6 months)",
            "Long term (6+ months)",
        ],
    )
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
        st.dataframe(
            alternatives,
            use_container_width=True,
            hide_index=True,
        )

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
        option_count = int(risk_dollars / max_option_loss) if max_option_loss else 0

        sizes = st.columns(3)
        sizes[0].metric("Risk Budget", f"${risk_dollars:,.2f}")
        sizes[1].metric("Stock Size at 2 ATR", f"{share_count:,} shares")
        sizes[2].metric("Defined-Risk Option Size", f"{option_count:,} positions")

        st.info(
            "Research and planning only. The suggestion uses price trend and realized volatility, not your complete financial circumstances or options implied volatility. AlphaOS does not execute trades."
        )
