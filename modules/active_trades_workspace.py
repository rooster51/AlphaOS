"""Shared API-backed tracking UI; credentials stay on the Streamlit server."""
from datetime import datetime, timezone
from uuid import uuid4
import os
from urllib.parse import urlsplit
import httpx
import streamlit as st


def render_active_trades():
    st.write('Record your entered PCS or CCS, compare current quotes with frozen entry evidence, and explicitly record closure. No orders are submitted.')
    def setting(name,default=''):
        try:
            return os.environ.get(name) or st.secrets.get(name,default)
        except Exception:
            return os.environ.get(name,default)
    base=setting('ALPHAOS_PUBLIC_URL','https://alphaos.onrender.com').rstrip('/')
    credential=setting('ALPHAOS_API_TOKEN')
    if not credential:
        st.info('Configure ALPHAOS_API_TOKEN in server secrets to connect local tracking to the AlphaOS API.')
        return
    if urlsplit(base).scheme!='https':
        st.error('The tracking API requires an HTTPS server URL.')
        return
    def api(path,body=None):
        try:
            r=httpx.request('POST' if body is not None else 'GET',base+'/v1/positions'+path,
                json=body,headers={'Authorization':'Bearer '+credential},timeout=120)
            if r.status_code>=400:
                st.error(f'Tracking request failed ({r.status_code}). Check inputs and API availability.')
                return None
            return r.json()
        except (httpx.HTTPError,ValueError):
            st.error('Tracking API is unavailable. Your existing records have not been removed.')
            return None
    with st.expander('Record an entered spread'):
        with st.form('record_active_position'):
            symbol=st.selectbox('Symbol',['SPY','QQQ','SPX','XSP'])
            strategy=st.selectbox('Strategy',['PCS','CCS'])
            expiry=st.date_input('Expiration')
            short=st.number_input('Short strike',min_value=.01,value=100.,step=1.)
            long=st.number_input('Long strike',min_value=.01,value=99.,step=1.)
            quantity=st.number_input('Quantity',min_value=1,max_value=10000,value=1,step=1)
            credit=st.number_input('Actual entry credit per share',min_value=.001,value=.20,step=.01,format='%.3f')
            timestamp=st.text_input('Entry timestamp (ISO 8601 with timezone)',value=datetime.now(timezone.utc).isoformat(timespec='seconds'))
            note=st.text_area('Optional note',max_chars=2000)
            confirmed=st.checkbox('I am recording a position I entered.')
            submit=st.form_submit_button('Record entry')
        if submit:
            if not confirmed:
                st.info('Confirm your declared entry before recording it.')
            else:
                payload=dict(symbol=symbol,strategy=strategy,expiration=str(expiry),short_strike=short,
                    long_strike=long,quantity=int(quantity),entry_credit=credit,entry_timestamp=timestamp,note=note)
                previous=st.session_state.get('position_request_payload')
                if previous!=payload:
                    st.session_state['position_request_id']=str(uuid4())
                    st.session_state['position_request_payload']=payload
                request_id=st.session_state.setdefault('position_request_id',str(uuid4()))
                result=api('',dict(request_id=request_id,**payload))
                if result:
                    st.session_state.pop('position_request_id',None)
                    st.success('Entry recorded. Evidence was captured now; it is not a historical execution quote.')
    listing=api('')
    if listing is None:
        return
    positions=listing['positions']
    if not positions:
        st.info('No active positions recorded.')
    else:
        labels={p['position_id']:f"{p['symbol']} {p['strategy']} {p['short_strike']:g}/{p['long_strike']:g} · {p['expiration']} · {p['quantity']} contracts · {p['position_id'][:8]}" for p in positions}
        selected=st.selectbox('Position',list(labels),format_func=labels.get)
        if st.button('Refresh current evidence',type='primary'):
            result=api('/'+selected+'/monitor')
            if result:
                st.session_state['position_monitor_'+selected]=result
        result=st.session_state.get('position_monitor_'+selected)
        if result:
            p=result['position'];current=result['current_snapshot']
            st.subheader(labels[selected])
            def display(value):
                return 'Unavailable' if value is None else f'{value:,.2f}'
            for row in ([('Entry credit',p['entry_credit']),('Estimated close debit',current['estimated_close_debit']),('Estimated P/L',current['estimated_pl'])],
                        [('% max profit captured',current['percent_max_profit_captured']),('Underlying',(current.get('underlying') or {}).get('quote',{}).get('last')),('Short distance',(current['distances'] or {}).get('short_strike'))]):
                for column,(label,value) in zip(st.columns(3),row):
                    column.metric(label,display(value))
            st.write('Breakeven distance:',display((current['distances'] or {}).get('breakeven')))
            st.write('State:',result['monitoring_state']['state'] or 'Assessment unavailable')
            st.caption('Observed '+current['captured_at']+' · Quote estimates, not fills; fees excluded. Distances are signed points. Negative means beyond the boundary.')
            with st.expander('Since Entry',expanded=True):
                st.json(result['entry_vs_current'])
                st.json(result['monitoring_state'])
            with st.expander('Entry Evidence — frozen'):
                st.json(p['entry_snapshot'])
            with st.expander('Current Context'):
                st.json(current)
            with st.expander('Data Quality and methodology'):
                st.write(current['pricing_method'])
                st.json(dict(underlying=(current.get('underlying') or {}).get('freshness'),
                    consumed_contracts=current.get('consumed_contract_quality'),limitations=current['errors']))
        with st.expander('Record closure'):
            with st.form('close_'+selected):
                amount=st.number_input('Actual close amount per share',min_value=0.,value=.05,step=.01)
                flow=st.selectbox('Close cashflow',['debit','credit'])
                closed_at=st.text_input('Close timestamp with timezone',value=datetime.now(timezone.utc).isoformat(timespec='seconds'))
                confirmed=st.checkbox('I confirm this position was closed.')
                close_submit=st.form_submit_button('Record closure')
            if close_submit and confirmed:
                if api('/'+selected+'/close',dict(amount=amount,cashflow=flow,timestamp=closed_at)):
                    st.session_state.pop('position_monitor_'+selected,None)
                    st.rerun()
    with st.expander('Retrieve an active or closed record'):
        lookup=st.text_input('Position ID')
        if st.button('Retrieve record') and lookup:
            try:
                from uuid import UUID
                key=str(UUID(lookup))
            except ValueError:
                st.error('Enter a valid position ID.')
            else:
                result=api('/'+key)
                if result:
                    st.json(result)
