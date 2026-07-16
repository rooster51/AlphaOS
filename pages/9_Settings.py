import streamlit as st

from modules.auth import get_current_user, sign_in_form, sign_out_button
from modules.data import add_watchlist_symbol, get_user_settings, get_watchlist, save_user_settings
from modules.risk_guardrails import normalize_guardrails
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
guardrails = normalize_guardrails(settings)
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
    st.markdown("#### Discipline Guardrails")
    r1, r2, r3 = st.columns(3)
    max_trades_per_day = r1.number_input(
        "Max trades per day",
        min_value=0,
        value=guardrails["max_trades_per_day"],
        step=1,
    )
    max_daily_loss_pct = r2.number_input(
        "Max daily loss (%)",
        min_value=0.0,
        max_value=100.0,
        value=guardrails["max_daily_loss_pct"],
        step=0.25,
    )
    cooldown_after_losses = r3.number_input(
        "Cooldown after losses",
        min_value=0,
        value=guardrails["cooldown_after_losses"],
        step=1,
    )
    r4, r5, r6 = st.columns(3)
    cooldown_minutes = r4.number_input(
        "Cooldown minutes",
        min_value=0,
        value=guardrails["cooldown_minutes"],
        step=15,
    )
    min_backtest_win_rate = r5.number_input(
        "Minimum backtest win rate (%)",
        min_value=0.0,
        max_value=100.0,
        value=guardrails["min_backtest_win_rate"],
        step=1.0,
    )
    max_reversal_warnings = r6.number_input(
        "Allowed reversal warnings",
        min_value=0,
        value=guardrails["max_reversal_warnings"],
        step=1,
    )
    require_pretrade_checklist = st.checkbox(
        "Require pre-trade checklist before considering a setup clear",
        value=guardrails["require_pretrade_checklist"],
    )
    settings_submitted = st.form_submit_button("Save settings")

if settings_submitted:
    save_user_settings(
        {
            "display_name": display_name,
            "default_account_size": default_account_size,
            "default_risk_pct": default_risk_pct,
            "timezone": timezone,
            "max_trades_per_day": max_trades_per_day,
            "max_daily_loss_pct": max_daily_loss_pct,
            "cooldown_after_losses": cooldown_after_losses,
            "cooldown_minutes": cooldown_minutes,
            "min_backtest_win_rate": min_backtest_win_rate,
            "max_reversal_warnings": max_reversal_warnings,
            "require_pretrade_checklist": require_pretrade_checklist,
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
