"""Streamlit view for Phase 5 distribution-conditioned option economics."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.historical_analogs import DEFAULT_TOLERANCES, analog_research, sample_warning
from modules.market_outcomes import forward_outcomes
from modules.market_state import market_state_features
from modules.option_scenario_ev import scenario_economics
from modules.options_payoff import trade_analysis, validate_trade
from modules.research_session import get_research_session, summarize_research_session


def _fmt_money(value):
    return "Unavailable" if value is None or not np.isfinite(value) else f"${value:,.2f}"


def _fmt_pct(value):
    return "Unavailable" if value is None or not np.isfinite(value) else f"{value:.1%}"


def _vertical_context(trade, analysis):
    legs=trade['legs']
    if trade['shares'] or len(legs)!=2 or legs[0]['type']!=legs[1]['type'] or legs[0]['qty']!=-legs[1]['qty']:
        return None
    short=[leg for leg in legs if leg['qty']<0]
    long=[leg for leg in legs if leg['qty']>0]
    if len(short)!=1 or len(long)!=1:
        return None
    short_strike=float(short[0]['strike']); long_strike=float(long[0]['strike'])
    breakeven=analysis['breakevens'][0] if len(analysis['breakevens'])==1 else None
    return dict(short_strike=short_strike,long_strike=long_strike,
                short_distance=short_strike/trade['spot']-1,
                breakeven=breakeven,width=analysis['width'])


def _row(label, result):
    s=result['net_summary']
    return dict(sample=label,N=s['n'],expected_payoff=s['expected_payoff'],median=s['median_payoff'],
                positive_frequency=s['positive_frequency'],p10=s['p10_payoff'],
                ev_on_max_risk=s['expected_payoff_on_max_risk'])


def render_option_economics():
    st.subheader("Option Economics")
    st.caption("Select analogs from the latest completed market state, then apply their forward returns to the current trade spot and today's exact expiration payoff. This is scenario research, not a historical options backtest or trade recommendation.")
    selected=st.session_state.get("quant_selected_option")
    if not selected:
        st.info("Select an opportunity in Strategy Selector first.")
        return
    try:
        selected=validate_trade(selected)
    except ValueError as exc:
        st.error(str(exc)); return
    if selected['symbol'] not in ('SPY','QQQ'):
        st.info("Phase 5 underlying analog research currently supports SPY and QQQ."); return
    active=get_research_session(st.session_state)
    if active is None:
        st.warning("No active Quant Lab research dataset. Open Market State Research, generate SPY or QQQ history, then return here."); return
    summary=summarize_research_session(st.session_state)
    if summary.symbol!=selected['symbol']:
        st.warning(f"Active research dataset is {summary.symbol}, but the selected option is {selected['symbol']}. Generate {selected['symbol']} in Market State Research first."); return

    research_close=float(active['history']['close'].iloc[-1]); spot_gap=float(selected['spot'])/research_close-1
    st.success(f"Active Research Dataset: {summary.symbol} · {summary.period} · through {summary.last_date} · {summary.observations:,} sessions")
    a,b,c=st.columns(3)
    a.metric("Research anchor · completed close",f"${research_close:,.2f}")
    b.metric("Trade anchor · current spot",f"${selected['spot']:,.2f}")
    c.metric("Move since research close",f"{spot_gap:+.2%}")
    st.caption("The research close is NOT the option threshold. It defines the completed market state used to find historical analogs. The option threshold is the short strike shown below.")

    analysis=trade_analysis(selected,1); vertical=_vertical_context(selected,analysis)
    st.markdown("#### Trade economics & option threshold")
    st.write(f"**{selected['symbol']} · {selected['strategy']} · {selected['expiration']}**")
    if vertical:
        a,b,c,d=st.columns(4)
        a.metric("Short-strike threshold",f"${vertical['short_strike']:,.2f}")
        b.metric("Long strike",f"${vertical['long_strike']:,.2f}")
        c.metric("Short strike vs current spot",f"{vertical['short_distance']:+.2%}")
        d.metric("Breakeven",_fmt_money(vertical['breakeven']))
    a,b,c,d=st.columns(4)
    a.metric("Net option premium",_fmt_money(analysis['net_cash']))
    b.metric("Max profit",_fmt_money(analysis['max_profit']))
    c.metric("Max loss",_fmt_money(analysis['max_loss']))
    d.metric("Return on max risk",_fmt_pct(analysis['return_on_risk']))
    st.caption(f"Saved quote source {selected['source']}. Refresh the selected opportunity if its option quote or underlying spot is stale.")

    a,b,c,d=st.columns(4)
    horizon=a.selectbox("Observed-session horizon",[1,2,3,5,10],index=2,key='ev_horizon')
    method=b.selectbox("Primary analog method",['tolerance','nearest'],key='ev_method')
    units=c.number_input("Strategy units",1,100,1,key='ev_units')
    commission=d.number_input("Extra commission / contract ($)",0.,20.,0.,step=.05,key='ev_commission')
    a,b=st.columns(2)
    slippage=a.number_input("Entry slippage / unit ($)",0.,100.,0.,step=.50,key='ev_slippage')
    terminal=b.number_input("Terminal/exit friction / unit ($)",0.,100.,0.,step=.50,key='ev_terminal')

    if st.button("Run option economics →",type='primary',use_container_width=True,key='run_option_economics'):
        try:
            with st.spinner("Building primary and robustness analog payoff scenarios…"):
                bars=active['history'].copy(deep=True); completed_before=pd.Timestamp(summary.last_date)+pd.Timedelta(days=1)
                features=market_state_features(bars,completed_before.date()); outcomes=forward_outcomes(bars,completed_before.date())
                primary=analog_research(features,outcomes,method=method,horizon=horizon)
                result=scenario_economics(primary,selected,horizon,units,commission,slippage,terminal)
                robustness=[]
                for name,mult in [('Tight tolerance',.75),('Default tolerance',1.),('Wide tolerance',1.5)]:
                    r=analog_research(features,outcomes,method='tolerance',horizon=horizon,
                        tolerances={k:v*mult for k,v in DEFAULT_TOLERANCES.items()})
                    robustness.append((name,scenario_economics(r,selected,horizon,units,commission,slippage,terminal)))
                nearest=analog_research(features,outcomes,method='nearest',horizon=horizon,neighbors=50)
                robustness.append(('Nearest 50',scenario_economics(nearest,selected,horizon,units,commission,slippage,terminal)))
                st.session_state['option_economics_result']=result
                st.session_state['option_economics_robustness']=robustness
        except Exception as exc:
            st.session_state.pop('option_economics_result',None); st.session_state.pop('option_economics_robustness',None); st.error(str(exc))

    result=st.session_state.get('option_economics_result')
    if not result: return
    gross,net=result['gross_summary'],result['net_summary']
    warning=sample_warning(net['n'])
    if net['n']<30: st.warning(f"Analog N = {net['n']}. {warning} Compare the robustness samples below before interpreting the payoff distribution.")
    elif net['n']<100: st.info(f"Analog N = {net['n']}. {warning}")

    st.markdown("#### Distribution-conditioned payoff")
    a,b,c,d=st.columns(4)
    a.metric("Gross expected payoff",_fmt_money(gross['expected_payoff']))
    b.metric("Net expected payoff",_fmt_money(net['expected_payoff']))
    c.metric("Positive-payoff frequency",_fmt_pct(net['positive_frequency']))
    d.metric("Net EV / max risk",_fmt_pct(net['expected_payoff_on_max_risk']))
    a,b,c,d=st.columns(4)
    a.metric("Analog N",net['n']); b.metric("Median payoff",_fmt_money(net['median_payoff']))
    c.metric("10th percentile",_fmt_money(net['p10_payoff'])); d.metric("Worst scenario",_fmt_money(net['worst_payoff']))
    st.caption("Positive-payoff frequency is an observed analog scenario frequency, not provider/model POP or a calibrated probability of profit.")
    obs=result['observations']
    if not obs.empty:
        fig=go.Figure(go.Histogram(x=obs.net_expiration_pnl,nbinsx=min(40,max(10,len(obs)//4))))
        fig.add_vline(x=0,line_dash='dash'); fig.update_layout(title='Scenario expiration P&L distribution',template='plotly_dark',height=360,xaxis_title='Net expiration P&L ($)',yaxis_title='Analog observations')
        st.plotly_chart(fig,use_container_width=True)

    st.markdown("#### Robustness across reasonable analog definitions")
    rows=[_row(label,r) for label,r in st.session_state.get('option_economics_robustness',[])]
    non=result['non_overlapping_net_summary']
    rows.append(dict(sample=f"Primary {method} · non-overlapping",N=non['n'],expected_payoff=non['expected_payoff'],median=non['median_payoff'],positive_frequency=non['positive_frequency'],p10=non['p10_payoff'],ev_on_max_risk=non['expected_payoff_on_max_risk']))
    robust=pd.DataFrame(rows)
    st.dataframe(robust,column_config={
        'expected_payoff':st.column_config.NumberColumn('Expected payoff',format='$%.2f'),
        'median':st.column_config.NumberColumn('Median',format='$%.2f'),
        'positive_frequency':st.column_config.NumberColumn('Positive payoff',format='percent'),
        'p10':st.column_config.NumberColumn('P10 payoff',format='$%.2f'),
        'ev_on_max_risk':st.column_config.NumberColumn('EV / max risk',format='percent')},hide_index=True,use_container_width=True)
    st.caption("Do not select the most favorable row. The purpose is to see whether the economics remain similar when the definition of 'similar market state' changes. The non-overlapping subset is a dependence diagnostic, not proof of independence.")
    with st.expander("Inspect primary scenario observations"):
        st.dataframe(obs,hide_index=True,use_container_width=True)
        st.download_button("Export scenario observations",obs.to_csv(index=False),'option-scenario-economics.csv','text/csv')
