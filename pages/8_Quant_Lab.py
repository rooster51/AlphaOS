import pandas as pd
import streamlit as st

from modules.alpaca_data import get_alpaca_intraday_bars, has_alpaca_config
from modules.pulse_backtest import PULSE_SYMBOLS, compare_pulse_strategies
from modules.ui import configure_page, empty_state, page_header


configure_page("Quant Lab")
page_header(
    "Quant Lab",
    "Pulse Bar backtesting for SPX, SPY, QQQ, and XSP.",
)

st.info(
    "Pulse Bar testing requires completed 30-minute OHLC bars. AlphaOS will not treat daily quote history as a valid Pulse backtest."
)

symbols = st.multiselect(
    "Symbols",
    list(PULSE_SYMBOLS),
    default=list(PULSE_SYMBOLS),
)
data_source = st.radio(
    "Historical data source",
    ["Alpaca 30-minute bars", "CSV upload"],
    horizontal=True,
)
threshold = st.select_slider(
    "Pulse close-location threshold",
    options=[0.80, 0.85, 0.90, 0.95],
    value=0.90,
)
lookback_days = st.slider(
    "Intraday lookback days represented in CSV",
    min_value=1,
    max_value=365,
    value=30,
)
uploaded = st.file_uploader(
    "Optional 30-minute OHLC CSV",
    type=["csv"],
    help="Expected columns: symbol, timestamp, open, high, low, close. Volume is optional.",
)
alpaca_feed = st.selectbox(
    "Alpaca feed",
    ["iex", "sip"],
    help="Free Alpaca accounts can use IEX. SIP historical data may require the end time to be at least 15 minutes old or a paid plan.",
)
use_spy_proxy = st.checkbox(
    "Use SPY as proxy for SPX/XSP",
    value=True,
    help="Alpaca stock bars are best for ETFs. This lets SPX and XSP research use SPY bars when index bars are unavailable.",
)


def uploaded_data_by_symbol(file) -> dict[str, pd.DataFrame]:
    frame = pd.read_csv(file)
    if "symbol" not in frame.columns:
        if len(symbols) == 1:
            frame["symbol"] = symbols[0]
        else:
            raise ValueError("CSV must include a symbol column when multiple symbols are selected.")
    return {
        symbol: group.drop(columns=["symbol"]).copy()
        for symbol, group in frame.groupby(frame["symbol"].astype(str).str.upper())
    }


run = st.button("Run Pulse Backtest", type="primary", use_container_width=True)

if run:
    try:
        if data_source == "CSV upload":
            if uploaded is None:
                st.error("Upload a 30-minute OHLC CSV before running the Pulse backtest.")
                st.stop()
            data_by_symbol = uploaded_data_by_symbol(uploaded)
            source = f"uploaded 30-minute CSV, expected lookback around {lookback_days} days"
        else:
            if not has_alpaca_config():
                st.error("Add ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY in Streamlit secrets before using Alpaca bars.")
                st.stop()
            data_by_symbol = {}
            labels = []
            for symbol in symbols:
                bars, label = get_alpaca_intraday_bars(
                    symbol,
                    lookback_days=int(lookback_days),
                    timeframe="30Min",
                    feed=alpaca_feed,
                    use_spy_proxy=use_spy_proxy,
                )
                data_by_symbol[symbol] = bars
                labels.append(label)
            source = f"Alpaca {alpaca_feed} 30-minute bars: {', '.join(labels)}"
        if not data_by_symbol:
            st.error("Upload a 30-minute OHLC CSV before running the Pulse backtest.")
            st.stop()

        summary, diagnostics = compare_pulse_strategies(
            data_by_symbol,
            symbols=tuple(symbols),
            threshold=float(threshold),
        )
    except Exception as exc:
        st.error(f"Backtest failed: {exc}")
        st.stop()

    st.caption(f"Data source: {source}")
    if summary.empty:
        empty_state("No backtest rows were produced.")
    else:
        st.dataframe(summary, use_container_width=True, hide_index=True)

    unavailable = summary[summary["Status"] == "DATA_UNAVAILABLE"] if "Status" in summary else pd.DataFrame()
    if not unavailable.empty:
        st.warning(
            "One or more symbols could not be tested because valid 30-minute OHLC history was unavailable."
        )

    for key, result in diagnostics.items():
        with st.expander(key, expanded=False):
            st.write(result["reason"])
            trades = result.get("trades", pd.DataFrame())
            setups = result.get("setups", pd.DataFrame())
            if not setups.empty:
                st.markdown("#### Pulse Setups")
                st.dataframe(setups.tail(100), use_container_width=True, hide_index=True)
            if not trades.empty:
                st.markdown("#### Trades")
                st.dataframe(trades.tail(100), use_container_width=True, hide_index=True)

st.caption(
    "Original Pulse uses the raw 30-minute Pulse Bar breakout. Enhanced Pulse adds 9/21 EMA alignment. Public.com remains the options-chain source; Alpaca or CSV supplies historical bars. Results are research only and exclude option pricing, slippage, commissions, taxes, assignment, and execution quality."
)
