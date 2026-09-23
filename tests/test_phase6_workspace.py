from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from modules.phase6_research import research_workspace, chain_verticals, compare_candidates
from modules.price_structure import price_structure
from modules.level_behavior import level_behavior
from modules.forward_distribution import summarize_forward_distribution
from modules.research_session import save_research_session
from modules.historical_analogs import analog_research, DEFAULT_TOLERANCES
from modules.market_state import market_state_features
from modules.market_outcomes import forward_outcomes
from modules.option_scenario_ev import scenario_economics


def history():
    n=260; p=100+np.sin(np.arange(n)/6)*3
    return pd.DataFrame(dict(date=pd.bdate_range('2020-01-02',periods=n),symbol='SPY',open=p,high=p+1,low=p-1,close=p))


def trade(call=False):
    return dict(symbol='SPY',strategy='Credit vertical',expiration='2030-01-18',source='Fixture',
        spot=100.,credit=.2,fees=0,shares=0,stock_basis=100.,legs=[
        dict(type='Call' if call else 'Put',strike=101. if call else 99.,qty=-1),
        dict(type='Call' if call else 'Put',strike=102. if call else 98.,qty=1)])


def workspace(call=False):
    return research_workspace(history(),trade(call),'2022-01-01',method='nearest')


@pytest.mark.parametrize('call',[False,True])
def test_selected_direction_and_current_anchor(call):
    r=workspace(call); e=r['evidence']; c=e['context']
    assert c['research_close'] != 100
    assert e['threshold']['config']['target_spot']==100
    assert e['threshold']['config']['mode']==('call' if call else 'put')
    assert c['strike_distance_pct']==pytest.approx(.01 if call else -.01)
    assert c['nearest_structural_level'] is not None
    for h,d in r['distributions'].items():
        assert d['summary']['terminal_spot']['p50']==pytest.approx(100*(1+d['summary']['terminal_return']['p50']))
    assert e['economics']['config']['research_close']==c['research_close']


def test_robustness_matches_frozen_calculations():
    r=workspace(); bars=history(); features=market_state_features(bars,'2022-01-01'); outcomes=forward_outcomes(bars,'2022-01-01')
    for name,mult in [('Tight tolerance',.75),('Default tolerance',1.),('Wide tolerance',1.5)]:
        a=analog_research(features,outcomes,horizon=3,tolerances={k:v*mult for k,v in DEFAULT_TOLERANCES.items()})
        expected=scenario_economics(a,trade(),3)['net_summary']
        actual=r['robustness'].set_index('sample').loc[name]
        assert actual['n']==expected['n']
        assert actual.expected_payoff==pytest.approx(expected['expected_payoff'])
    assert list(r['robustness']['sample'])==['Tight tolerance','Default tolerance','Wide tolerance','Nearest 50','Primary non-overlapping diagnostic']


def test_future_mutation_cannot_change_research():
    bars=history(); cutoff=bars.date.iloc[230]
    before=research_workspace(bars,trade(),cutoff,method='nearest')
    bars.loc[bars.date>=cutoff,['open','high','low','close']]*=5
    after=research_workspace(bars,trade(),cutoff,method='nearest')
    assert before['provenance']['ohlc_sha256']==after['provenance']['ohlc_sha256']
    pd.testing.assert_frame_equal(before['robustness'],after['robustness'])
    pd.testing.assert_frame_equal(before['structure']['levels'],after['structure']['levels'])


def test_maturity_rechecked_even_when_flags_claim_true():
    r=workspace(); a=r['primary'].copy(); a['analogs']=a['analogs'].tail(1).copy()
    a['analogs']['date']=a['session_dates'].iloc[-2]
    a['analogs']['outcome_known_by_target_10s']=True
    a['analogs']['future_return_10s']=.5
    d=summarize_forward_distribution(a,10,100)
    assert d['n']==0
    assert level_behavior(a,horizon=10,anchor_spot=100,level=101,side='resistance')['summary']['n']==0


