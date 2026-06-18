from datetime import date

import streamlit as st

from modules.auth import get_current_user
from modules.data import add_trade, get_account_snapshot, trades_dataframe
from modules.ui import configure_page, empty_state, page_header


configure_page("Trade Journal")
page_header("Trade Journal", "Manual entries for open positions and closed trades.")

user = get_current_user()

with st.form("trade_form"):
    c1, c2, c3 = st.columns(3)
    symbol = c1.text_input("Symbol", value="SPY").upper()
    side = c2.selectbox("Side", ["Long", "Short"])
    status = c3.selectbox("Status", ["Open", "Closed"])

    c4, c5, c6 = st.columns(3)
    entry_date = c4.date_input("Entry date", value=date.today())
    exit_date = c5.date_input("Exit date", value=date.today(), disabled=status == "Open")
    strategy = c6.text_input("Strategy", value="Momentum")

    c7, c8, c9 = st.columns(3)
    quantity = c7.number_input("Quantity", min_value=0.0, value=1.0, step=1.0)
    entry_price = c8.number_input("Entry price", min_value=0.0, value=100.0, step=0.01)
    exit_price = c9.number_input("Exit price", min_value=0.0, value=101.0, step=0.01, disabled=status == "Open")

    notes = st.text_area("Notes")
    submitted = st.form_submit_button("Save trade", use_container_width=True)

if submitted:
    multiplier = 1 if side == "Long" else -1
    pnl = None if status == "Open" else (exit_price - entry_price) * quantity * multiplier
    add_trade(
        {
            "symbol": symbol,
            "side": side,
            "entry_date": str(entry_date),
            "exit_date": None if status == "Open" else str(exit_date),
            "quantity": quantity,
            "entry_price": entry_price,
            "exit_price": None if status == "Open" else exit_price,
            "pnl": pnl,
            "status": status,
            "strategy": strategy,
            "notes": notes,
        },
        user_id=user.get("id") if user else None,
    )
    st.success("Trade saved.")

snapshot = get_account_snapshot(user_id=user.get("id") if user else None)
df = trades_dataframe(snapshot["trades"])

st.subheader("Trade Log")
if df.empty:
    empty_state("No trades saved yet.")
else:
    st.dataframe(df, use_container_width=True, hide_index=True)
