from datetime import date

import streamlit as st

from modules.auth import get_current_user
from modules.data import (
    add_trade,
    delete_trade,
    get_account_snapshot,
    trades_dataframe,
    update_trade,
)
from modules.strategies import strategies_for_instrument, strategy_ideas
from modules.ui import configure_page, empty_state, page_header


HORIZONS = [
    "Day trade (same day)",
    "Swing (2-8 weeks)",
    "Intermediate (2-6 months)",
    "Long term (6+ months)",
]


def _instrument_from_notes(notes: str | None) -> str:
    for line in str(notes or "").splitlines():
        if line.startswith("Instrument: "):
            instrument = line.replace("Instrument: ", "", 1).strip()
            if instrument in {"Stock", "ETF", "Option", "Option Spread"}:
                return instrument
    return "Stock"


def _trade_label(trade: dict) -> str:
    entry = trade.get("entry_date") or "unknown entry"
    try:
        quantity = f"{float(trade.get('quantity') or 0):g}"
    except (TypeError, ValueError):
        quantity = str(trade.get("quantity") or 0)
    strategy = trade.get("strategy") or "Unspecified"
    return f"{trade.get('symbol', '')} | {strategy} | {quantity} | entered {entry}"


def _load_close_trade(trade: dict, session_index: int | None = None) -> None:
    close_draft = dict(trade)
    close_draft["_session_index"] = session_index
    st.session_state["journal_close_draft"] = close_draft
    st.session_state.pop("journal_spread_draft", None)

    for key in list(st.session_state):
        if key.startswith("journal_") and key not in {"journal_close_draft"}:
            del st.session_state[key]

    st.rerun()


def _delete_trade_selection(trade: dict, user_id: str | None) -> None:
    delete_trade(
        trade.get("id"),
        user_id=user_id,
        session_index=trade.get("_session_index"),
    )
    st.session_state.pop("journal_close_draft", None)
    st.session_state.pop("journal_delete_confirm", None)
    st.success("Trade deleted.")
    st.rerun()


configure_page("Trade Journal")
page_header(
    "Trade Journal",
    "Manual stock, option, and multi-leg spread entries.",
)

user = get_current_user()
user_id = user.get("id") if user else None
snapshot = get_account_snapshot(user_id=user_id)
open_trades = [
    {**trade, "_session_index": index}
    for index, trade in enumerate(snapshot.get("trades", []))
    if trade.get("status") == "Open"
]

spread_draft = st.session_state.get("journal_spread_draft")
close_draft = st.session_state.get("journal_close_draft")
draft = spread_draft or close_draft
is_closing_trade = close_draft is not None

if spread_draft:
    st.success(
        f"Loaded {spread_draft['symbol']} {spread_draft['strategy']} from Strategy Selector."
    )
    if st.button("Clear Loaded Spread"):
        st.session_state.pop("journal_spread_draft", None)
        st.rerun()

if close_draft:
    st.success(
        f"Closing {_trade_label(close_draft)}. Enter the exit details and save."
    )
    if st.button("Cancel Close Trade"):
        st.session_state.pop("journal_close_draft", None)
        st.rerun()

with st.expander("Open Journal Trades", expanded=bool(open_trades) and not draft):
    if not open_trades:
        empty_state("No open journal trades.", "Save a trade with status Open first.")
    else:
        for index, trade in enumerate(open_trades):
            row = st.columns([4, 1])
            row[0].write(_trade_label(trade))
            if row[1].button(
                "Close Trade",
                key=f"close_trade_{trade.get('id', index)}",
                use_container_width=True,
            ):
                _load_close_trade(trade, trade.get("_session_index"))

all_trades_for_delete = [
    {**trade, "_session_index": index}
    for index, trade in enumerate(snapshot.get("trades", []))
]
with st.expander("Delete Journal Trades", expanded=False):
    if not all_trades_for_delete:
        empty_state("No saved trades to delete.")
    else:
        delete_labels = [
            f"{index + 1}. {_trade_label(trade)} | {trade.get('status', 'Unknown')}"
            for index, trade in enumerate(all_trades_for_delete)
        ]
        selected_delete_index = st.selectbox(
            "Trade to delete",
            range(len(all_trades_for_delete)),
            format_func=lambda index: delete_labels[index],
            key="journal_delete_trade_index",
        )
        selected_trade = all_trades_for_delete[selected_delete_index]
        st.warning(
            "Deleting a trade permanently removes it from the journal and P&L calculations."
        )
        confirm_delete = st.checkbox(
            f"Confirm delete {_trade_label(selected_trade)}",
            key="journal_delete_confirm",
        )
        if st.button(
            "Delete Selected Trade",
            disabled=not confirm_delete,
            type="primary",
            use_container_width=True,
        ):
            _delete_trade_selection(selected_trade, user_id)

