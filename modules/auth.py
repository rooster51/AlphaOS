from __future__ import annotations

import streamlit as st

from modules.supabase_client import get_supabase, has_supabase_config


def get_current_user() -> dict | None:
    return st.session_state.get("user")


def sign_in_form() -> None:
    if not has_supabase_config():
        st.caption("Auth disabled until Supabase secrets are configured.")
        if st.button("Use demo session", use_container_width=True):
            st.session_state["user"] = {
                "id": "demo-user",
                "email": "demo@alphaos.local",
            }
            st.rerun()
        return

    with st.form("sign_in"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", use_container_width=True)

    if submitted:
        supabase = get_supabase()
        try:
            response = supabase.auth.sign_in_with_password(
                {"email": email, "password": password}
            )
            st.session_state["user"] = {
                "id": response.user.id,
                "email": response.user.email,
                "access_token": response.session.access_token,
            }
            st.rerun()
        except Exception as exc:
            st.error(f"Sign in failed: {exc}")


def sign_out_button() -> None:
    if st.button("Sign out", use_container_width=True):
        supabase = get_supabase()
        if supabase:
            try:
                supabase.auth.sign_out()
            except Exception:
                pass
        st.session_state.pop("user", None)
        st.rerun()
