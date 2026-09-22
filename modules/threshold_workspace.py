"""Threshold research presentation, separate from model/provider POP."""
import hashlib
import json
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.historical_analogs import sample_warning
from modules.threshold_survival import (threshold_research,distance_grid,horizon_matrix,
    extract_short_strikes,selected_trade_threshold,export_threshold_observations)


def _percent(value):
    return 'Unavailable' if value is None or pd.isna(value) else f'{value:.1%}'


def _interval(low,high):
    return 'Unavailable' if low is None else f'{low:.1%}–{high:.1%}'


def _identity(analogs):
    return hashlib.sha256((json.dumps(analogs['config'],sort_keys=True)+analogs['analogs'].to_csv(index=False)
        +str(analogs['target']['close'])).encode()).hexdigest()


def render_threshold_research():
    st.subheader('Threshold Research')
    st.write('Terminal survival asks whether the underlying finished on the safe side of a threshold. Touch/breach asks whether daily highs or lows reached or crossed it during the intervening sessions. A threshold can be breached intraperiod and still survive at the terminal close.')
    analogs=st.session_state.get('historical_analog_result')
    dataset=st.session_state.get('market_state_result')
    if analogs is None or dataset is None:
        st.info('Generate Market State Research, then run Historical Analogs before opening threshold research.')
        return
    meta=dataset['metadata']
    dataset_identity=(meta['source_ohlc_sha256'],meta['symbol'],meta.get('data_read_at'))
    if analogs.get('dataset_identity')!=dataset_identity:
        st.info('The market dataset changed. Run Historical Analogs again before researching thresholds.')
        return
    identity=_identity(analogs)
    target=analogs['target']
    st.caption(f"Saved analog sample: {target.symbol} · target {target.date.date()} · spot ${target.close:,.2f} · {len(analogs['analogs'])} analogs · matching horizon {analogs['config']['horizon']} sessions. Threshold research keeps this membership fixed; changing its horizon does not refill or rematch the sample.")
    input_mode=st.selectbox('Threshold input',['Percentage distance','Price threshold','Use short strike from selected trade'])
    chosen=None
    if input_mode=='Use short strike from selected trade':
        if analogs.get('target_mode')!='LATEST COMPLETED SESSION':
            st.warning('Saved-trade shortcuts are disabled for historical targets so a later trade cannot silently set a historical threshold. Enter an explicit hypothetical price or percentage instead.')
            return
        source=st.selectbox('Short-strike trade source',['Selected opportunity','Manual trade'])
        trade=st.session_state.get('quant_selected_option' if source=='Selected opportunity' else 'quant_manual_option')
        try:
            shorts=extract_short_strikes(trade,target.symbol)
        except ValueError as exc:
            st.warning(str(exc))
            return
        if not shorts:
            st.info('The saved trade has no short option legs. Enter a threshold manually.')
            return
        choice=st.selectbox('Short leg to research',range(len(shorts)),
            format_func=lambda i:f"{shorts[i]['type']} strike ${shorts[i]['strike']:g} · {shorts[i]['contracts']:g} short contract(s)")
        chosen=selected_trade_threshold(analogs,trade,shorts[choice]['leg_index'])
        st.caption('Only the selected short strike is copied. Normalization uses the market-state target spot, not a saved trade quote. Research each condor side separately. Option expiration is not mapped to a session horizon automatically.')
    with st.form('threshold_research_form'):
        a,b=st.columns(2)
        label=a.selectbox('Threshold research mode',['Short put style — ABOVE','Short call style — BELOW'],
            index=1 if chosen and chosen['mode']=='call' else 0,disabled=chosen is not None)
        mode=chosen['mode'] if chosen else ('put' if label.startswith('Short put') else 'call')
        horizon=b.selectbox('Threshold horizon (observed sessions)',[1,2,3,5,10],index=2)
        price=distance=None
        if chosen:
            price=chosen['threshold_price']
            st.write(f"Selected short strike: ${price:g} · {'Put' if mode=='put' else 'Call'} style")
        elif input_mode=='Price threshold':
            price=st.number_input('Threshold price ($)',min_value=.000001,value=float(target.close*.985),format='%.6f')
        else:
            distance=st.number_input('Signed threshold distance (%)',min_value=-99.9999,value=-1.5,step=.25,format='%.4f')/100
            st.caption('Put-style distances are normally negative; call-style distances normally positive. For example, enter −1.5 for a put threshold 1.5% below spot.')
        allow=st.checkbox('I intentionally want a threshold on the opposite side of target spot',value=False)
        grid_text=st.text_input('Distance grid (% magnitudes, comma separated)',value='0.5, 1, 1.5, 2, 2.5, 3')
        st.caption('Grid values are positive magnitudes: automatically negative for put style and positive for call style. No best threshold is selected.')
        submitted=st.form_submit_button('Run threshold research',type='primary')
    if submitted:
        try:
            distances=[float(s.strip())/100 for s in grid_text.split(',')]
            result=threshold_research(analogs,mode,horizon,threshold_price=price,threshold_return=distance,allow_opposite=allow)
            result['grid']=distance_grid(analogs,mode,distances=distances)
            result['analog_identity']=identity
            result['input_mode']=input_mode
            st.session_state['threshold_research_result']=result
        except ValueError as exc:
            st.session_state.pop('threshold_research_result',None)
            st.error(str(exc) or 'Enter a valid comma-separated distance grid.')
    result=st.session_state.get('threshold_research_result')
    if result is None or result.get('analog_identity')!=identity:
        st.info('Submit the threshold settings to evaluate the saved analog sample.')
        return
    cfg,s=result['config'],result['summary']
    st.markdown(f"#### {cfg['symbol']} THRESHOLD RESEARCH · {cfg['target_date']}")
    st.caption(f"Last submitted result · {cfg['mode'].upper()} style · {cfg['horizon']} observed sessions · {result['input_mode']}")
    a,b,c,d=st.columns(4)
    a.metric('Threshold target spot',f"${cfg['target_spot']:,.2f}")
    b.metric('Research threshold',f"${cfg['threshold_price']:,.4f}")
    c.metric('Relative threshold distance',f"{cfg['threshold_return']:+.4%}")
    d.metric('Selected analog sample',s['sample_n'])
    if cfg['opposite_side']:
        st.warning('OPPOSITE-SIDE THRESHOLD: explicitly acknowledged. The selected put threshold is above spot or call threshold below spot; this differs from the usual out-of-the-money research convention.')
    st.caption('Each historical threshold = that analog’s close × (threshold price ÷ target spot). Raw strike prices are never applied directly across history.')
    terminal,touch,recovery=st.columns(3)
    with terminal:
        st.markdown('##### TERMINAL — finished safely')
        st.metric('Historical analog terminal survival',_percent(s['survival_frequency']))
        st.write(f"Survived: {s['survived_n']} / {s['terminal_valid_n']} · Strict terminal breaches: {s['terminal_breached_n']} · Equal: {s['equality_n']}")
        st.write('Historical terminal breach frequency: '+_percent(s['terminal_breach_frequency']))
        st.caption('95% Wilson interval for the observed historical frequency: '+_interval(s['survival_wilson_low'],s['survival_wilson_high']))
    with touch:
        st.markdown('##### INTRAPERIOD — touched or crossed')
        st.metric('Historical touch/breach frequency',_percent(s['touch_frequency']))
        st.write(f"Touched/breached: {s['touch_n']} / {s['touch_valid_n']} · No-touch: {s['no_touch_n']}")
        st.write('Historical no-touch frequency: '+_percent(s['no_touch_frequency']))
        st.caption('95% Wilson interval for the observed historical frequency: '+_interval(s['touch_wilson_low'],s['touch_wilson_high']))
    with recovery:
        st.markdown('##### RECOVERY — breached then survived')
        st.metric('Breached but terminally survived',s['recovery_n'])
        st.write(f"{_percent(s['recovery_frequency_all'])} of {s['paired_valid_n']} paired-valid observations")
        st.write(f"{_percent(s['recovery_frequency_touched'])} of {s['paired_touch_n']} touched observations with a known terminal close")
    st.caption('Terminal denominator: matured finite close returns. Touch denominator: matured finite relevant excursions. Recovery requires both; its conditional denominator is touched observations within that paired sample. Equality is a separate terminal category, not survival; touch includes equality. A 1e−12 decimal-return tolerance handles floating-point equality.')
    st.warning(f"Terminal N={s['terminal_valid_n']}: {sample_warning(s['terminal_valid_n'])} Touch N={s['touch_valid_n']}: {sample_warning(s['touch_valid_n'])}")
    st.caption('Wilson intervals are nominal binomial intervals for observed historical frequencies. Overlap, clustering and selected samples violate independent-binomial assumptions; these intervals are not calibrated forecast uncertainty.')
    grids,context,robust,details=st.tabs(['Distance grid & horizons','Distribution context','Non-overlapping robustness','Threshold observations'])
    with grids:
        grid=result['grid']
        view=grid[grid.horizon==cfg['horizon']][['threshold_return','terminal_valid_n','touch_valid_n','paired_valid_n','survival_frequency','touch_frequency','recovery_frequency_all']].copy()
        for col in ['threshold_return','survival_frequency','touch_frequency','recovery_frequency_all']:
            view[col+' (%)']=view.pop(col)*100
        st.caption('Selected-horizon grid. Denominators can differ; recovery uses paired-valid N. No threshold ranking or recommendation.')
        st.dataframe(view,hide_index=True,use_container_width=True)
        for name,field,nfield in [('TERMINAL SURVIVAL','survival_frequency','terminal_valid_n'),('TOUCH / BREACH','touch_frequency','touch_valid_n')]:
            st.markdown('##### '+name)
            matrix=horizon_matrix(grid,field)*100
            matrix.index=(matrix.index*100).round(6)
            matrix.index.name='Signed threshold distance (%)'
            st.dataframe(matrix,use_container_width=True,column_config={str(h):st.column_config.NumberColumn(format='%.1f') for h in matrix.columns})
            with st.expander(name+' valid N per cell'):
                counts=horizon_matrix(grid,nfield)
                counts.index=(counts.index*100).round(6)
                st.dataframe(counts,use_container_width=True)
        st.caption('Matrix values are historical percentages, not probabilities. Every horizon has a fresh maturity/validity mask on the same original Phase 3 sample.')
    with context:
        percentiles=result['distribution_percentiles']
        st.dataframe(pd.DataFrame({'Percentile':['10th','25th','Median','75th','90th'],
            'Forward return (%)':[None if v is None else v*100 for v in percentiles.values()]}),hide_index=True)
        st.write(f"Selected threshold distance: {cfg['threshold_return']:+.4%}")
        values=result['observations'][f"future_return_{cfg['horizon']}s"].dropna()*100
        if len(values):
            fig=go.Figure(go.Histogram(x=values,nbinsx=30,name='Analog forward returns',marker_color='#61d8c1'))
            fig.add_vline(x=cfg['threshold_return']*100,line_color='#f4bd62',annotation_text='Threshold')
            fig.add_vline(x=values.median(),line_dash='dash',line_color='#7da9ff',annotation_text='Median')
            fig.update_layout(template='plotly_dark',paper_bgcolor='#0b111c',plot_bgcolor='#0b111c',height=350,
                xaxis_title='Forward close return (%)',yaxis_title='Valid analog observations')
            st.plotly_chart(fig,use_container_width=True)
        else:
            st.info('No valid terminal outcomes at this horizon; distribution is unavailable.')
    with robust:
        subset=result['non_overlapping_summary']
        comparison=pd.DataFrame([{'Sample':label,'Terminal N':row['terminal_valid_n'],'Touch N':row['touch_valid_n'],
            'Historical survival (%)':None if row['survival_frequency'] is None else row['survival_frequency']*100,
            'Historical touch/breach (%)':None if row['touch_frequency'] is None else row['touch_frequency']*100}
            for label,row in [('FULL ANALOG SAMPLE',s),('NON-OVERLAPPING SAMPLE',subset)]])
        st.dataframe(comparison,hide_index=True,use_container_width=True)
        st.caption('Greedy earliest-first selection among paired-valid observations. Future windows i+1 through i+H cannot share an observed bar; next signal j must be at least i+H. This reduces horizon overlap, not all dependence. If full-sample denominators differ, the subset also reflects complete-case filtering.')
        st.warning(sample_warning(subset['paired_valid_n']))
    with details:
        st.dataframe(result['observations'],hide_index=True,use_container_width=True)
        st.download_button('Export threshold observations · CSV',export_threshold_observations(result,analogs['config']),
            f"{cfg['symbol']}-threshold-research.csv",'text/csv')
    st.warning('These frequencies describe selected historical analogs. They are not option POP, calibrated forecasts, expected returns, or realized option profitability. Provider/model POP elsewhere remains separate. Short-strike survival ignores credit received.')
    st.caption('Daily OHLC cannot reveal intraday path or event order. Touch uses daily high/low only. No option premium history, Greeks path, bid/ask spread, slippage, early assignment or stop-loss execution is modeled. Corporate-action adjustment, exchange-calendar completeness and point-in-time data revisions remain unverified. Horizons count observed bars; today is conservatively excluded. Overlapping analogs are dependent and historical frequencies are not guaranteed future probabilities.')

