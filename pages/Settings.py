import streamlit as st

from modules.auth import get_current_user, sign_in_form, sign_out_button
from modules.data import add_watchlist_symbol, get_user_settings, get_watchlist, save_user_settings
from modules.supabase_client import has_supabase_config
from modules.ui import configure_page, page_header


configure_page("Settings")
page_header("Settings", "Account, data connections, and watchlist preferences.")

user = get_current_user()

st.subheader("User")
if user:
    st.success(f"Signed in as {user.get('email')}")
    sign_out_button()
else:
    sign_in_form()

st.subheader("Supabase")
if has_supabase_config():
    st.success("Supabase secrets detected.")
else:
    st.warning("Supabase secrets are not configured. Demo session storage is browser-session only.")

st.subheader("Trading Preferences")
settings = get_user_settings(user_id=user.get("id") if user else None)
with st.form("settings_form"):
    display_name = st.text_input("Display name", value=settings.get("display_name") or "")
    default_account_size = st.number_input(
        "Default account size",
        min_value=0.0,
        value=float(settings.get("default_account_size") or 0.0),
        step=500.0,
    )
    default_risk_pct = st.number_input(
        "Default risk per trade (%)",
        min_value=0.0,
        max_value=100.0,
        value=float(settings.get("default_risk_pct") or 1.0),
        step=0.1,
    )
    timezone = st.text_input("Timezone", value=settings.get("timezone") or "America/New_York")
    settings_submitted = st.form_submit_button("Save settings")

if settings_submitted:
    save_user_settings(
        {
            "display_name": display_name,
            "default_account_size": default_account_size,
            "default_risk_pct": default_risk_pct,
            "timezone": timezone,
        },
        user_id=user.get("id") if user else None,
    )
    st.success("Settings saved.")

st.subheader("Watchlist")
with st.form("watchlist_form"):
    symbol = st.text_input("Symbol")
    notes = st.text_input("Notes")
    submitted = st.form_submit_button("Add symbol")

if submitted and symbol:
    add_watchlist_symbol(symbol, notes, user_id=user.get("id") if user else None)
    st.success(f"Added {symbol.upper()}.")

st.dataframe(get_watchlist(user_id=user.get("id") if user else None), use_container_width=True, hide_index=True)
