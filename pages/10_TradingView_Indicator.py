from pathlib import Path

import streamlit as st

from modules.ui import configure_page, page_header


SCRIPT_PATH = Path("tradingview/alphaos_pulse_confirm.pine")


configure_page("TradingView Indicator")
page_header(
    "TradingView Indicator",
    "Copy the AlphaOS Pulse confirmation script into TradingView Pine Editor.",
)

if not SCRIPT_PATH.exists():
    st.error("TradingView script file is missing from the repository.")
    st.stop()

script = SCRIPT_PATH.read_text(encoding="utf-8")

st.info(
    "Use this on a 30-minute TradingView chart. It marks Pulse Bars, breakout confirmation, VWAP/EMA context, and chop warnings."
)

st.download_button(
    "Download Pine Script",
    data=script,
    file_name="alphaos_pulse_confirm.pine",
    mime="text/plain",
    use_container_width=True,
)

st.code(script, language="pine")

st.subheader("How to Add It")
st.markdown(
    """
1. Open TradingView.
2. Open a 30-minute chart for SPY, QQQ, DIA, IWM, SPX, or XSP.
3. Open Pine Editor.
4. Paste this script.
5. Click Save, then Add to chart.
6. Create alerts from the AlphaOS alert conditions if you want phone/desktop notifications.
"""
)

st.caption(
    "This is a confirmation indicator only. It does not place trades and does not send orders."
)
