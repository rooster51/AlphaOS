import plotly.express as px
import streamlit as st

from modules.market_data import MARKET_SYMBOLS, market_pulse, price_history
from modules.ui import configure_page, empty_state, page_header


configure_page("Market Pulse")
page_header("Market Pulse", "Live trend context calculated from Public market data.")

symbol = st.selectbox("Symbol", MARKET_SYMBOLS, index=0)
history, history_source = price_history(symbol)
pulse, pulse_source = market_pulse()

st.caption(f"Data sources: {pulse_source}; {history_source}")
if history.empty or not pulse:
    empty_state(
        "Live market data is unavailable.",
        "Check the Public API key and marketdata scope in Settings.",
    )
    st.stop()

cols = st.columns(3)
for col, item in zip(cols, pulse[:3]):
    with col:
        value = item.get("last")
        display_value = f"${value:,.2f}" if value is not None else item["signal"]
        change = item.get("change")
        delta = f"{change:+.2f}%" if change is not None else None
        st.metric(item["symbol"], display_value, delta)

st.plotly_chart(
    px.line(history, x="date", y="close", title=f"{symbol} Price Trend"),
    use_container_width=True,
)

st.dataframe(pulse, use_container_width=True, hide_index=True)
st.caption("Score uses 5-day and 20-day returns plus position relative to the 20-day moving average.")
