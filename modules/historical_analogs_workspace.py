"""Descriptive analog UI. No option recommendations or forecast probabilities."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.historical_analogs import analog_research, sensitivity_analysis, sample_warning, export_analogs
from modules.market_state import RAW, market_state_features


def _plot(fig, x_title, y_title):
    fig.update_layout(template='plotly_dark',paper_bgcolor='#0b111c',plot_bgcolor='#0b111c',
        height=350,margin=dict(l=20,r=20,t=30,b=35),xaxis_title=x_title,yaxis_title=y_title,
        legend=dict(orientation='h'))
    st.plotly_chart(fig,use_container_width=True)


def render_historical_analogs():
    st.subheader('Historical Analogs')
    st.write('An analog is a past trading day whose measurable market conditions resembled the selected target day. Historical analogs describe what happened in similar past environments. They do not predict what must happen next.')
    dataset=st.session_state.get('market_state_result')
    if dataset is None:
        st.session_state.pop('historical_analog_result',None)
        st.info('Generate a SPY or QQQ dataset in Market State Research first, then return here.')
        return
    features,outcomes,meta=dataset['features'],dataset['outcomes'],dataset['metadata']
    identity=(meta['source_ohlc_sha256'],meta['symbol'],meta.get('data_read_at'))
    st.caption(f"Using the last generated {meta['symbol']} dataset: {meta['start']} to {meta['end']}. Generate another dataset in Market State Research to change symbol or history.")
    with st.form('historical_analog_form'):
        a,b=st.columns(2)
        mode=a.selectbox('Analog target mode',['LATEST COMPLETED SESSION','HISTORICAL TARGET DATE'])
        historical=b.selectbox('Historical target date',list(reversed(features.date.tolist())),format_func=lambda d:str(d.date()))
        a,b,c=st.columns(3)
        method=a.selectbox('Analog method',['Tolerance filter','Standardized nearest neighbors'])
        horizon=b.selectbox('Research horizon (observed sessions)',[1,2,3,5,10],index=2)
        neighbors=c.selectbox('Closest N analogs',[25,50,100,200],index=2)
        exact=st.checkbox('Require exact EMA structure match',value=True)
        st.caption('The selected horizon sets the minimum outcome-maturity rule for candidate dates. Every displayed horizon also masks any outcome not yet known at the target close. N applies only to nearest neighbors.')
        with st.expander('Manual tolerance ranges'):
            a,b,c=st.columns(3)
            ret=a.number_input('5D return tolerance (percentage points)',min_value=0.,value=2.,step=.25)
            rsi=b.number_input('RSI tolerance (points)',min_value=0.,value=10.,step=1.)
            atr=c.number_input('EMA21 distance tolerance (ATR)',min_value=0.,value=.75,step=.05)
            a,b=st.columns(2)
            vol=a.number_input('20D volatility tolerance (percentage points)',min_value=0.,value=5.,step=.5)
            location=b.number_input('20D range-position tolerance (0–1 units)',min_value=0.,value=.20,step=.05)
            st.caption('Symmetric inclusive ranges around the target. Starting defaults are not optimized; ranges never widen automatically. These inputs apply only to tolerance matching.')
        submitted=st.form_submit_button('Find historical analogs',type='primary')
    if submitted:
        try:
            target=features.date.iloc[-1] if mode=='LATEST COMPLETED SESSION' else historical
            # Explicitly rebuild all predictor states from raw data through T only.
            prefix=features.loc[features.date<=target,RAW]
            as_of_features=market_state_features(prefix,target+pd.Timedelta(days=1))
            result=analog_research(as_of_features,outcomes,target_date=target,
                method='tolerance' if method=='Tolerance filter' else 'nearest',horizon=horizon,
                exact_structure=exact,neighbors=neighbors,tolerances=dict(return_5d=ret/100,rsi_14=rsi,
                    distance_ema_21_atr=atr,realized_vol_20d=vol/100,range_position_20=location))
            result['sensitivity']=sensitivity_analysis(as_of_features,outcomes,target,horizon,exact) if method=='Tolerance filter' else None
            result['dataset_identity']=identity
            result['target_mode']=mode
            st.session_state['historical_analog_result']=result
        except ValueError as exc:
            st.session_state.pop('historical_analog_result',None)
            st.error(str(exc))
    result=st.session_state.get('historical_analog_result')
    if result is None or result.get('dataset_identity')!=identity:
        st.info('Choose a target and method, then find historical analogs. Early dates may lack the required indicator history.')
        return
    target=result['target']
    st.markdown(f"#### {target.symbol} HISTORICAL ANALOG RESEARCH · {target.date.date()}")
    st.caption(f"Target state — {result['target_mode']}. Results reflect the last submitted settings; submit again to apply changes.")
    fields=[('Target close','close','price'),('Target 5D return','return_5d','pct'),('Target RSI14','rsi_14','num'),
        ('Target EMA structure','ema_structure','text'),('Target EMA21 distance (ATR)','distance_ema_21_atr','num'),
        ('Target 20D realized volatility','realized_vol_20d','pct'),('Target 20D range position','range_position_20','num')]
    for start in (0,4):
        for col,(label,key,fmt) in zip(st.columns(4),fields[start:start+4]):
            value=target[key]
            shown='Unavailable' if pd.isna(value) else f'${value:,.2f}' if fmt=='price' else f'{value:.2%}' if fmt=='pct' else f'{value:.2f}' if fmt=='num' else str(value)
            col.metric(label,shown)
    a,b,c=st.columns(3)
    a.metric('Historical dates before target',result['audit']['prior_dates'])
    b.metric('Eligible historical candidates',result['audit']['eligible_dates'])
    c.metric('Final analog sample',len(result['analogs']))
    st.caption(f"Method: {result['config']['method']} · Maturity horizon: {result['config']['horizon']} observed sessions · Exact EMA match: {result['config']['exact_structure']}")
    st.warning(sample_warning(len(result['analogs'])))
    for note in result['notes']:
        st.warning(note)
    evidence,transparency,sensitivity,table=st.tabs(['Observed outcomes','Matching transparency','Tolerance sensitivity','All analog observations'])
    with transparency:
        st.caption('Funnel order: before target → selected-horizon maturity → complete features → EMA structure → 5D return → RSI → EMA21 ATR distance → volatility → range position. Nearest neighbors uses EMA filtering followed by distance selection.')
        st.dataframe(result['funnel'],hide_index=True,use_container_width=True)
        st.caption('Independent pass counts apply each filter to the same eligible pool, before any other matching filter. Sequential counts depend on the documented order.')
        st.dataframe(result['independent_passes'],hide_index=True,use_container_width=True)
        if not result['independent_passes'].empty and result['config']['method']=='tolerance':
            restrictive=result['independent_passes'].sort_values('eliminated',ascending=False,kind='stable').iloc[0]
            st.write(f"Largest independent exclusion: {restrictive['feature']} ({int(restrictive['eliminated'])} of {int(restrictive['eligible'])} eligible dates). No tolerances were changed automatically.")
        if result['config']['method']=='nearest':
            st.caption('Euclidean distance between z-scores. Population standard deviations are fitted on complete, matured candidates strictly before target, before EMA filtering. Each active feature has equal standardized weight. Date ascending breaks ties.')
            st.dataframe(result['scaler'],hide_index=True,use_container_width=True)
    with evidence:
        summary=result['summary']
        view=summary.copy()
        rate_columns=[c for c in view if c not in ('horizon','n','n_high_excursion','n_low_excursion')]
        view[rate_columns]=view[rate_columns]*100
        view=view.rename(columns={c:c+' (%)' for c in rate_columns})
        st.caption('Historical frequencies, returns and excursions below are percentages. Zero returns count as neither positive nor negative. Each horizon has its own valid N; excursion counts are reported separately.')
        st.dataframe(view,hide_index=True,use_container_width=True)
        chart_h=st.selectbox('Distribution horizon',[1,2,3,5,10],index=HORIZON_INDEX[result['config']['horizon']])
        row=summary.loc[summary.horizon==chart_h].iloc[0]
        st.caption(f"{chart_h}-session valid outcomes: {int(row['n'])}. {sample_warning(int(row['n']))}")
        if row['n']:
            st.write(f"Historically, {row['positive_frequency']:.1%} of {int(row['n'])} selected analog observations had a positive {chart_h}-session close-to-close return. The median was {row['median_return']:+.2%}; the 10th percentile was {row['p10_return']:+.2%}.")
            values=result['analogs'][f'future_return_{chart_h}s'].dropna()*100
            fig=go.Figure(go.Histogram(x=values,nbinsx=30,marker_color='#61d8c1',name='Observed returns'))
            fig.add_vline(x=0,line_color='#a1acbb',annotation_text='Zero')
            fig.add_vline(x=float(values.median()),line_color='#f4bd62',line_dash='dash',annotation_text='Median')
            _plot(fig,'Forward close-to-close return (%)','Analog observations')
        else:
            st.info('No valid outcomes for this horizon as of the target. Nothing was widened or substituted.')
        fig=go.Figure()
        for col,label in [('p10_return','10th'),('p25_return','25th'),('median_return','Median'),('p75_return','75th'),('p90_return','90th')]:
            fig.add_trace(go.Scatter(x=summary.horizon,y=summary[col]*100,mode='lines+markers',name=label,connectgaps=False))
        _plot(fig,'Forward observed sessions','Historical return percentile (%)')
        analogs=result['analogs']
        y=analogs['similarity_distance'] if 'similarity_distance' in analogs else np.ones(len(analogs))
        fig=go.Figure(go.Scatter(x=analogs.date,y=y,mode='markers',name='Analog dates',marker=dict(color='#61d8c1',size=6)))
        _plot(fig,'Analog date','Standardized distance' if 'similarity_distance' in analogs else 'Matched observation')
        if not analogs.empty:
            st.dataframe(analogs.groupby(analogs.date.dt.year).size().rename('Analog count').rename_axis('Year').reset_index(),hide_index=True)
    with sensitivity:
        if result['sensitivity'] is None:
            st.info('Select the tolerance method to compare TIGHT, DEFAULT and WIDE presets.')
        else:
            st.caption('TIGHT=0.75×, DEFAULT=1×, WIDE=1.5× the documented starting tolerances, not your manually edited values. Same target, maturity horizon and EMA rule. No preset is selected based on outcomes.')
            view=result['sensitivity'].copy()
            view['median_return (%)']=view.pop('median_return')*100
            view['positive_frequency (%)']=view.pop('positive_frequency')*100
            st.dataframe(view,hide_index=True,use_container_width=True)
    with table:
        st.caption('Signed decimal returns/excursions (0.01 = 1%). Unknown-as-of-target outcomes are blank. This table combines features and future labels for research only; never use it as a live predictor dataset.')
        st.dataframe(result['analogs'],hide_index=True,use_container_width=True)
        st.download_button('Export historical analogs · CSV',export_analogs(result,meta),f"{target.symbol}-{target.date.date()}-historical-analogs.csv",'text/csv')
    st.warning('Results depend on chosen features and tolerances. Similarity does not imply identical conditions. Samples are not independent; overlapping forward horizons can produce correlated observations. Historical frequencies are not calibrated probabilities or guarantees.')
    st.caption('Public corporate-action adjustment and exchange-calendar completeness remain unverified. Horizons count observed bars. Today’s session is conservatively excluded by the data loader; history may be revised. No options expectancy, survival estimates, trade recommendations, or automatic parameter optimization are provided.')
    for warning in meta.get('audit',{}).get('warnings',[]):
        st.caption(warning)


HORIZON_INDEX={h:i for i,h in enumerate((1,2,3,5,10))}
