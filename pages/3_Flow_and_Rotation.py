import plotly.express as px
import streamlit as st

from modules.mock_market import get_rotation_table
from modules.ui import configure_page, page_header


configure_page("Flow & Rotation")
page_header("Flow & Rotation", "Sector rotation and flow placeholders ready for real feeds.")

rotation = get_rotation_table()

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
