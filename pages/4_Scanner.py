import streamlit as st

from modules.market_data import scanner_results
from modules.ui import configure_page, page_header


configure_page("Scanner")
page_header("Scanner", "Setup scanner with live quote context when connected.")

results, source = scanner_results()
st.caption(f"Data source: {source}")

min_score = st.slider("Minimum score", 0, 100, 65, 5)
risk = st.multiselect("Risk", sorted(results["Risk"].unique()), default=sorted(results["Risk"].unique()))

filtered = results[(results["Score"] >= min_score) & (results["Risk"].isin(risk))]
st.dataframe(filtered, use_container_width=True, hide_index=True)

st.caption("Scores remain research placeholders; prices and one-day changes are live when Public is connected.")
