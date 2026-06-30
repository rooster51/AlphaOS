import streamlit as st

from modules.strategies import strategy_ideas
from modules.ui import configure_page, page_header


configure_page("Budget Strategy Selector")
page_header("Budget Strategy Selector", "Match a research strategy and position limit to your risk budget.")

capital = st.number_input("Account capital", min_value=0.0, value=10000.0, step=500.0)
risk_pct = st.slider("Risk per trade (%)", 0.1, 5.0, 1.0, 0.1)
position_type = st.radio(
    "Position type",
    ["Shares", "Defined-risk options"],
    index=0,
    horizontal=True,
)
loss_per_unit_label = (
    "Stop distance per share"
    if position_type == "Shares"
    else "Maximum loss per spread/contract"
)
loss_per_unit = st.number_input(
    loss_per_unit_label,
    min_value=0.01,
    value=2.0 if position_type == "Shares" else 100.0,
    step=0.25 if position_type == "Shares" else 10.0,
)

risk_dollars = capital * (risk_pct / 100)
size = int(risk_dollars / loss_per_unit) if loss_per_unit else 0

cols = st.columns(2)
cols[0].metric("Risk Budget", f"${risk_dollars:,.2f}")
cols[1].metric(
    "Suggested Size",
    f"{size:,} {'shares' if position_type == 'Shares' else 'contracts'}",
)

st.subheader("Potential Strategies")
s1, s2, s3, s4 = st.columns(4)
outlook = s1.selectbox(
    "Market outlook",
    ["Bullish", "Bearish", "Neutral", "Large move / uncertain direction"],
)
volatility = s2.selectbox("Implied volatility", ["Normal", "High", "Low"])
risk_tolerance = s3.selectbox("Risk tolerance", ["Conservative", "Moderate", "Aggressive"])
objective = s4.selectbox("Objective", ["Directional", "Income", "Hedging"])

ideas = strategy_ideas(outlook, volatility, risk_tolerance, objective)
st.dataframe(ideas, use_container_width=True, hide_index=True)

st.info("Research and planning only. Suggestions do not consider your full financial situation, and AlphaOS does not execute trades.")
