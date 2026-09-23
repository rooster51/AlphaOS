from copy import deepcopy
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch
import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from modules.market_state_research import build_research_dataset
from modules.selector_research import (build_scan_research,context_from_dataset,annotate_candidates,
    structural_position,select_candidate,valid_saved_snapshot,research_columns)
from modules.threshold_survival import threshold_research
from modules.premium_engine import demo_chain,generate


def dataset():
    n=260;p=500+10*np.sin(np.arange(n)/6)
    return build_research_dataset(pd.DataFrame(dict(date=pd.bdate_range('2020-01-02',periods=n),symbol='SPY',
        open=p,high=p+2,low=p-2,close=p)),'2022-01-01',dict(source='fixture',data_read_at='2026-09-23T12:00:00Z'))


def candidates():
    return generate(demo_chain(35),500,35/365,.25)


def snapshot(h=3):
    return context_from_dataset(dataset(),500,h,'2026-09-23T13:00:00Z','2026-09-23T13:01:00Z')


def selected_state(h=3):
    snap=snapshot(h); rows=annotate_candidates(candidates(),snap,'SPY')
    index=next(i for i,r in enumerate(rows) if r['strategy']=='Bull put spread')
    result=dict(rows=rows,symbol='SPY',source='Public · connected quotes',quote_time=snap['quote_timestamp'],
        fetched=snap['scan_retrieved_at'],research_snapshot=snap)
    state={};selected=select_candidate(state,result,index)
    return state,selected,result


def test_single_history_and_sample_reused_across_candidates():
    loader=Mock(return_value=dataset())
    from modules.selector_research import analog_research
    with patch('modules.selector_research.analog_research',wraps=analog_research) as analog:
        snap=build_scan_research('SPY',500,3,'quote','read',loader=loader)
        rows=candidates(); rows+=deepcopy(rows[:2])
        with patch('modules.selector_research.threshold_research',wraps=threshold_research) as thresholds:
            output=annotate_candidates(rows,snap,'SPY')
        assert analog.call_count==1
    loader.assert_called_once_with('SPY','FIVE_YEARS')
    keys={(r['legs'][0]['type'],r['research_context']['short_strike']) for r in output if r.get('research_context')}
    assert thresholds.call_count==len(keys)
    assert len(output)==len(rows)


@pytest.mark.parametrize('side',['support','resistance'])
@pytest.mark.parametrize('strike,position',[(98,'BELOW'),(99,'INSIDE'),(100,'INSIDE'),(101,'INSIDE'),(102,'ABOVE')])
def test_zone_boundaries(side,strike,position):
    zone=dict(zone_low=99.,level=100.,zone_high=101.)
    assert structural_position(strike,zone,side)==position+' '+side.upper()
    assert structural_position(99.-1e-14,zone,side)=='INSIDE '+side.upper()
    assert structural_position(strike,None,side) is None


def test_multiple_strikes_directions_and_spot_bridge():
    snap=snapshot(); output=annotate_candidates(candidates(),snap,'SPY')
    assert snap['research_close']!=500
    for row in output:
        c=row.get('research_context')
        if not c:
            assert all(v is None for v in research_columns(row).values()); continue
        mode='put' if row['strategy']=='Bull put spread' else 'call'
        bridge={**snap['analog'],'target':dict(snap['analog']['target'])};bridge['target']['close']=500
        expected=threshold_research(bridge,mode,3,threshold_price=c['short_strike'],allow_opposite=True)['summary']
        assert c['threshold_statistics']==expected
        assert c['strike_distance_pct']==pytest.approx(c['short_strike']/500-1)
        if c['nearest_zone']:
            assert c['structural_position'].endswith('SUPPORT' if mode=='put' else 'RESISTANCE')
    assert any(r.get('research_context') for r in output)


