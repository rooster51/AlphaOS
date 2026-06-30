import streamlit as st

from modules.strategies import strategy_ideas
from modules.ui import configure_page, page_header


configure_page("Budget Strategy Selector")
page_header("Strategy Suggestions", "Compare stock, LEAPS, and defined-risk spread candidates.")

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
s1, s2, s3 = st.columns(3)
outlook = s1.selectbox(
    "Market outlook",
    ["Bullish", "Bearish", "Neutral", "Large move / uncertain direction"],
)
volatility = s2.selectbox("Implied volatility", ["Normal", "High", "Low"])
risk_tolerance = s3.selectbox("Risk tolerance", ["Conservative", "Moderate", "Aggressive"])
s4, s5 = st.columns(2)
objective = s4.selectbox("Objective", ["Directional", "Income", "Hedging"])
horizon = s5.selectbox(
    "Time horizon",
    ["Swing (2-8 weeks)", "Intermediate (2-6 months)", "Long term (6+ months)"],
)

ideas = strategy_ideas(
    outlook,
    volatility,
    risk_tolerance,
    objective,
    horizon,
)
st.dataframe(ideas, use_container_width=True, hide_index=True)

st.info("Research and planning only. Suggestions do not consider your full financial situation, and AlphaOS does not execute trades.")
