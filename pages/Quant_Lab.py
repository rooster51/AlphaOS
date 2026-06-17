import plotly.express as px
import streamlit as st

from modules.mock_market import SYMBOLS, get_mock_price_history
from modules.ui import configure_page, page_header


configure_page("Quant Lab")
page_header("Quant Lab", "Prototype factor ideas against mock market data.")

symbol = st.selectbox("Symbol", SYMBOLS, index=1)
lookback = st.slider("Moving average lookback", 5, 60, 20)
history = get_mock_price_history(symbol, periods=120)
history["moving_average"] = history["close"].rolling(lookback).mean()
history["score"] = (history["close"] > history["moving_average"]).astype(int) * 100

fig = px.line(history, x="date", y=["close", "moving_average"], title=f"{symbol} Moving Average Prototype")
st.plotly_chart(fig, use_container_width=True)

st.metric("Latest Placeholder Score", int(history["score"].iloc[-1]))
st.caption("Quant Lab is intentionally research-only in the MVP.")

