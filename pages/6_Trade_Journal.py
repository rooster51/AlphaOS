from datetime import date

import streamlit as st

from modules.auth import get_current_user
from modules.data import add_trade, get_account_snapshot, trades_dataframe
from modules.strategies import strategies_for_instrument, strategy_ideas
from modules.ui import configure_page, empty_state, page_header


configure_page("Trade Journal")
page_header("Trade Journal", "Manual entries for open positions and closed trades.")

user = get_current_user()

with st.expander("Strategy ideas", expanded=False):
    i1, i2, i3, i4 = st.columns(4)
    idea_outlook = i1.selectbox(
        "Market outlook",
        ["Bullish", "Bearish", "Neutral", "Large move / uncertain direction"],
    )
    idea_volatility = i2.selectbox("Implied volatility", ["Normal", "High", "Low"])
    idea_risk = i3.selectbox("Risk tolerance", ["Conservative", "Moderate", "Aggressive"])
    idea_objective = i4.selectbox("Objective", ["Directional", "Income", "Hedging"])
    idea_horizon = st.selectbox(
        "Time horizon",
        ["Swing (2-8 weeks)", "Intermediate (2-6 months)", "Long term (6+ months)"],
    )
    ideas = strategy_ideas(
        idea_outlook,
        idea_volatility,
        idea_risk,
        idea_objective,
        idea_horizon,
    )
    st.dataframe(ideas, use_container_width=True, hide_index=True)
    st.caption("Educational research ideas only. Review liquidity, assignment, expiration, and maximum-loss risks before entering any options trade.")

with st.form("trade_form"):
    c1, c2, c3 = st.columns(3)
    symbol = c1.text_input("Symbol", value="SPY").upper()
    instrument_type = c2.selectbox(
        "Instrument",
        ["Stock", "ETF", "Option", "Option Spread"],
    )
    status = c3.selectbox("Status", ["Open", "Closed"])

    c4, c5, c6 = st.columns(3)
    entry_date = c4.date_input("Entry date", value=date.today())
    exit_date = c5.date_input("Exit date", value=date.today(), disabled=status == "Open")
    strategy_choice = c6.selectbox(
        "Strategy",
        strategies_for_instrument(instrument_type) + ["Custom"],
    )

    c7, c8, c9 = st.columns(3)
    side_options = (
        ["Long / Debit", "Short / Credit"]
        if instrument_type in {"Option", "Option Spread"}
        else ["Long", "Short"]
    )
    side_choice = c7.selectbox("Position type", side_options)
    quantity_label = "Contracts" if instrument_type in {"Option", "Option Spread"} else "Shares"
    quantity = c8.number_input(quantity_label, min_value=0.0, value=1.0, step=1.0)
    fees = c9.number_input("Total fees", min_value=0.0, value=0.0, step=0.01)

    custom_strategy = ""
    if strategy_choice == "Custom":
        custom_strategy = st.text_input("Custom strategy name")

    c10, c11 = st.columns(2)
    price_label = "Net entry premium" if instrument_type in {"Option", "Option Spread"} else "Entry price"
    exit_label = "Net exit premium" if instrument_type in {"Option", "Option Spread"} else "Exit price"
    entry_price = c10.number_input(price_label, min_value=0.0, value=1.0, step=0.01)
    exit_price = c11.number_input(
        exit_label,
        min_value=0.0,
        value=1.0,
        step=0.01,
        disabled=status == "Open",
    )

    expiration = None
    spread_legs = ""
    if instrument_type in {"Option", "Option Spread"}:
        expiration = st.date_input("Expiration", value=date.today())
    if instrument_type == "Option Spread":
        spread_legs = st.text_area(
            "Spread legs",
            placeholder="Example: Buy 1 SPY 550 Call; Sell 1 SPY 560 Call",
        )

    notes = st.text_area("Notes")
    submitted = st.form_submit_button("Save trade", use_container_width=True)

if submitted:
    strategy = custom_strategy.strip() or strategy_choice
    side = "Short" if "Short" in side_choice else "Long"
    direction = 1 if side == "Long" else -1
    contract_multiplier = 100 if instrument_type in {"Option", "Option Spread"} else 1
    pnl = (
        None
        if status == "Open"
        else ((exit_price - entry_price) * quantity * contract_multiplier * direction)
        - fees
    )
    details = [f"Instrument: {instrument_type}"]
    if expiration:
        details.append(f"Expiration: {expiration}")
    if spread_legs.strip():
        details.append(f"Legs: {spread_legs.strip()}")
    if notes.strip():
        details.append(notes.strip())
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
            "fees": fees,
            "status": status,
            "strategy": strategy,
            "notes": "\n".join(details),
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