with st.expander("Strategy ideas", expanded=False):
    i1, i2, i3 = st.columns(3)
    idea_outlook = i1.selectbox(
        "Market outlook",
        ["Bullish", "Bearish", "Neutral", "Large move / uncertain direction"],
    )
    idea_volatility = i2.selectbox(
        "Volatility",
        ["Normal", "High", "Low"],
    )
    idea_risk = i3.selectbox(
        "Risk tolerance",
        ["Conservative", "Moderate", "Aggressive"],
    )
    i4, i5 = st.columns(2)
    idea_objective = i4.selectbox(
        "Objective",
        ["Directional", "Income", "Hedging"],
    )
    idea_horizon = i5.selectbox("Time horizon", HORIZONS)
    ideas = strategy_ideas(
        idea_outlook,
        idea_volatility,
        idea_risk,
        idea_objective,
        idea_horizon,
    )
    st.dataframe(ideas, use_container_width=True, hide_index=True)

mode1, mode2 = st.columns(2)
instrument_options = ["Stock", "ETF", "Option", "Option Spread"]
default_instrument = (
    _instrument_from_notes(close_draft.get("notes"))
    if close_draft
    else "Option Spread"
    if spread_draft
    else "Stock"
)
instrument_type = mode1.radio(
    "Instrument",
    instrument_options,
    index=instrument_options.index(default_instrument),
    horizontal=True,
    key="journal_instrument",
)
status = mode2.radio(
    "Status",
    ["Open", "Closed"],
    index=1 if is_closing_trade else 0,
    horizontal=True,
    key="journal_status",
    disabled=is_closing_trade,
)

leg_count = 0
if instrument_type == "Option Spread":
    leg_count = st.number_input(
        "Number of spread legs",
        min_value=2,
        max_value=4,
        value=min(4, max(2, len(draft.get("legs", [])))) if draft else 2,
        step=1,
        key="journal_leg_count",
    )

