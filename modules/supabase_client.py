from __future__ import annotations

import streamlit as st
from supabase import Client, create_client


def has_supabase_config() -> bool:
    return bool(st.secrets.get("SUPABASE_URL") and st.secrets.get("SUPABASE_ANON_KEY"))


def get_supabase() -> Client | None:
    if not has_supabase_config():
        return None
    if "supabase_client" not in st.session_state:
        st.session_state["supabase_client"] = create_client(
            st.secrets["SUPABASE_URL"],
            st.secrets["SUPABASE_ANON_KEY"],
        )
    return st.session_state["supabase_client"]
