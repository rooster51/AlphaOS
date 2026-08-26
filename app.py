import streamlit as st

from modules.auth import get_current_user, sign_in_form, sign_out_button
from modules.market_data import dashboard_pulse
from modules.ui import configure_page, empty_state, page_header, require_auth_notice, render_nav_hint


configure_page("AlphaOS")

page_header(
    "AlphaOS",
    "Barebones spread scanner, strategy selector, and Pulse backtest lab.",
)

user = get_current_user()
with st.sidebar:
    st.markdown("### AlphaOS")
    st.caption("Streamlit Cloud")
    if user:
        st.success(user.get("email", "Signed in"))
        sign_out_button()
    else:
        sign_in_form()
    render_nav_hint()

if not user:
    require_auth_notice()
    st.info("Configure Supabase and API keys in Streamlit secrets for cloud auth and live data.")

st.subheader("Core Workflow")
cards = st.columns(3)
with cards[0]:
    st.markdown("#### Scanner")
    st.write("Scan SPX, XSP, SPY, QQQ, IWM, and DIA for current market context.")
    st.page_link("pages/4_Scanner.py", label="Open Scanner")
with cards[1]:
    st.markdown("#### Strategy Selector")
    st.write("Generate debit spreads, credit spreads, and iron condors with defined risk.")
    st.page_link("pages/5_Strategy_Selector.py", label="Open Strategy Selector")
with cards[2]:
    st.markdown("#### Quant Lab")
    st.write("Run the 30-minute Pulse Bar backtest when valid intraday data is available.")
    st.page_link("pages/8_Quant_Lab.py", label="Open Quant Lab")

st.divider()

st.markdown("#### Market Pulse")
pulse, pulse_source = dashboard_pulse()
st.caption(pulse_source)
if pulse:
    st.dataframe(pulse, use_container_width=True, hide_index=True)
else:
    empty_state("Live market pulse is unavailable.")
