import streamlit as st
from modules.ui import configure_page
from modules.active_trades_workspace import render_active_trades

configure_page('AlphaOS | Active Trades')
st.caption('ALPHAOS / LOCAL POSITION TRACKING')
st.title('Active Trades')
render_active_trades()
