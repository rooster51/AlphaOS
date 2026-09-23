"""One selected-trade research workspace, with explicit submitted snapshots."""
from datetime import datetime, timedelta
import hashlib
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st
from modules.research_session import get_research_session
from modules.daily_archive import canonical_bytes, digest
from modules.options_payoff import validate_trade
from modules.phase6_research import research_workspace, chain_verticals, compare_candidates
from modules.historical_analogs import sample_warning


def render_phase6():
    st.subheader('Trade Research · Price Structure')
    st.caption('Historical evidence for one trade. Descriptive zones and scenario distributions are not predictions, price targets, or recommendations.')
    active=get_research_session(st.session_state)
    if active is None:
        dataset=st.session_state.get('market_state_result')
        if dataset:
            active=dict(history=dataset['features'][['date','symbol','open','high','low','close']],metadata=dataset['metadata'])
    if active is None:
        st.info('Generate Market State Research for SPY or QQQ first. The completed daily dataset is reused here.'); return
    bars=active['history']; metadata=active.get('metadata',{})
    symbol=str(bars.symbol.iloc[-1]); today=datetime.now(ZoneInfo('America/New_York')).date()
    source=st.selectbox('Trade Research input',['Enter a vertical','Selected opportunity','Saved manual trade'],key='p6_source')
    saved=None
    if source!='Enter a vertical':
        try: saved=validate_trade(st.session_state.get('quant_selected_option' if source=='Selected opportunity' else 'quant_manual_option'))
        except ValueError:
            st.info('Save a matching trade in Strategy Selector or Options stress lab first.'); return
        if saved['symbol']!=symbol:
            st.warning('Trade and research symbols differ. Load matching Market State Research.'); return
        st.dataframe(pd.DataFrame(saved['legs']),hide_index=True)
    with st.form('p6_form'):
        a,b,c=st.columns(3)
        spot=a.number_input('Current trade spot',min_value=.01,value=float(saved['spot'] if saved else bars.close.iloc[-1]))
        credit=b.number_input('Credit per share for entered spread',min_value=.0001,value=float(saved['credit'] if saved else .20))
        expiry=c.date_input('Trade expiration',value=pd.Timestamp(saved['expiration']).date() if saved else today+timedelta(days=7))
        if saved is None:
            a,b,c=st.columns(3)
            kind=a.selectbox('Vertical strategy',['Put credit spread','Call credit spread'])
            short=b.number_input('Short strike',min_value=.01,value=float(round(float(bars.close.iloc[-1])*.99)))
            long=c.number_input('Long strike',min_value=.01,value=float(round(float(bars.close.iloc[-1])*.99)-1))
        a,b=st.columns(2)
        horizon=a.selectbox('Trade Research observed-session horizon',[1,2,3,5,10],index=2)
        method=b.selectbox('Trade Research analog method',['tolerance','nearest'])
        st.caption('Choose the observed-session horizon explicitly. Calendar DTE does not determine this setting. All five horizons are shown with separately matured analog samples.')
        a,b,c=st.columns(3)
        commission=a.number_input('Research extra commission / contract ($)',min_value=0.,value=0.)
        slip=b.number_input('Research entry slippage / structure ($)',min_value=0.,value=0.)
        terminal=c.number_input('Research exit friction / structure ($)',min_value=0.,value=0.)
        submit=st.form_submit_button('Run integrated trade research',type='primary')
    identity=digest(dict(history=bars,metadata=metadata,source=source,saved=saved,completed_before=str(today)))
    if submit:
        st.session_state.pop('phase6_result',None)
        try:
            if expiry<today: raise ValueError('Select an unexpired structure.')
            if saved:
                if expiry.isoformat()!=saved['expiration']: raise ValueError('Saved legs retain their expiration. Enter a new vertical to change it.')
                trade={**saved,'spot':spot,'credit':credit}
            else:
                trade=dict(symbol=symbol,strategy=kind,expiration=expiry.isoformat(),spot=spot,stock_basis=spot,
                    shares=0,fees=0,credit=credit,source='Explicit manual research input',
                    legs=[dict(type='Put' if kind.startswith('Put') else 'Call',strike=short,qty=-1),
                          dict(type='Put' if kind.startswith('Put') else 'Call',strike=long,qty=1)])
            with st.spinner('Building completed-state research and fixed robustness comparisons…'):
                result=research_workspace(bars,trade,today,horizon,method,metadata,
                    commission_per_contract=commission,entry_slippage=slip,terminal_friction=terminal)
            st.session_state['phase6_result']=dict(identity=identity,result=result)
        except (ValueError,TypeError,KeyError) as exc: st.error(str(exc))
    stored=st.session_state.get('phase6_result')
    if not stored or stored['identity']!=identity:
        st.info('Submit the trade inputs to build a research snapshot.'); return
    r=stored['result']; c=r['evidence']['context']; ev=r['evidence']['economics']; threshold=r['evidence']['threshold']
    st.caption('Showing the last submitted snapshot. Submit again after changing inputs. All dollar figures use the entered structure quantities; returns and frequencies are decimal fractions in exports.')
    st.markdown('#### 1. Market snapshot')
    a,b,d=st.columns(3)
    a.metric('Research anchor · completed close',f"${c['research_close']:,.2f}")
    b.metric('Current trade spot',f"${c['current_spot']:,.2f}")
    d.metric('Research session',r['provenance']['research_date'])
    st.caption('Completed daily history excludes today conservatively, even after close. Current trade spot and premium are explicit inputs, not independently verified live prices.')
    st.markdown('#### 2. Support / resistance')
    st.caption('Historical price-structure zones. Observations count unique pivot/extreme session dates, not every intraday touch. Distances use current trade spot and completed-history ATR.')
    st.dataframe(r['levels'].rename(columns={'distance_pct':'Distance from current spot (decimal)','distance_atr':'Distance in ATR',
        'observations':'Unique structural observations','last_observed_sessions_ago':'Sessions since last observation',
        'touch_frequency':'Historical touch frequency','terminal_beyond_frequency':'Historical finish-beyond frequency',
        'rejection_given_touch':'Rejection conditional on touch','break_hold_given_touch':'Finish beyond conditional on touch',
        'terminal_equal_frequency':'Historical finish-at-level frequency',
        'median_post_level_excursion':'Median continuation (decimal return)',
        'p75_post_level_excursion':'P75 continuation','p90_post_level_excursion':'P90 continuation'}),hide_index=True)
    if r['levels'].empty: st.info('No nearby structural zones were identified.')
    st.markdown('#### 3. Historical move distribution')
    rows=[]
    labels={'terminal_return':'Terminal return','terminal_spot':'Terminal scenario price','max_up_excursion':'Maximum upside excursion',
        'max_down_excursion':'Maximum downside excursion','upside_spot':'Upside excursion scenario price','downside_spot':'Downside excursion scenario price'}
    for h,distribution in r['distributions'].items():
        for field,values in distribution['summary'].items():
            rows.append({'Observed sessions':h,'Measure':labels[field],'N':distribution['counts'][field],**values})
    st.dataframe(pd.DataFrame(rows),hide_index=True)
    st.caption('Scenario prices are anchored to current trade spot. They are not price targets. Horizon samples can differ because maturity is enforced separately.')
    st.markdown('#### 4. Selected option threshold')
    st.dataframe(pd.DataFrame([{**c,'Calendar DTE':(pd.Timestamp(c['expiration']).date()-today).days}]).drop(columns=['mode']),hide_index=True)
    s=threshold['summary']
    a,b,d=st.columns(3)
    def pct(value): return 'Unavailable' if value is None else f'{value:.1%}'
    a.metric('Historical survival '+('ABOVE short strike' if c['mode']=='put' else 'BELOW short strike'),pct(s['survival_frequency']))
    b.metric('Historical touch / breach frequency',pct(s['touch_frequency']))
    d.metric('Historical finish-beyond frequency',pct(s['terminal_breach_frequency']))
    if threshold['config']['opposite_side']: st.warning('Short strike is across current spot from the usual out-of-the-money direction.')
    st.caption('Touch includes equality. Finishing beyond is strict; terminal equality is separate. Breach and recovery means a touch/breach followed by terminal survival, not an observed intraday event sequence.')
    st.dataframe(pd.DataFrame({'Full sample':s,'Non-overlapping paired diagnostic':threshold['non_overlapping_summary']}))
    st.markdown('#### 5. Option economics')
    st.warning(sample_warning(ev['net_summary']['n']))
    st.dataframe(pd.DataFrame({'Before additional friction':ev['gross_summary'],'After additional friction':ev['net_summary']}))
    st.caption('Existing saved fees are included once. EV/max risk retains the Phase 5.2 denominator: entry max risk before additional modeled friction. Historical scenario EV is not a guarantee of positive expectancy; positive-payoff frequency is not forecast probability.')
    st.markdown('#### 6. Robustness')
    st.dataframe(r['robustness'],hide_index=True)
    st.caption('Fixed Tight / Default / Wide / Nearest 50 and primary non-overlapping comparisons. No favorable definition is selected automatically; non-overlap does not establish independence.')
    st.markdown('#### 7. Detailed observations / exports')
    with st.expander('Level behavior and continuation definitions'):
        st.caption('Touch then rejection finishes strictly on the original side. Break and hold finishes strictly beyond; equality belongs to neither. Continuation measures maximum excursion beyond the level, not a timed post-touch path or persistent hold. Daily OHLC cannot establish intraday sequence.')
        for detail in r['level_details']:
            st.write(detail['config']); st.dataframe(detail['observations'],hide_index=True)
    with st.expander('Scenario observations and provenance'):
        st.dataframe(ev['observations'],hide_index=True); st.json(canonical_bytes(r['provenance']).decode())
    st.download_button('Export integrated research JSON',canonical_bytes(r),'alphaos-trade-research.json','application/json')
    st.download_button('Export payoff observations CSV',ev['observations'].to_csv(index=False),'alphaos-payoffs.csv','text/csv')
    with st.expander('Compare option-chain candidates · research only'):
        st.caption('Upload a normalized chain CSV: symbol, expiration (YYYY-MM-DD), type (put/call), strike, bid, ask, observed_at (timezone required), contract. Maximum 100 contracts / 200 spreads. Short bid minus long ask is a hypothetical credit, not a fill. Every candidate uses the submitted observed-session horizon, regardless of DTE; narrow expirations to your intended horizon. Archived observations remain dated observations, not current quotes.')
        upload=st.file_uploader('Normalized option chain',type=['csv'],key='p6_chain')
        candidate_identity=None if upload is None else digest(dict(content_sha256=hashlib.sha256(upload.getvalue()).hexdigest(),research=r['provenance'],trade=r['trade']))
        if upload is not None and st.button('Compare candidate evidence'):
            st.session_state.pop('phase6_candidates',None)
            try:
                upload.seek(0)
                chain=pd.read_csv(upload)
                trades,rejected=chain_verticals(chain,symbol,c['current_spot'],today)
                comparison=compare_candidates(trades,r,today,**r['provenance']['friction'])
                comparison['chain_rejections']=rejected
                comparison['research_provenance']=r['provenance']
                st.session_state['phase6_candidates']=dict(identity=candidate_identity,result=comparison)
            except (ValueError,TypeError,KeyError) as exc: st.error(str(exc))

        comparison=st.session_state.get('phase6_candidates')
        if comparison and comparison['identity']==candidate_identity:
            comparison=comparison['result']
            st.dataframe(comparison['candidates'],hide_index=True)
            st.dataframe(comparison['chain_rejections'],hide_index=True)
            st.dataframe(comparison['rejected'],hide_index=True)
            st.download_button('Export candidate evidence CSV',comparison['candidates'].to_csv(index=False),'alphaos-candidates.csv','text/csv')
            st.download_button('Export candidate evidence with provenance',canonical_bytes(comparison),'alphaos-candidates.json','application/json')
            st.caption('Rows follow contract order. There is no recommendation, ranking score, or best-trade selection.')
