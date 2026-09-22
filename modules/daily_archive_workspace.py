"""Read-only archive viewer. Files are authoritative; no collection from the UI."""
from pathlib import Path
import streamlit as st
from modules.daily_archive import scan_archive, read_artifact

DATA_ROOT=Path(__file__).resolve().parents[1]/'data'


def render_daily_archive():
    st.subheader('Daily Archive')
    st.caption('Dated underlying research and separate option observations. Historical frequencies are not forecasts or recommendations.')
    inventory=scan_archive(DATA_ROOT)
    if inventory['issues']:
        st.warning('Some archive files are unreadable or inconsistent. They are excluded from this inventory; the manifest is not treated as authoritative.')
    research=inventory['research']
    st.metric('Latest daily research date',research[-1]['date'] if research else 'Not archived yet')
    st.caption(f"{len(research)} research sessions · {len(inventory['options'])} separate option snapshots")
    dates=sorted({r['date'] for kind in ('research','options') for r in inventory[kind]},reverse=True)
    if not dates:
        st.info('No daily snapshots have been archived. Configure the Public GitHub Secrets and enable the daily archive workflow. No synthetic history is shown.')
        return
    session=st.selectbox('Archived session',dates)
    entry=next((r for r in research if r['date']==session),None)
    payload=read_artifact(DATA_ROOT/entry['path']) if entry else None
    if payload:
        st.caption(f"Research collected {payload['generated_at']} · {payload['config_version']} · {payload['status']}")
        for warning in payload['warnings']: st.warning(warning)
    else:
        st.info('No underlying research artifact exists for this date. Available option observations remain separate.')
    for symbol in ('SPY','QQQ'):
        with st.expander(f'{symbol} archived summary',expanded=True):
            item=payload.get('symbols',{}).get(symbol) if payload else None
            if item and item['status']=='complete':
                state=item['market_state'];a,b,c=st.columns(3)
                a.metric(f'{symbol} close',f"${state['close']:,.2f}")
                b.metric(f'{symbol} EMA structure',state['ema_structure'])
                c.metric(f'{symbol} historical analog N',item['historical_analogs']['final_n'])
                st.caption(item['historical_analogs']['sample_warning'])
                st.dataframe(item['historical_analogs']['outcome_summaries'],hide_index=True)
            else: st.info(f'{symbol} research unavailable for this snapshot.')
            option=next((r for r in inventory['options'] if r['date']==session and r['symbol']==symbol),None)
            if option:
                st.caption(f"Separate options archive: {option['status']} · {option['valid_n']} valid · {option['questionable_n']} questionable · {option['rejected_n']} rejected")
                chain=read_artifact(DATA_ROOT/option['path'])
                st.caption(f"Collected {chain['generated_at']} · {chain['quote_timing']}")
                for warning in chain['warnings']: st.warning(warning)
                if chain['rejection_counts']: st.json(chain['rejection_counts'])
            else: st.info(f'{symbol} options snapshot is absent.')
    if payload:
        with st.expander('Open historical research JSON'):
            st.json(payload,expanded=False)
        st.download_button('Download daily research JSON',(DATA_ROOT/entry['path']).read_bytes(),f'{session}.json','application/json')
