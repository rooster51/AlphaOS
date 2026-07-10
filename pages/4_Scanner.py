import streamlit as st

from modules.market_data import scanner_results
from modules.ui import configure_page, empty_state, page_header


configure_page("Scanner")
page_header("Scanner", "Research setups calculated from Public live and historical data.")

if st.button("Run Scanner", type="primary", use_container_width=True):
    with st.spinner("Scanning symbols..."):
        st.session_state["scanner_results_view"] = scanner_results()

results, source = st.session_state.get(
    "scanner_results_view",
    (None, "Not loaded"),
)
st.caption(f"Data source: {source}")

if results is None:
    empty_state("Scanner is ready.", "Click Run Scanner to load live setups.")
    st.stop()

if results.empty:
    empty_state(
        "Live scanner data is unavailable.",
        "Check the Public API key and marketdata scope in Settings.",
    )
    st.stop()

min_score = st.slider("Minimum score", 0, 100, 65, 5)
risk = st.multiselect("Risk", sorted(results["Risk"].unique()), default=sorted(results["Risk"].unique()))

filtered = results[(results["Score"] >= min_score) & (results["Risk"].isin(risk))]
st.dataframe(filtered, use_container_width=True, hide_index=True)

st.caption("Scores combine trend, breakout, volume, and 14-day ATR inputs. Research only, not a trade recommendation.")
