"""Trade-centered view shared with the MCP/REST unified contract."""
import pandas as pd
import streamlit as st
from modules.unified_trade import build_unified_trade


def render_unified_trade(research):
    # Streamlit uses explicit submitted scenario inputs, not a new provider quote.
    result=build_unified_trade(research)
    t=result['trade_snapshot'];p=result['historical_scenario_payoff']
    st.markdown('#### 1. Trade Snapshot')
    st.write(f"{t['symbol']} · {t['strategy']} · {t['expiration']} · short {t['short_strike']:g} / long {t['long_strike']:g}")
    st.dataframe(pd.DataFrame([{k:t[k] for k in ('width','credit','max_profit','max_loss','return_on_risk','breakeven','scenario_spot')}]),hide_index=True)
    st.caption('Credit is dollars per share; payoff is dollars per structure. Return on risk is a decimal fraction. Scenario spot is an explicit input, not a verified live quote.')
    st.caption(t['instrument']['settlement_caveat'])
    st.write('Instrument',t['instrument'])
    st.write('Live trade state',t['live_trade_state'])
    st.write('Research state',t['research_state'])
    st.markdown('#### 2. Market Structure')
    st.dataframe(pd.DataFrame(result['market_structure']['price_ladder']),hide_index=True)
    st.dataframe(pd.DataFrame([dict(level=k,**v) for k,v in t['distances_from_scenario_spot'].items()]),hide_index=True)
    structure=result['market_structure'];distance=structure['short_minus_nearest_structural_level']
    if distance is not None:
        st.write(f"The short strike is ${abs(distance):.2f} {'above' if distance>=0 else 'below'} the nearest identified {structure['relevant_side']} level (${structure['nearest_relevant_level']:.2f}).")
    st.caption(structure['interpretation'])
    st.markdown('#### 3. Historical Analog Behavior')
    rows=[]
    for level in result['historical_analog_behavior']['levels']:
        s=level['statistics']
        rows.append(dict(Level=level['level'],Price=level['price'],Distance=level['distance']['fraction'],
            Sessions=level['horizon'],Touch=s['touch_frequency'],Finish_beyond=s['terminal_breach_frequency'],
            Recovery_given_touch=s['recovery_frequency_touched'],Terminal_N=s['terminal_valid_n'],Touch_N=s['touch_valid_n'],
            Touch_CI_low=s['touch_wilson_low'],Touch_CI_high=s['touch_wilson_high']))
    st.dataframe(pd.DataFrame(rows),hide_index=True)
    st.caption(result['historical_analog_behavior']['interpretation']+' Frequencies and distances are decimal fractions.')
    st.markdown('#### 4. Historical Scenario Payoff')
    st.warning(p['caveat'])
    st.dataframe(pd.DataFrame([p['summary']]),hide_index=True)
    st.write('Outcome counts',p['outcome_counts'])
    st.caption('Observed-session horizon differs from expiration DTE. Modeled payoffs are not an options backtest or a forecast.')
    return result
