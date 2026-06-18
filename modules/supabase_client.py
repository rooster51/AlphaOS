from __future__ import annotations

from functools import lru_cache

import streamlit as st
from supabase import Client, create_client


def has_supabase_config() -> bool:
    return bool(st.secrets.get("SUPABASE_URL") and st.secrets.get("SUPABASE_ANON_KEY"))


@lru_cache(maxsize=1)
def get_supabase() -> Client | None:
    if not has_supabase_config():
        return None
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_ANON_KEY"])
