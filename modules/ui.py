from __future__ import annotations

import streamlit as st


def configure_page(title: str) -> None:
    st.set_page_config(
        page_title=title,
        page_icon="A",
        layout="wide",
        initial_sidebar_state="expanded",
    )


def page_header(title: str, subtitle: str | None = None) -> None:
    st.title(title)
    if subtitle:
        st.caption(subtitle)


def render_nav_hint() -> None:
    st.caption("Use the pages menu for Strategy Suggestions, Journal, P&L, Scanner, Quant Lab, and Settings.")


def require_auth_notice() -> None:
    st.warning("Sign in or start a demo session from the sidebar.")


def metric_card(label: str, value: float | int | str, prefix: str = "", suffix: str = "") -> None:
    if isinstance(value, float):
        formatted = f"{value:,.2f}"
    elif isinstance(value, int):
        formatted = f"{value:,}"
    else:
        formatted = str(value)
    st.metric(label, f"{prefix}{formatted}{suffix}")


def empty_state(title: str, body: str = "") -> None:
    st.info(f"{title} {body}".strip())
