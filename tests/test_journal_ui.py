from unittest.mock import Mock
import httpx
from streamlit.testing.v1 import AppTest
from alphaos_api.journal import TradeJournal,JournalFilters
from test_positions import position_db
from test_journal import store,seed,close,observe
from modules.trade_journal_workspace import journal_table,timeline_table


def test_helpers_keep_estimate_separate_and_timeline_quoted(store):
    p=seed(store);observe(store,p,30);close(store,p,.07,exit_basis='estimated')
    journal=TradeJournal(store)
    row=journal_table(journal.journal(JournalFilters())['trades'])[0]
    assert row['Actual P/L'] is None and row['Estimated exit P/L'] is not None
    rows=timeline_table(journal.review(p['position_id'])['monitoring_timeline'])
    assert len(rows)==1 and rows[0]['Estimated P/L']==30


def test_streamlit_journal_empty_and_filled(store,monkeypatch):
    monkeypatch.setenv('ALPHAOS_API_TOKEN','fixture-secret')
    monkeypatch.setenv('ALPHAOS_PUBLIC_URL','https://alphaos.example')
    j=TradeJournal(store)
    def request(method,url,**kwargs):
        assert method=='GET'
        if url.endswith('/v1/positions'):data=dict(positions=[])
        elif url.endswith('/performance'):data=j.performance(JournalFilters(),kwargs.get('params',{}).get('group_by'))
        else:data=j.journal(JournalFilters())
        return httpx.Response(200,json=data)
    mock=Mock(side_effect=request);monkeypatch.setattr(httpx,'request',mock)
    app=AppTest.from_string('from modules.active_trades_workspace import render_active_trades; render_active_trades()',default_timeout=30).run()
    next(r for r in app.radio if r.label=='Workspace').set_value('Trade journal / performance').run()
    assert not app.exception
    assert any('No closed trades' in i.value for i in app.info)
    assert all(m.value=='Unavailable' for m in app.metric)
    close(store,seed(store))
    app.run()
    assert not app.exception and app.dataframe
    assert any(m.value=='56.00' for m in app.metric)
    assert all(call.args[0]=='GET' for call in mock.call_args_list)
