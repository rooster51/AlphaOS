"""Streamlit view for Phase 5 distribution-conditioned option economics."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.historical_analogs import analog_research
from modules.market_outcomes import forward_outcomes
from modules.market_state import market_state_features
from modules.option_scenario_ev import scenario_economics
from modules.options_payoff import validate_trade
from modules.public_data import get_public_research_bars


def _fmt_money(value):
    return "Unavailable" if value is None or not np.isfinite(value) else f"${value:,.2f}"


def _fmt_pct(value):
    return "Unavailable" if value is None or not np.isfinite(value) else f"{value:.1%}"


def render_option_economics():
    st.subheader("Option Economics")
    st.caption("Apply today's exact expiration payoff to underlying returns observed in similar historical market states. This is scenario research, not a historical options backtest or trade recommendation.")
    selected = st.session_state.get("quant_selected_option")
    if not selected:
        st.info("Select an opportunity in Strategy Selector first. Manual-trade integration can be added after the core Phase 5 path is validated.")
        return
    try:
        selected = validate_trade(selected)
    except ValueError as exc:
        st.error(str(exc))
        return
    if selected['symbol'] not in ('SPY','QQQ'):
        st.info("Phase 5 underlying analog research currently supports SPY and QQQ.")
        return
    st.write(f"**{selected['symbol']} · {selected['strategy']} · {selected['expiration']}**")
    st.caption(f"Saved spot ${selected['spot']:,.2f} · saved quote source {selected['source']}. Refresh the selected opportunity before research if the underlying has moved.")
    a,b,c,d=st.columns(4)
    horizon=a.selectbox("Observed-session horizon",[1,2,3,5,10],index=2,key='ev_horizon')
    method=b.selectbox("Analog method",['tolerance','nearest'],key='ev_method')
    units=c.number_input("Strategy units",1,100,1,key='ev_units')
    commission=d.number_input("Extra commission / contract ($)",0.,20.,0.,step=.05,key='ev_commission')
    a,b=st.columns(2)
    slippage=a.number_input("Entry slippage / unit ($)",0.,100.,0.,step=.50,key='ev_slippage')
    terminal=b.number_input("Terminal/exit friction / unit ($)",0.,100.,0.,step=.50,key='ev_terminal')
    if st.button("Run option economics →",type='primary',use_container_width=True,key='run_option_economics'):
        try:
            with st.spinner("Loading completed daily history and building analog payoff scenarios…"):
                bars=get_public_research_bars(selected['symbol'],'TEN_YEARS')
                features=market_state_features(bars,selected['symbol'])
                outcomes=forward_outcomes(features)
                research=analog_research(features,outcomes,method=method,horizon=horizon)
                target_spot=float(research['target']['close'])
                if abs(selected['spot']/target_spot-1)>1e-6:
                    raise ValueError(f"Saved trade spot (${selected['spot']:.2f}) differs from latest completed research close (${target_spot:.2f}). Refresh/research on a synchronized snapshot; AlphaOS will not silently mix them.")
                result=scenario_economics(research,selected,horizon,units,commission,slippage,terminal)
                st.session_state['option_economics_result']=result
        except Exception as exc:
            st.session_state.pop('option_economics_result',None)
            st.error(str(exc))
    result=st.session_state.get('option_economics_result')
    if not result:
        return
    gross,net=result['gross_summary'],result['net_summary']
    st.markdown("#### Distribution-conditioned payoff")
    a,b,c,d=st.columns(4)
    a.metric("Gross expected payoff",_fmt_money(gross['expected_payoff']))
    b.metric("Net expected payoff",_fmt_money(net['expected_payoff']))
    c.metric("Positive-payoff frequency",_fmt_pct(net['positive_frequency']))
    d.metric("Net EV / max risk",_fmt_pct(net['expected_payoff_on_max_risk']))
    a,b,c,d=st.columns(4)
    a.metric("Analog N",net['n'])
    b.metric("Median payoff",_fmt_money(net['median_payoff']))
    c.metric("10th percentile",_fmt_money(net['p10_payoff']))
    d.metric("Worst scenario",_fmt_money(net['worst_payoff']))
    st.caption("Positive-payoff frequency is an observed analog scenario frequency, not provider/model POP or a calibrated probability of profit.")
    obs=result['observations']
    if not obs.empty:
        fig=go.Figure(go.Histogram(x=obs.net_expiration_pnl,nbinsx=min(40,max(10,len(obs)//4))))
        fig.add_vline(x=0,line_dash='dash')
        fig.update_layout(title='Scenario expiration P&L distribution',template='plotly_dark',height=360,
                          xaxis_title='Net expiration P&L ($)',yaxis_title='Analog observations')
        st.plotly_chart(fig,use_container_width=True)
    st.markdown("#### Robustness")
    non=result['non_overlapping_net_summary']
    st.dataframe(pd.DataFrame([
        dict(sample='Full analog sample',N=net['n'],expected_payoff=net['expected_payoff'],median=net['median_payoff'],positive_frequency=net['positive_frequency'],p10=net['p10_payoff'],ev_on_max_risk=net['expected_payoff_on_max_risk']),
        dict(sample='Non-overlapping diagnostic',N=non['n'],expected_payoff=non['expected_payoff'],median=non['median_payoff'],positive_frequency=non['positive_frequency'],p10=non['p10_payoff'],ev_on_max_risk=non['expected_payoff_on_max_risk'])
    ]),hide_index=True,use_container_width=True)
    st.caption("The non-overlapping subset is a robustness diagnostic; it does not make observations fully independent.")
    with st.expander("Inspect scenario observations"):
        st.dataframe(obs,hide_index=True,use_container_width=True)
        st.download_button("Export scenario observations",obs.to_csv(index=False),'option-scenario-economics.csv','text/csv')
