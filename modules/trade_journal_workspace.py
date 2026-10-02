"""Trader-readable journal UI over the shared authenticated API."""
import streamlit as st


def journal_table(trades):
    return [dict(Date=t['closed_timestamp'],Symbol=t['symbol'],Strategy=t['strategy'],DTE=t['entry_dte'],
        Strikes=f"{t['short_strike']:g}/{t['long_strike']:g}",Quantity=t['quantity'],
        **{'Entry credit':t['entry_credit'],'Exit amount':t['exit_amount'],'Exit basis':t['exit_basis'],
            'Actual P/L':t['realized_pl'],'Estimated exit P/L':t['estimated_exit_pl'],
            'Hold minutes':t['hold_seconds']/60 if t['hold_seconds'] is not None else None,
            'Exit reason':t['exit_reason'] or 'Not recorded'}) for t in trades]


def timeline_table(events):
    rows=[]
    for e in events:
        if e['kind']!='monitor':continue
        c=e['payload']['current_snapshot'];s=e['payload']['monitoring_state']
        rows.append(dict(Timestamp=e['observed_at'],Underlying=(c.get('underlying') or {}).get('quote',{}).get('last'),
            **{'Natural close estimate':c.get('estimated_close_debit'),'Estimated P/L':c.get('estimated_pl'),
                'Short delta':c.get('short_delta'),'State':s.get('state'),
                'Quality limitations':', '.join(c.get('errors',[])) or 'None reported'}))
    return rows


def render_trade_journal(fetch):
    st.subheader('Trade Journal')
    st.caption('User-recorded closed trades. Actual declared fills and estimates stay separate. Fees excluded.')
    a,b,c=st.columns(3)
    symbol=a.selectbox('Journal symbol',['All','SPY','QQQ','SPX','XSP'])
    strategy=b.selectbox('Journal strategy',['All','PCS','CCS'])
    dte=c.selectbox('Entry DTE',['All','0DTE','1DTE+'])
    params={}
    if symbol!='All':params['symbol']=symbol
    if strategy!='All':params['strategy']=strategy
    if dte=='0DTE':params.update(dte_min=0,dte_max=0)
    if dte=='1DTE+':params['dte_min']=1
    with st.expander('More filters'):
        if st.checkbox('Filter by date range'):
            start=st.date_input('From date');end=st.date_input('Through date')
            params.update(date_from=str(start),date_to=str(end),date_basis=st.selectbox('Date basis',['close','entry']))
        reason=st.selectbox('Filter exit reason',['All','profit_target','risk_management','short_strike_pressure','breakeven_pressure','thesis_changed','expiration','manual_discretionary','other'])
        if reason!='All':params['exit_reason']=reason
        regime=st.text_input('Captured entry regime (blank for all)')
        if regime:params['entry_regime']=regime
        structure=st.text_input('Captured completed-session EMA structure (blank for all)')
        if structure:params['entry_structure']=structure
        state=st.selectbox('Recorded monitoring state',['All','THESIS_INTACT','UNDER_PRESSURE','BOUNDARY_BREACHED'])
        if state!='All':params['monitor_state']=state
        if st.checkbox('Only recorded short-strike breaches'):params['short_breached']='true'
    page=int(st.number_input('Journal page',min_value=1,value=1,step=1))
    journal=fetch('',dict(**params,limit=20,offset=(page-1)*20))
    if journal is None:return
    st.caption(f"Closed trades matching filters: n = {journal['n_closed']}")
    trades=journal['trades']
    if trades:
        selection=st.dataframe(journal_table(trades),hide_index=True,on_select='rerun',selection_mode='single-row',key='closed_trade_table')
        selected=selection.selection.rows
        if selected and selected[0]<len(trades):
            position_id=trades[selected[0]]['position_id']
            event_page=int(st.number_input('Review timeline page',min_value=1,value=1,step=1,key='timeline_'+position_id))
            review=fetch('/'+position_id,dict(event_limit=100,event_offset=(event_page-1)*100))
            if review:
                st.subheader('Trade Review')
                metrics=review['metrics'];entry=review['entry_record']
                st.write(f"{entry['symbol']} {entry['strategy']} · {entry['short_strike']:g}/{entry['long_strike']:g} · {entry['expiration']}")
                st.write('Entry:',entry['entry_timestamp'],'· Credit:',entry['entry_credit'])
                st.write('Outcome basis:',metrics['exit_basis'] or 'Active','· Actual recorded P/L:',metrics['realized_pl'] if metrics['realized_pl'] is not None else 'Unavailable')
                st.caption(f"Stored events: {review['event_count']}. Eligible monitoring observations: {metrics['eligible_monitor_count']}. These are sampled observations, not a continuous path.")
                st.dataframe(timeline_table(review['monitoring_timeline']),hide_index=True)
                with st.expander('Entry research — frozen'):
                    st.json(entry['entry_snapshot'])
                with st.expander('Exit and notes'):
                    st.write('Entry note:',entry.get('note') or 'Not recorded')
                    st.json(review['outcome'])
                with st.expander('Boundary observations, excursions and transitions'):
                    st.json(metrics)
    else:
        st.info('No closed trades on this page. Missing data is not a zero result.')
    st.subheader('Performance')
    group=st.selectbox('Group results by',['All trades','symbol','strategy','dte_bucket','entry_dte','entry_time_bucket','hold_bucket','exit_reason','entry_regime','entry_structure','last_monitor_state','recorded_short_breach'])
    performance=fetch('/performance',dict(**params,**({'group_by':group} if group!='All trades' else {})))
    if performance is None:return
    s=performance['summary']
    st.caption(f"Closed n = {s['n_closed']} · Actual recorded outcomes n = {s['n_realized']} · Without actual result n = {s['n_missing_actual']}")
    if s['small_sample']:st.info('Small recorded sample. These summaries do not establish an edge or predict future results.')
    for column,label,key in zip(st.columns(3),['Cumulative realized P/L','Realized win rate (%)','Realized expectancy per recorded trade'],
            ['cumulative_realized_pl','realized_win_rate','realized_expectancy_per_recorded_trade']):
        m=s[key];column.metric(f"{label} · n={m['n']}",'Unavailable' if m['value'] is None else f"{m['value']:,.2f}")
    if performance['groups']:
        st.dataframe([dict(Group=g['value'] if g['value'] is not None else 'Not captured',
            **{'Closed n':g['summary']['n_closed'],'Actual n':g['summary']['n_realized'],
                'Win rate (%)':g['summary']['realized_win_rate']['value'],
                'Average actual P/L':g['summary']['average_realized_pl']['value'],
                'Small sample':g['summary']['small_sample']}) for g in performance['groups']],hide_index=True)
    with st.expander('Recorded profit giveback'):
        st.json(s['after_recorded_50_percent'])
    with st.expander('Full descriptive metrics and cumulative results'):
        st.json(s)
        st.dataframe(performance['cumulative_realized_series'],hide_index=True)
    with st.expander('Definitions and limitations'):
        for caveat in performance['caveats']:st.write(caveat)
        st.write('Date filters use America/New_York dates. Entry context comes only from frozen captured fields. Realized expectancy is not historical scenario EV. Excursions and breaches only describe recorded observations; unknown history stays unavailable.')
