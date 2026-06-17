import plotly.express as px
import streamlit as st

from modules.mock_market import SYMBOLS, get_market_pulse, get_mock_price_history
from modules.ui import configure_page, page_header


configure_page("Market Pulse")
page_header("Market Pulse", "Mock breadth, trend, and macro context for the MVP.")

symbol = st.selectbox("Symbol", SYMBOLS, index=0)
history = get_mock_price_history(symbol)

cols = st.columns(3)
for col, item in zip(cols, get_market_pulse()[:3]):
    with col:
        st.metric(item["symbol"], item["signal"], f"{item['change']}%")

st.plotly_chart(
    px.line(history, x="date", y="close", title=f"{symbol} Mock Price Trend"),
    use_container_width=True,
)

st.dataframe(get_market_pulse(), use_container_width=True, hide_index=True)

