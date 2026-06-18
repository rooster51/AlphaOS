import streamlit as st

from modules.ui import configure_page, page_header


configure_page("Budget Strategy Selector")
page_header("Budget Strategy Selector", "Translate account risk into position and strategy limits.")

capital = st.number_input("Account capital", min_value=0.0, value=10000.0, step=500.0)
risk_pct = st.slider("Risk per trade (%)", 0.1, 5.0, 1.0, 0.1)
stop_distance = st.number_input("Stop distance per share/contract", min_value=0.01, value=2.0, step=0.25)
strategy = st.selectbox("Strategy", ["Momentum", "Pullback", "Breakout", "Mean Reversion", "Swing Core"])

risk_dollars = capital * (risk_pct / 100)
size = int(risk_dollars / stop_distance) if stop_distance else 0

cols = st.columns(3)
cols[0].metric("Risk Budget", f"${risk_dollars:,.2f}")
cols[1].metric("Suggested Size", f"{size:,}")
cols[2].metric("Strategy", strategy)

st.info("This selector is for planning and journaling only. AlphaOS does not execute trades.")
