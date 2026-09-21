"""Presentation for deterministic options payoff analysis."""
from math import isfinite
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.options_payoff import trade_analysis
from modules.premium_workspace import money


def payoff_figure(analysis):
    frame = pd.DataFrame(analysis['grid'])
    fig = go.Figure(go.Scatter(x=frame['Terminal underlying ($)'], y=frame['Expiration P&L ($)'],
        name='Expiration P&L', mode='lines', line=dict(color='#61d8c1',width=3),
        hovertemplate='Terminal spot: $%{x:.4f}<br>P&L: $%{y:.2f}<extra></extra>'))
    fig.add_hline(y=0,line_color='#a1acbb',line_width=1)
    # Legend groups keep many strikes readable; exact labels are in hover/table.
    for name, points, color, dash in (
        ('Strikes',analysis['strikes'],'#65758b','dot'),
        ('Breakevens',analysis['breakevens'],'#f4bd62','dash'),
        ('Current spot',[analysis['trade']['spot']],'#7da9ff','solid')):
        for p in points:
            fig.add_vline(x=p,line_color=color,line_dash=dash,line_width=1)
        selected = frame[frame['Terminal underlying ($)'].isin(points)]
        fig.add_trace(go.Scatter(x=selected['Terminal underlying ($)'],y=selected['Expiration P&L ($)'],
            name=name,mode='markers',marker=dict(color=color,size=9),
            hovertemplate=name+': $%{x:.4f}<br>P&L: $%{y:.2f}<extra></extra>'))
    for name,value,color in (('Max profit',analysis['max_profit'],'#61d8c1'),
                             ('Max loss',-analysis['max_loss'],'#f08391')):
        if isfinite(value):
            fig.add_hline(y=value,line_dash='dash',line_color=color,
                          annotation_text=f'{name}: {money(abs(value))}',annotation_position='top left')
    fig.update_layout(template='plotly_dark',paper_bgcolor='#0b111c',plot_bgcolor='#0b111c',
        height=460,margin=dict(l=20,r=20,t=35,b=30),legend=dict(orientation='h'),
        xaxis_title='Terminal underlying price ($)',yaxis_title='Expiration P&L ($)')
    return fig


def render_payoff_analysis(selected, units):
    analysis = trade_analysis(selected,units)
    st.markdown('#### Trade economics')
    a,b,c,d = st.columns(4)
    a.metric('Spot price',money(analysis['trade']['spot']))
    cash = analysis['net_cash']
    b.metric('Net credit' if cash >= 0 else 'Net debit',money(abs(cash)))
    c.metric('Maximum expiration profit',money(analysis['max_profit']))
    d.metric('Maximum expiration loss',money(analysis['max_loss']))
    a,b,c = st.columns(3)
    a.metric('Return on max risk',f"{analysis['return_on_risk']:.2%}" if analysis['return_on_risk'] is not None else 'Not meaningful')
    b.metric('Vertical spread width',f"${analysis['width']:g}" if analysis['width'] is not None else 'Not applicable')
    c.metric('Credit / width',f"{analysis['credit_width']:.2%}" if analysis['credit_width'] is not None else 'Not applicable')
    st.write('**Breakevens:** '+(', '.join(f'${p:,.6f}'.rstrip('0').rstrip('.') for p in analysis['breakevens']) or 'None'))
    st.caption(f"All P&L amounts include {units:g} strategy unit(s). Option premium before fees: {money(abs(analysis['option_premium']))} {'credit' if analysis['option_premium'] >= 0 else 'debit'}; entry fees: {money(analysis['fees'])}. Net credit/debit includes entry fees and excludes stock purchase proceeds/cost. Credit / width uses option premium before fees, adjusted for leg quantity; shown only for plain two-leg verticals.")
    st.caption('PAYOFF ANALYSIS: What happens if the underlying expires here? These deterministic scenarios are not probabilities or a historical options backtest. How likely an outcome is, and whether a trade is statistically attractive, require separate research.')
    payoff_tab, extreme_tab = st.tabs(['Payoff map','Extreme stress'])
    with payoff_tab:
        st.plotly_chart(payoff_figure(analysis),use_container_width=True)
        st.caption('Adaptive sampling around spot, strikes and breakevens. Narrow strikes receive finer spacing; broad ranges are capped. Exact landmarks and their interval midpoints are always included. Global payoff bounds may occur outside this local price range.')
        _table(analysis['grid'])
    with extreme_tab:
        st.caption('Large terminal shocks: ±5%, ±10%, ±20%, ±30%, ±50%, plus unchanged spot. These are expiration outcomes, not pre-expiration mark-to-market losses.')
        frame = pd.DataFrame(analysis['extremes'])
        fig = go.Figure(go.Scatter(x=frame['Move from spot (%)'],y=frame['Expiration P&L ($)'],mode='lines+markers',name='Extreme stress'))
        fig.add_hline(y=0,line_color='#a1acbb')
        fig.update_layout(template='plotly_dark',paper_bgcolor='#0b111c',plot_bgcolor='#0b111c',height=330,
                          xaxis_title='Move from current spot (%)',yaxis_title='Expiration P&L ($)')
        st.plotly_chart(fig,use_container_width=True)
        _table(analysis['extremes'])
    if not isfinite(analysis['max_loss']) or not isfinite(analysis['max_profit']):
        st.warning('Unlimited payoff exposure extends beyond these finite grids. Return on maximum risk is unavailable when the denominator is unlimited or zero.')
    st.caption('Standard 100-share contracts, a common expiration, and entered stock basis. Entry fees are included; exit fees, early assignment, dividends, and pre-expiration volatility changes are not modeled.')


def _table(rows):
    st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True,column_config={
        'Terminal underlying ($)':st.column_config.NumberColumn(format='%.6f'),
        'Move from spot (%)':st.column_config.NumberColumn(format='%.4f'),
        'Expiration P&L ($)':st.column_config.NumberColumn(format='%.2f'),
        'Return on max risk (%)':st.column_config.NumberColumn(format='%.2f')})
