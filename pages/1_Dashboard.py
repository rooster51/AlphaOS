import streamlit as st

from modules.auth import get_current_user
from modules.data import get_account_snapshot, get_watchlist
from modules.metrics import compute_trade_metrics
from modules.mock_market import get_market_pulse
from modules.ui import empty_state, metric_card, page_header


page_header("Dashboard", "Account snapshot, open risk, watchlist, and market context.")

user = get_current_user()
snapshot = get_account_snapshot(user_id=user.get("id") if user else None)
trades = snapshot.get("trades", [])
positions = snapshot.get("open_positions", [])
watchlist = get_watchlist(user_id=user.get("id") if user else None)
metrics = compute_trade_metrics(trades)
pulse = get_market_pulse()

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
    if positions:
        st.dataframe(positions, use_container_width=True, hide_index=True)
    else:
        empty_state("No open positions yet.", "Add entries from the Trade Journal page.")

with right:
    st.markdown("#### Market Pulse")
    for item in pulse[:4]:
        st.write(f"**{item['symbol']}** - {item['signal']} - Score {item['score']}")

st.divider()

st.markdown("#### Watchlist")
if watchlist:
    st.dataframe(watchlist, use_container_width=True, hide_index=True)
else:
    empty_state("No watchlist symbols.", "Use Settings to add the markets you want to follow.")