def test_empty_small_and_missing_excursion_samples():
    a=workspace()['primary']; a['analogs']=a['analogs'].iloc[:1].copy()
    assert summarize_forward_distribution(a,3,100)['n']==1
    a['analogs']['future_high_excursion_3s']=np.nan
    d=summarize_forward_distribution(a,3,100)
    assert d['n']==1 and d['counts']['max_up_excursion']==0
    assert level_behavior(a,horizon=3,anchor_spot=100,level=101,side='resistance')['summary']['n']==0
    a['analogs']=a['analogs'].iloc[:0]
    assert summarize_forward_distribution(a,3,100)['summary']['terminal_spot']['p10'] is None


def test_structure_deterministic_zones_and_validation():
    s=price_structure(history(),completed_before='2022-01-01',anchor_spot=100)
    assert {'support','resistance'}==set(s['levels'].side)
    assert (s['levels'].observations>=1).all()
    assert (s['levels'].last_observed_sessions_ago>=0).all()
    assert s['levels'].zone_low.lt(s['levels'].zone_high).all()
    broken=history(); broken.loc[0,'high']=np.inf
    with pytest.raises(ValueError): price_structure(broken)
    with pytest.raises(ValueError): price_structure(pd.concat([history(),history().tail(1)]))
    with pytest.raises(ValueError): price_structure(history(),lookback=3)


def chain():
    return pd.DataFrame([dict(symbol='SPY',expiration='2030-01-18',type='put',strike=k,bid=b,ask=a,
        observed_at='2026-09-23T14:00:00Z',contract=f'SPY-{k}') for k,b,a in [(98,.05,.1),(99,.3,.35),(100,.7,.8)]])


def test_chain_comparison_provenance_no_score():
    trades,rejected=chain_verticals(chain(),'SPY',100,'2026-09-23')
    assert not len(rejected) and len(trades)==3
    assert trades[0]['credit']==pytest.approx(.2)
    r=workspace(); table=compare_candidates(trades,r,'2026-09-23')['candidates']
    assert len(table)==3 and 'score' not in table and table.analog_N.gt(0).all()
    assert table.quote_provenance.iloc[0]['short']['observed_at']=='2026-09-23T14:00:00Z'


def test_chain_missing_crossed_duplicate_and_limit():
    f=chain(); f.loc[0,'bid']=np.nan
    trades,rejected=chain_verticals(f,'SPY',100,'2026-09-23')
    assert len(rejected)==1 and len(trades)==1
    f=chain(); f.loc[0,'bid']=10
    assert len(chain_verticals(f,'SPY',100,'2026-09-23')[1])==1
    with pytest.raises(ValueError): chain_verticals(pd.concat([chain(),chain().tail(1)]),'SPY',100,'2026-09-23')
    with pytest.raises(ValueError): chain_verticals(chain(),'SPY',100,'2026-09-23',max_candidates=1)


def app_script():
    return "from modules.phase6_workspace import render_phase6; render_phase6()"


def test_ui_manual_submit_and_stale_research():
    app=AppTest.from_string(app_script(),default_timeout=60)
    state={}; save_research_session(state,history=history(),symbol='SPY',period='fixture')
    app.session_state['quant_research_session']=state['quant_research_session']
    app.run(); assert not app.exception
    next(b for b in app.button if b.label=='Run integrated trade research').click().run()
    assert not app.exception
    assert 'phase6_result' in app.session_state
    assert 'Historical touch / breach frequency' in [m.label for m in app.metric]
    assert len(app.get('download_button'))==2
    state['quant_research_session']['metadata']={'changed':True}
    app.session_state['quant_research_session']=state['quant_research_session']; app.run()
    assert not app.exception and not app.metric


def test_ui_saved_call_and_missing_dataset():
    app=AppTest.from_string(app_script(),default_timeout=60).run()
    assert not app.exception and app.info
    state={}; save_research_session(state,history=history(),symbol='SPY',period='fixture')
    app.session_state['quant_research_session']=state['quant_research_session']
    app.session_state['quant_selected_option']=trade(True)
    app.run(); app.selectbox(key='p6_source').set_value('Selected opportunity').run()
    next(b for b in app.button if b.label=='Run integrated trade research').click().run()
    assert not app.exception
    assert 'Historical survival BELOW short strike' in [m.label for m in app.metric]


def test_quant_lab_tab_integration():
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'streamlit_app.py'),default_timeout=60).run()
    app.switch_page('pages/8_Quant_Lab.py').run()
    assert not app.exception
    assert 'Trade Research' in [t.label for t in app.tabs]