def test_selection_transfer_preserves_snapshot_and_credit():
    state,t,result=selected_state(5)
    assert valid_saved_snapshot(t,state['quant_selected_research'])
    assert t['research_context']['horizon']==5
    assert t['quote_timestamp']=='2026-09-23T13:00:00Z'
    assert state['quant_research_session']['symbol']=='SPY'
    original=deepcopy(result['research_snapshot'])
    state['quant_selected_research']['current_spot']=123
    assert result['research_snapshot']['current_spot']==original['current_spot']
    assert not valid_saved_snapshot(t,state['quant_selected_research'])


@pytest.mark.parametrize('field,value',[('spot',501),('credit',.1),('expiration','2031-01-01'),('symbol','QQQ')])
def test_changed_candidate_invalidates_context(field,value):
    state,t,_=selected_state();t[field]=value
    assert not valid_saved_snapshot(t,state['quant_selected_research'])


def test_future_outcomes_do_not_change_asof_thresholds():
    data=dataset(); cutoff=data['features'].date.iloc[230]
    bars=data['features'][['date','symbol','open','high','low','close']].copy()
    before=build_research_dataset(bars,cutoff)
    bars.loc[bars.date>=cutoff,['open','high','low','close']]*=3
    after=build_research_dataset(bars,cutoff)
    first=annotate_candidates(candidates(),context_from_dataset(before,500,3,'q','r'),'SPY')
    second=annotate_candidates(candidates(),context_from_dataset(after,500,3,'q','r'),'SPY')
    assert [r.get('research_context') for r in first]==[r.get('research_context') for r in second]


def test_quant_defaults_horizon_credit_and_snapshot_without_fetch():
    state,t,_=selected_state(5)
    app=AppTest.from_string('from modules.phase6_workspace import render_phase6; render_phase6()',default_timeout=60)
    for k,v in state.items(): app.session_state[k]=v
    with patch('modules.phase6_workspace.load_market_state') as loader:
        app.run()
        assert not app.exception
        assert app.selectbox(key='p6_source').value=='Selected Strategy Selector candidate'
        assert next(s for s in app.selectbox if s.label=='Trade Research observed-session horizon').value==5
        assert next(n for n in app.number_input if n.label=='Credit per share for entered spread').value==t['credit']
        next(b for b in app.button if b.label=='Run integrated trade research').click().run()
        assert not app.exception
        assert app.session_state['phase6_result']['result']['trade']['credit']==t['credit']
        loader.assert_not_called()


def test_explicit_refresh_keeps_original_snapshot():
    state,t,_=selected_state();old=deepcopy(t)
    app=AppTest.from_string('from modules.phase6_workspace import render_phase6; render_phase6()',default_timeout=60)
    for k,v in state.items(): app.session_state[k]=v
    app.run()
    new=dataset();new['metadata']['data_read_at']='2026-09-23T16:00:00Z'
    with patch('modules.phase6_workspace.load_market_state',return_value=new) as loader:
        app.button(key='p6_refresh_button').click().run()
        loader.assert_called_once_with('SPY','FIVE_YEARS')
    assert not app.exception
    assert app.session_state['quant_selected_option']==old
    assert any('Candidate snapshot:' in c.value for c in app.caption)
    assert any('Refreshed research:' in c.value for c in app.caption)


def test_invalid_context_requires_refresh_and_manual_remains():
    state,t,_=selected_state();t['spot']=501
    app=AppTest.from_string('from modules.phase6_workspace import render_phase6; render_phase6()',default_timeout=60)
    for k,v in state.items():app.session_state[k]=v
    app.run();assert not app.exception
    assert any('does not match' in w.value for w in app.warning)
    assert not any(b.label=='Run integrated trade research' for b in app.button)
    app.selectbox(key='p6_source').set_value('Enter a vertical').run()
    next(b for b in app.button if b.label=='Run integrated trade research').click().run()
    assert not app.exception and 'phase6_result' in app.session_state


