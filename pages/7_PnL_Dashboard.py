from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from modules.auth import get_current_user
from modules.data import (
    get_account_snapshot,
    get_daily_pnl_snapshots,
    save_daily_pnl_snapshot,
)
from modules.market_data import brokerage_positions
from modules.metrics import compute_trade_metrics, pnl_by_period
from modules.ui import configure_page, empty_state, metric_card, page_header


configure_page("P&L Dashboard")
page_header(
    "P&L Dashboard",
    "Live brokerage positions and closed-trade journal analytics.",
)

user = get_current_user()
user_id = user.get("id") if user else None
snapshot = get_account_snapshot(user_id=user_id)
trades = snapshot["trades"]
manual_metrics = compute_trade_metrics(trades)

brokerage_tab, journal_tab, growth_tab = st.tabs(
    ["Brokerage Account", "Trade Journal", "Growth Plan"]
)

with brokerage_tab:
    if st.button("Refresh Live Brokerage P&L", type="primary", use_container_width=True):
        with st.spinner("Loading Public brokerage data..."):
            st.session_state["brokerage_pnl_snapshot"] = brokerage_positions(user)

    positions, portfolio, position_source = st.session_state.get(
        "brokerage_pnl_snapshot",
        ([], {}, "Not loaded"),
    )

    if position_source != "Public.com Live":
        empty_state(
            "Live brokerage P&L is unavailable.",
            "Click Refresh Live Brokerage P&L after signing in with the owner account.",
        )
    else:
        unrealized_pnl = sum(
            float(position.get("unrealized_pnl") or 0) for position in positions
        )
        equity = float(portfolio.get("equity") or 0)
        buying_power = float(portfolio.get("buying_power") or 0)
        save_daily_pnl_snapshot(user_id, equity, unrealized_pnl)

        cols = st.columns(4)
        with cols[0]:
            metric_card("Account Equity", equity, prefix="$")
        with cols[1]:
            metric_card("Open P&L", unrealized_pnl, prefix="$")
        with cols[2]:
            metric_card("Buying Power", buying_power, prefix="$")
        with cols[3]:
            metric_card("Open Positions", len(positions))

        st.caption(
            f"Source: Public.com Live, account ending in {str(portfolio.get('account_id', ''))[-4:]}"
        )

        snapshots = pd.DataFrame(get_daily_pnl_snapshots(user_id))
        if not snapshots.empty:
            snapshots["snapshot_date"] = pd.to_datetime(
                snapshots["snapshot_date"], errors="coerce"
            )
            snapshots["equity"] = pd.to_numeric(
                snapshots["equity"], errors="coerce"
            )
            snapshots = snapshots.dropna(
                subset=["snapshot_date", "equity"]
            ).sort_values("snapshot_date")

        st.subheader("Account Change")
        change_cols = st.columns(3)
        windows = [("Daily", 1), ("Weekly", 7), ("Monthly", 30)]
        for col, (label, days) in zip(change_cols, windows):
            cutoff = pd.Timestamp(date.today() - timedelta(days=days))
            eligible = (
                snapshots[snapshots["snapshot_date"] <= cutoff]
                if not snapshots.empty
                else pd.DataFrame()
            )
            change = (
                equity - float(eligible.iloc[-1]["equity"])
                if not eligible.empty
                else None
            )
            col.metric(
                f"{label} Equity Change",
                f"${change:,.2f}" if change is not None else "Collecting data",
            )

        st.caption(
            "Equity changes require an earlier daily snapshot and may include deposits or withdrawals."
        )

        if not snapshots.empty:
            st.plotly_chart(
                px.line(
                    snapshots,
                    x="snapshot_date",
                    y="equity",
                    markers=True,
                    title="Recorded Account Equity",
                ),
                use_container_width=True,
            )

        st.subheader("Open Positions")
        if positions:
            st.dataframe(positions, use_container_width=True, hide_index=True)
        else:
            empty_state("No open brokerage positions.")

with journal_tab:
    metrics = manual_metrics

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
        empty_state(
            "No closed journal trades yet.",
            "Save a trade with status Closed and an exit price to calculate realized P&L.",
        )
    else:
        st.plotly_chart(
            px.bar(
                period_df,
                x="period",
                y="pnl",
                title=f"{period_label} Realized P&L",
            ),
            use_container_width=True,
        )

    st.caption(
        "Journal analytics use manually entered closed trades. Open brokerage P&L appears in the Brokerage Account tab."
    )

with growth_tab:
    st.subheader("Portfolio Growth Plan")
    g1, g2, g3 = st.columns(3)
    current_value = g1.number_input(
        "Current portfolio value",
        min_value=0.0,
        value=10000.0,
        step=500.0,
    )
    target_value = g2.number_input(
        "Target portfolio value",
        min_value=0.0,
        value=25000.0,
        step=500.0,
    )
    target_days = g3.number_input(
        "Target days",
        min_value=1,
        value=90,
        step=1,
    )

    gap = max(0.0, target_value - current_value)
    daily_dollars = gap / target_days if target_days else 0.0
    daily_pct = (
        ((target_value / current_value) ** (1 / target_days) - 1) * 100
        if current_value > 0 and target_value > current_value and target_days > 0
        else 0.0
    )
    weekly_pct = ((1 + daily_pct / 100) ** 5 - 1) * 100
    monthly_pct = ((1 + daily_pct / 100) ** 21 - 1) * 100

    plan_cols = st.columns(4)
    plan_cols[0].metric("Growth Needed", f"${gap:,.2f}")
    plan_cols[1].metric("Per Day", f"${daily_dollars:,.2f}")
    plan_cols[2].metric("Daily %", f"{daily_pct:.2f}%")
    plan_cols[3].metric("Monthly %", f"{monthly_pct:.2f}%")

    schedule = pd.DataFrame(
        [
            {
                "Cadence": "Daily",
                "Required $": round(daily_dollars, 2),
                "Required %": round(daily_pct, 2),
            },
            {
                "Cadence": "Weekly / 5 trading days",
                "Required $": round(daily_dollars * 5, 2),
                "Required %": round(weekly_pct, 2),
            },
            {
                "Cadence": "Monthly / 21 trading days",
                "Required $": round(daily_dollars * 21, 2),
                "Required %": round(monthly_pct, 2),
            },
        ]
    )
    st.dataframe(schedule, use_container_width=True, hide_index=True)

    realized_pnl = float(manual_metrics.get("net_pnl", 0.0))
    if gap > 0:
        progress = min(1.0, max(0.0, realized_pnl / gap))
        st.progress(progress)
        st.caption(
            f"Manual journal realized P&L covers {progress * 100:.1f}% of the remaining target gap."
        )
    else:
        st.success("Current value is already at or above the target.")

    st.caption(
        "Growth targets are planning math only. They do not account for drawdowns, deposits, withdrawals, slippage, taxes, or changing risk."
    )
