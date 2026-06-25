import plotly.express as px
import streamlit as st

from modules.market_data import price_history
from modules.mock_market import SYMBOLS
from modules.ui import configure_page, page_header


configure_page("Quant Lab")
page_header("Quant Lab", "Prototype factor ideas against live bars when connected.")

symbol = st.selectbox("Symbol", SYMBOLS, index=1)
lookback = st.slider("Moving average lookback", 5, 60, 20)
history, source = price_history(symbol)
history["moving_average"] = history["close"].rolling(lookback).mean()
history["score"] = (history["close"] > history["moving_average"]).astype(int) * 100
st.caption(f"Data source: {source}")

fig = px.line(history, x="date", y=["close", "moving_average"], title=f"{symbol} Moving Average Prototype")
st.plotly_chart(fig, use_container_width=True)

st.metric("Latest Placeholder Score", int(history["score"].iloc[-1]))
st.caption("Quant Lab is intentionally research-only in the MVP.")
