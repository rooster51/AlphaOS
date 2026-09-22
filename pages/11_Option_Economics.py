import streamlit as st

from modules.ui import configure_page
from modules.option_economics_workspace import render_option_economics

configure_page("AlphaOS | Option Economics")
st.caption("ALPHAOS / QUANTITATIVE RESEARCH / PHASE 5")
st.title("Option Economics")
st.write("Test a saved SPY or QQQ option structure against the terminal-return distribution of historically similar market states.")
render_option_economics()
