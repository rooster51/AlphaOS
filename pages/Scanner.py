import streamlit as st

from modules.mock_market import get_scanner_results
from modules.ui import configure_page, page_header


configure_page("Scanner")
page_header("Scanner", "Mock setup scanner with scoring placeholders.")

results = get_scanner_results()

min_score = st.slider("Minimum score", 0, 100, 65, 5)
risk = st.multiselect("Risk", sorted(results["Risk"].unique()), default=sorted(results["Risk"].unique()))

filtered = results[(results["Score"] >= min_score) & (results["Risk"].isin(risk))]
st.dataframe(filtered, use_container_width=True, hide_index=True)

st.caption("Scores are placeholders until market data and strategy models are connected.")

