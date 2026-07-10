import plotly.express as px
import streamlit as st

from modules.market_data import MARKET_SYMBOLS, dashboard_pulse, price_history
from modules.ui import configure_page, empty_state, page_header


configure_page("Market Pulse")
page_header("Market Pulse", "Live trend context calculated from Public market data.")

symbol = st.selectbox("Symbol", MARKET_SYMBOLS, index=0)
if st.button("Refresh Market Pulse", type="primary", use_container_width=True):
    with st.spinner("Loading market data..."):
        st.session_state["market_pulse_view"] = {
            "history": price_history(symbol),
            "pulse": dashboard_pulse(),
        }

view = st.session_state.get("market_pulse_view")
if not view:
    empty_state("Market pulse is ready.", "Click Refresh Market Pulse to load live data.")
    st.stop()

history, history_source = view["history"]
pulse, pulse_source = view["pulse"]

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
st.caption("Dashboard pulse uses live quote changes. The selected chart uses Public historical bars.")
