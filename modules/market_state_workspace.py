"""Market state UI; calculations live in pure research modules."""
import json
import pandas as pd
import streamlit as st
from modules.market_state_research import load_market_state, export_csv


def render_market_state():
    st.subheader('Market State Research')
    st.caption('Historical information available after each completed session close. Descriptive features and future research labels only; no trade recommendations.')
    with st.form('market_state_form'):
        a,b = st.columns(2)
        symbol = a.selectbox('Market-state symbol',['SPY','QQQ'])
        period = b.selectbox('Market-state history',['FIVE_YEARS','TEN_YEARS'])
        submitted = st.form_submit_button('Generate market-state dataset',type='primary')
    if submitted:
        try:
            with st.spinner('Loading completed daily OHLC and calculating historical states…'):
                st.session_state['market_state_result'] = load_market_state(symbol,period)
        except ValueError as exc:
            st.session_state.pop('market_state_result',None)
            st.error(str(exc))
            if hasattr(exc,'diagnostics'):
                with st.expander('History retrieval diagnostic'):
                    st.json(exc.diagnostics)
    result = st.session_state.get('market_state_result')
    if result is None:
        st.info('Select SPY or QQQ and generate a dataset. Missing warm-up history remains unavailable.')
        return
    meta = result['metadata']
    st.caption(f"Last submitted dataset: {meta['symbol']} · {meta.get('requested_period','')} · {meta['start']} to {meta['end']} · {meta['observations']:,} observations. Submit again to apply changed inputs.")
    st.warning('Provider OHLC adjustment for splits/dividends is unverified. Corporate actions can distort returns and indicators. This is not total-return performance or guaranteed point-in-time data.')
    for warning in meta['audit']['warnings']:
        st.warning(warning)
    latest = result['features'].iloc[-1]
    st.markdown(f"#### {meta['symbol']} MARKET STATE · {latest['date'].date()}")
    fields = [('Close','close','dollar'),('1D return','return_1d','pct'),('5D return','return_5d','pct'),
        ('RSI 14','rsi_14','number'),('EMA structure','ema_structure','text'),
        ('Distance from EMA21','distance_ema_21_pct','pct'),('Distance from EMA21 in ATR','distance_ema_21_atr','number'),
        ('ATR %','atr_pct','pct'),('20D realized volatility','realized_vol_20d','pct'),
        ('20D range position (0–1)','range_position_20','number')]
    for start in range(0,len(fields),4):
        columns = st.columns(4)
        for col,(label,key,fmt) in zip(columns,fields[start:start+4]):
            value = latest[key]
            shown = 'Unavailable' if pd.isna(value) else (f'{value:.2%}' if fmt=='pct' else f'${value:,.2f}' if fmt=='dollar' else f'{value:.2f}' if fmt=='number' else str(value))
            col.metric(label,shown)
    st.caption('EMA structure describes strict close/EMA9/EMA21/EMA50 ordering only. Equalities are mixed. Unavailable values are retained, not backfilled.')
    known,future,audit = st.tabs(['FEATURES AVAILABLE AT TIME T','FUTURE OUTCOMES — RESEARCH ONLY','Data quality & conventions'])
    with known:
        st.caption('Fractions in tables/exports are decimals (0.01 = 1%). These features contain no forward outcome columns.')
        st.dataframe(result['features'],hide_index=True,use_container_width=True)
        st.download_button('Export market-state features · CSV',export_csv(result,'features'),f"{meta['symbol']}-market-state-features.csv",'text/csv')
    with future:
        st.warning('Future information: never use these columns as live predictors. The first eligible excursion bar is T+1; last H rows remain unavailable. Excursions are signed and not clipped to zero.')
        st.dataframe(result['outcomes'],hide_index=True,use_container_width=True)
        st.download_button('Export future outcomes · CSV',export_csv(result,'outcomes'),f"{meta['symbol']}-future-outcomes.csv",'text/csv')
    with audit:
        st.json(meta)
        st.caption('Possible missing weekdays include exchange holidays. No exchange calendar is installed; session completeness cannot be certified. No missing days or prices were fabricated.')
        st.download_button('Export market-state metadata · JSON',json.dumps(meta,indent=2),f"{meta['symbol']}-market-state-metadata.json",'application/json')
