from unittest.mock import Mock
import httpx
from streamlit.testing.v1 import AppTest


def test_tracking_page_empty_and_form_validation(monkeypatch):
    monkeypatch.setenv('ALPHAOS_API_TOKEN','test-tracking-secret')
    request=Mock(return_value=httpx.Response(200,json=dict(positions=[])))
    monkeypatch.setattr(httpx,'request',request)
    app=AppTest.from_string('from modules.active_trades_workspace import render_active_trades; render_active_trades()',default_timeout=30).run()
    assert not app.exception
    assert any('No active' in item.value for item in app.info)
    next(b for b in app.button if b.label=='Record entry').click().run()
    assert not app.exception
    assert all(call.args[0]=='GET' for call in request.call_args_list)
    assert 'test-tracking-secret' not in str([x.value for x in app.text_input])


def test_tracking_ui_rejects_insecure_destination(monkeypatch):
    monkeypatch.setenv('ALPHAOS_API_TOKEN','test-tracking-secret')
    monkeypatch.setenv('ALPHAOS_PUBLIC_URL','http://example.com')
    request=Mock();monkeypatch.setattr(httpx,'request',request)
    app=AppTest.from_string('from modules.active_trades_workspace import render_active_trades; render_active_trades()').run()
    assert not app.exception and app.error
    request.assert_not_called()
