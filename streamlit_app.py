import streamlit as st

from modules.auth import get_current_user, sign_in_form, sign_out_button
from modules.data import get_account_snapshot, get_watchlist
from modules.market_data import brokerage_positions, market_pulse
from modules.metrics import compute_trade_metrics
from modules.ui import (
    configure_page,
    empty_state,
    metric_card,
    page_header,
    require_auth_notice,
    render_nav_hint,
)


configure_page("AlphaOS Dashboard")

page_header(
    "AlphaOS",
    "Cloud trading operating system for journaling, risk, P&L, and market context.",
)

user = get_current_user()
with st.sidebar:
    st.markdown("### AlphaOS")
    st.caption("Streamlit Cloud MVP")
    if user:
        st.success(user.get("email", "Signed in"))
        sign_out_button()
    else:
        sign_in_form()
    render_nav_hint()

if not user:
    require_auth_notice()
    st.info("Supabase credentials are optional for local preview. Configure Streamlit secrets to enable cloud auth and persistence.")

snapshot = get_account_snapshot(user_id=user.get("id") if user else None)
trades = snapshot.get("trades", [])
positions = snapshot.get("open_positions", [])
public_positions, public_portfolio, position_source = brokerage_positions(user)
if position_source == "Public.com Live":
    positions = public_positions
watchlist = get_watchlist(user_id=user.get("id") if user else None)
metrics = compute_trade_metrics(trades)
pulse, pulse_source = market_pulse()

st.subheader("Dashboard")

cols = st.columns(4)
with cols[0]:
    metric_card("Net P&L", metrics["net_pnl"], prefix="$")
with cols[1]:
    metric_card("Win Rate", metrics["win_rate"], suffix="%")
with cols[2]:
    metric_card("Profit Factor", metrics["profit_factor"])
with cols[3]:
    metric_card("Max Drawdown", metrics["max_drawdown"], prefix="$")

st.divider()

left, right = st.columns([1.35, 1])
with left:
    st.markdown("#### Open Positions")
    if position_source == "Public.com Live":
        st.caption("Public.com Live")
    if positions:
        st.dataframe(positions, use_container_width=True, hide_index=True)
    else:
        empty_state("No open positions yet.", "Add entries from the Trade Journal page.")

with right:
    st.markdown("#### Market Pulse")
    st.caption(pulse_source)
    for item in pulse[:4]:
        st.write(f"**{item['symbol']}** - {item['signal']} - Score {item['score']}")
    if not pulse:
        empty_state("Live market pulse is unavailable.")
    st.page_link(
        "pages/5_Budget_Strategy_Selector.py",
        label="Open Strategy Suggestions",
    )

st.divider()

st.markdown("#### Watchlist")
if watchlist:
    st.dataframe(watchlist, use_container_width=True, hide_index=True)
else:
    empty_state("No watchlist symbols.", "Use Settings to add the markets you want to follow.")