with st.form("trade_form"):
    c1, c2, c3 = st.columns(3)
    symbol = c1.text_input(
        "Underlying Symbol",
        value=draft.get("symbol", "SPY") if draft else "SPY",
        disabled=is_closing_trade,
        key="journal_symbol",
    ).strip().upper()
    entry_date = c2.date_input(
        "Entry date",
        value=(
            date.fromisoformat(str(close_draft["entry_date"]))
            if close_draft and close_draft.get("entry_date")
            else date.today()
        ),
        disabled=is_closing_trade,
        key="journal_entry_date",
    )
    exit_date = c3.date_input(
        "Exit date",
        value=date.today(),
        disabled=status == "Open",
        key="journal_exit_date",
    )

    strategy_options = strategies_for_instrument(instrument_type) + ["Custom"]
    draft_strategy = draft.get("strategy") if draft else None
    if draft_strategy and draft_strategy not in strategy_options:
        strategy_options.insert(0, draft_strategy)
    strategy_index = (
        strategy_options.index(draft_strategy)
        if draft_strategy in strategy_options
        else 0
    )

    c4, c5, c6 = st.columns(3)
    strategy_choice = c4.selectbox(
        "Strategy",
        strategy_options,
        index=strategy_index,
        disabled=is_closing_trade,
        key="journal_strategy",
    )
    side_options = (
        ["Long / Debit", "Short / Credit"]
        if instrument_type in {"Option", "Option Spread"}
        else ["Long", "Short"]
    )
    draft_side = draft.get("side") if draft else None
    side_index = side_options.index(draft_side) if draft_side in side_options else 0
    side_choice = c5.selectbox(
        "Position Type",
        side_options,
        index=side_index,
        disabled=is_closing_trade,
        key="journal_side",
    )
    quantity_label = (
        "Spread Contracts"
        if instrument_type == "Option Spread"
        else "Contracts"
        if instrument_type == "Option"
        else "Shares"
    )
    quantity = c6.number_input(
        quantity_label,
        min_value=1.0,
        value=float(draft.get("quantity", 1.0)) if draft else 1.0,
        step=1.0,
        disabled=is_closing_trade,
        key="journal_quantity",
    )

    custom_strategy = ""
    if strategy_choice == "Custom":
        custom_strategy = st.text_input(
            "Custom strategy name",
            key="journal_custom_strategy",
        )

    is_option = instrument_type in {"Option", "Option Spread"}
    c7, c8, c9 = st.columns(3)
    entry_price = c7.number_input(
        "Net Entry Premium" if is_option else "Entry Price",
        min_value=0.0,
        value=float(draft.get("entry_price", 1.0)) if draft else 1.0,
        step=0.01,
        disabled=is_closing_trade,
        key="journal_entry_price",
    )
    exit_price = c8.number_input(
        "Net Exit Premium" if is_option else "Exit Price",
        min_value=0.0,
        value=0.0,
        step=0.01,
        disabled=status == "Open",
        key="journal_exit_price",
    )
    fees = c9.number_input(
        "Total Fees",
        min_value=0.0,
        value=0.0,
        step=0.01,
        key="journal_fees",
    )

    expiration = None
    option_type = None
    option_strike = None
    option_contract = ""
    spread_legs = []

    if instrument_type == "Option":
        st.subheader("Option Contract")
        o1, o2, o3, o4 = st.columns(4)
        expiration = o1.date_input(
            "Expiration",
            value=date.today(),
            key="journal_option_expiration",
        )
        option_type = o2.selectbox(
            "Type",
            ["Call", "Put"],
            key="journal_option_type",
        )
        option_strike = o3.number_input(
            "Strike",
            min_value=0.01,
            value=100.0,
            step=0.5,
            key="journal_option_strike",
        )
        option_contract = o4.text_input(
            "Contract Symbol",
            key="journal_option_contract",
        ).strip().upper()

    if instrument_type == "Option Spread":
        st.subheader("Spread Builder")
        draft_expiration = (
            date.fromisoformat(draft["expiration"])
            if draft and draft.get("expiration")
            else date.today()
        )
        expiration = st.date_input(
            "Spread Expiration",
            value=draft_expiration,
            key="journal_spread_expiration",
        )

        labels = st.columns([1, 1, 1, 1, 2])
        for col, label in zip(
            labels,
            ["Action", "Ratio", "Type", "Strike", "Contract Symbol"],
        ):
            col.caption(label)

        draft_legs = draft.get("legs", []) if draft else []
        for index in range(int(leg_count)):
            default = draft_legs[index] if index < len(draft_legs) else {}
            row = st.columns([1, 1, 1, 1, 2])
            action_options = ["Buy", "Sell"]
            action = row[0].selectbox(
                f"Leg {index + 1} action",
                action_options,
                index=(
                    action_options.index(default.get("action"))
                    if default.get("action") in action_options
                    else index % 2
                ),
                label_visibility="collapsed",
                key=f"journal_leg_{index}_action",
            )
            ratio = row[1].number_input(
                f"Leg {index + 1} ratio",
                min_value=1,
                value=int(default.get("quantity", 1)),
                step=1,
                label_visibility="collapsed",
                key=f"journal_leg_{index}_ratio",
            )
            type_options = ["Call", "Put"]
            leg_type = row[2].selectbox(
                f"Leg {index + 1} type",
                type_options,
                index=(
                    type_options.index(default.get("type"))
                    if default.get("type") in type_options
                    else 0
                ),
                label_visibility="collapsed",
                key=f"journal_leg_{index}_type",
            )
            strike = row[3].number_input(
                f"Leg {index + 1} strike",
                min_value=0.01,
                value=float(default.get("strike", 100.0)),
                step=0.5,
                label_visibility="collapsed",
                key=f"journal_leg_{index}_strike",
            )
            contract = row[4].text_input(
                f"Leg {index + 1} contract",
                value=str(default.get("contract", "")),
                label_visibility="collapsed",
                key=f"journal_leg_{index}_contract",
            ).strip().upper()
            spread_legs.append(
                {
                    "action": action,
                    "quantity": ratio,
                    "type": leg_type,
                    "strike": strike,
                    "contract": contract,
                }
            )

    notes = st.text_area(
        "Trade Notes",
        value=draft.get("notes", "") if draft else "",
        key="journal_notes",
    )
    submitted = st.form_submit_button(
        "Close Trade" if is_closing_trade else "Save Trade",
        type="primary",
        use_container_width=True,
    )

if submitted:
    strategy = custom_strategy.strip() or strategy_choice
    side = "Short" if "Short" in side_choice else "Long"
    direction = 1 if side == "Long" else -1
    contract_multiplier = 100 if is_option else 1
    pnl = (
        None
        if status == "Open"
        else ((exit_price - entry_price) * quantity * contract_multiplier * direction)
        - fees
    )

    details = [f"Instrument: {instrument_type}"]
    if expiration:
        details.append(f"Expiration: {expiration}")
    if instrument_type == "Option":
        details.append(f"Contract: {option_type} {option_strike:g} {option_contract}")
    for index, leg in enumerate(spread_legs, start=1):
        details.append(
            f"Leg {index}: {leg['action']} {leg['quantity']} "
            f"{leg['type']} {leg['strike']:g} {leg['contract']}".strip()
        )
    if notes.strip():
        details.append(notes.strip())

    payload = {
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
    }

    try:
        if is_closing_trade:
            update_trade(
                close_draft.get("id"),
                payload,
                user_id=user_id,
                session_index=close_draft.get("_session_index"),
            )
            st.session_state.pop("journal_close_draft", None)
            st.success("Trade closed.")
        else:
            add_trade(payload, user_id=user_id)
            st.session_state.pop("journal_spread_draft", None)
            st.success("Trade saved.")
    except Exception as exc:
        st.error(f"Trade could not be saved: {exc}")

snapshot = get_account_snapshot(user_id=user_id)
df = trades_dataframe(snapshot["trades"])

st.subheader("Trade Log")
if df.empty:
    empty_state("No trades saved yet.")
else:
    st.dataframe(df, use_container_width=True, hide_index=True)