def test_demo_scanner_preserves_columns_ranking_and_nonverticals():
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'streamlit_app.py'),default_timeout=60).run()
    next(b for b in app.button if b.label=='Find premium trades →').click().run()
    assert not app.exception
    r=app.session_state['premium_result']
    assert len(r['rows'])>0 and r['research_snapshot'] is None
    assert any(len(row['legs'])>2 for row in r['rows'])
    assert r['rows']==sorted(r['rows'],key=lambda row:(row['short_distance'],-row['net_credit']))
    table=next(d.value for d in app.dataframe if 'Est. POP' in d.value.columns)
    assert {'Est. POP','Net credit / unit ($)','Historical terminal survival','Research N'}<=set(table)


def test_public_scan_fetches_once_and_history_failure_preserves_candidates():
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'streamlit_app.py'),default_timeout=60).run()
    next(r for r in app.radio if r.label=='Market data').set_value('Public · connected quotes').run()
    chain=demo_chain(35)
    with patch('modules.public_data.get_public_quotes',return_value=[dict(symbol='SPY',last=500,updated_at='quote-time')]), \
         patch('modules.public_data.get_public_option_expirations',return_value=[chain['expiration']]), \
         patch('modules.public_data.get_public_option_chain',return_value=chain), \
         patch('modules.selector_research.load_market_state',return_value=dataset()) as loader:
        next(b for b in app.button if b.label=='Find premium trades →').click().run()
        assert not app.exception
        loader.assert_called_once_with('SPY','FIVE_YEARS')
        assert app.session_state['premium_result']['research_snapshot']
        assert any(m.label=='Research close' for m in app.metric)
        loader.side_effect=ValueError('provider failure')
        next(b for b in app.button if b.label=='Find premium trades →').click().run()
        assert not app.exception
        assert app.session_state['premium_result']['rows']
        assert app.session_state['premium_result']['research_snapshot'] is None
        assert any('unavailable for this scan' in w.value for w in app.warning)


def test_deep_research_reuses_saved_primary_and_default_population():
    from modules.phase6_research import research_workspace, analog_research
    state,t,_=selected_state(5);snap=state['quant_selected_research']
    with patch('modules.phase6_research.analog_research',wraps=analog_research) as match:
        r=research_workspace(state['quant_research_session']['history'],t,'2026-09-24',horizon=5,prepared=snap)
    assert match.call_count==7  # Four other horizons, Tight, Wide, Nearest 50; no duplicated default.
    assert r['primary'] is snap['analog']
    assert r['evidence']['threshold']['summary']==t['research_context']['threshold_statistics']


def test_selection_button_navigates_with_full_saved_candidate():
    import streamlit as st
    from types import SimpleNamespace
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'streamlit_app.py'),default_timeout=60).run()
    state,t,result=selected_state(5)
    # Reuse the actual submitted-scan schema; emulate Streamlit's single-row event.
    result.update(source='Public · connected quotes',ranking='Nearest short strikes',scope='fixture',spot=500,
        errors=[],research_horizon=5)
    for row in result['rows']: row.update(iv=.25,dte=35)
    app.session_state['premium_result']=result
    app.session_state['premium_scan_version']=1
    next(r for r in app.radio if r.label=='Market data').set_value('Public · connected quotes')
    selected=next(i for i,row in enumerate(result['rows']) if row['strategy']=='Bull put spread')
    original=st.dataframe
    def selection_event(data,*args,**kwargs):
        displayed=original(data,*args,**kwargs)
        return SimpleNamespace(selection=SimpleNamespace(rows=[selected])) if kwargs.get('selection_mode')=='single-row' else displayed
    with patch('streamlit.dataframe',side_effect=selection_event):
        app.run()
        assert not app.exception
        next(b for b in app.button if b.label=='Research selected trade in Quant Lab →').click().run()
    assert not app.exception
    assert app.tabs[0].label=='Trade Research'
    assert app.selectbox(key='p6_source').value=='Selected Strategy Selector candidate'
    assert next(s for s in app.selectbox if s.label=='Trade Research observed-session horizon').value==5
    assert valid_saved_snapshot(app.session_state['quant_selected_option'],app.session_state['quant_selected_research'])
