import plotly.express as px
import streamlit as st

from modules.market_data import market_pulse, price_history
from modules.mock_market import SYMBOLS
from modules.ui import configure_page, page_header


configure_page("Market Pulse")
page_header("Market Pulse", "Live pricing with placeholder trend scores.")

symbol = st.selectbox("Symbol", SYMBOLS, index=0)
history, history_source = price_history(symbol)
pulse, pulse_source = market_pulse()

if history_source == "Public.com Live" and pulse_source == "Public.com Live":
    st.success("Data source: Public.com Live")
else:
    st.warning("Public data is unavailable. Showing mock fallback data.")

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
st.caption("Trend signals and scores remain placeholders; prices and changes are live when Public is connected.")

