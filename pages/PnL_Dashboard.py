import plotly.express as px
import streamlit as st

from modules.auth import get_current_user
from modules.data import get_account_snapshot
from modules.metrics import compute_trade_metrics, pnl_by_period
from modules.ui import configure_page, metric_card, page_header


configure_page("P&L Dashboard")
page_header("P&L Dashboard", "Closed-trade analytics for daily, weekly, and monthly performance.")

user = get_current_user()
snapshot = get_account_snapshot(user_id=user.get("id") if user else None)
trades = snapshot["trades"]
metrics = compute_trade_metrics(trades)

cols = st.columns(6)
with cols[0]:
    metric_card("Net P&L", metrics["net_pnl"], prefix="$")
with cols[1]:
    metric_card("Trades", metrics["trade_count"])
with cols[2]:
    metric_card("Win Rate", metrics["win_rate"], suffix="%")
with cols[3]:
    metric_card("Avg Win", metrics["average_win"], prefix="$")
with cols[4]:
    metric_card("Avg Loss", metrics["average_loss"], prefix="$")
with cols[5]:
    metric_card("Profit Factor", metrics["profit_factor"])

period_label = st.radio(
    "Period",
    options=["Daily", "Weekly", "Monthly"],
    index=0,
    horizontal=True,
)
period_map = {"Daily": "D", "Weekly": "W", "Monthly": "M"}
period_df = pnl_by_period(trades, period_map[period_label])

if period_df.empty:
    st.info("No closed trades available for the selected period.")
else:
    st.plotly_chart(
        px.bar(period_df, x="period", y="pnl", title=f"{period_label} P&L"),
        use_container_width=True,
    )

