import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from modules.market_data import MARKET_SYMBOLS, price_history
from modules.ui import configure_page, empty_state, page_header


configure_page("Quant Lab")
page_header(
    "Quant Lab",
    "Test transparent research rules against Public historical market data.",
)

c1, c2 = st.columns(2)
symbol = c1.selectbox("Symbol", MARKET_SYMBOLS, index=1)
lookback = c2.slider("Moving average lookback", 5, 50, 20)

history, source = price_history(symbol)
st.caption(f"Data source: {source}")

if history.empty:
    empty_state(
        "Public historical data is unavailable.",
        "Check the Public API key and marketdata scope in Settings.",
    )
    st.stop()

history = history.sort_values("date").copy()
history["close"] = pd.to_numeric(history["close"], errors="coerce")
history = history.dropna(subset=["close"])

if len(history) <= lookback:
    empty_state(
        "Not enough historical bars.",
        "Choose a shorter moving-average lookback.",
    )
    st.stop()

history["daily_return"] = history["close"].pct_change()
history["moving_average"] = history["close"].rolling(lookback).mean()
model = history.dropna(subset=["moving_average"]).copy()
model["signal"] = (model["close"] > model["moving_average"]).astype(float)
model["strategy_return"] = (
    model["signal"].shift(1).fillna(0) * model["daily_return"].fillna(0)
)
model["buy_hold_curve"] = 100 * (1 + model["daily_return"].fillna(0)).cumprod()
model["model_curve"] = 100 * (1 + model["strategy_return"]).cumprod()

period_return = ((model["close"].iloc[-1] / model["close"].iloc[0]) - 1) * 100
model_return = ((model["model_curve"].iloc[-1] / 100) - 1) * 100
annualized_volatility = (
    model["daily_return"].dropna().std() * np.sqrt(252) * 100
)
rolling_peak = model["close"].cummax()
max_drawdown = ((model["close"] / rolling_peak) - 1).min() * 100
latest_signal = "Above moving average" if model["signal"].iloc[-1] else "Below moving average"

metrics = st.columns(5)
metrics[0].metric("Latest Close", f"${model['close'].iloc[-1]:,.2f}")
metrics[1].metric("Rule State", latest_signal)
metrics[2].metric("Period Return", f"{period_return:+.2f}%")
metrics[3].metric("Annualized Volatility", f"{annualized_volatility:.2f}%")
metrics[4].metric("Max Drawdown", f"{max_drawdown:.2f}%")

price_tab, comparison_tab = st.tabs(["Price Rule", "Historical Comparison"])

with price_tab:
    st.plotly_chart(
        px.line(
            model,
            x="date",
            y=["close", "moving_average"],
            title=f"{symbol}: Close vs {lookback}-Day Moving Average",
        ),
        use_container_width=True,
    )

with comparison_tab:
    comparison = model[
        ["date", "buy_hold_curve", "model_curve"]
    ].rename(
        columns={
            "buy_hold_curve": "Buy and Hold",
            "model_curve": "Moving Average Rule",
        }
    )
    st.plotly_chart(
        px.line(
            comparison,
            x="date",
            y=["Buy and Hold", "Moving Average Rule"],
            title="Growth of $100 Over Available History",
        ),
        use_container_width=True,
    )
    st.metric("Moving Average Rule Return", f"{model_return:+.2f}%")

st.caption(
    "The rule uses the prior day's signal to avoid look-ahead bias. Results exclude slippage, taxes, and trading costs and are not a recommendation."
)
