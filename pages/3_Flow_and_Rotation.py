import plotly.express as px
import streamlit as st

from modules.market_data import rotation_table
from modules.ui import configure_page, empty_state, page_header


configure_page("Flow & Rotation")
page_header("Flow & Rotation", "Sector ETF leadership calculated from Public historical data.")

rotation, source = rotation_table()
st.caption(f"Data source: {source}")

if rotation.empty:
    empty_state(
        "Live rotation data is unavailable.",
        "Check the Public API key and marketdata scope in Settings.",
    )
    st.stop()

st.dataframe(rotation, use_container_width=True, hide_index=True)

st.plotly_chart(
    px.bar(
        rotation,
        x="Group",
        y="Score",
        color="Phase",
        title="Rotation Score by Group",
    ),
    use_container_width=True,
)
st.caption("Scores rank sector ETF 5-day momentum and 20-day performance relative to SPY.")
