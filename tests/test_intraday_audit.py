from scripts.audit_intraday_capabilities import summarize

def test_bar_audit_reports_actual_spacing_not_requested_resolution():
    bars=[dict(timestamp=t,open=1,high=2,low=1,close=2,volume=0) for t in ['2026-10-01T13:30:00Z','2026-10-01T14:30:00Z']]
    result=summarize(dict(symbol='XSP-INDEX',regularMarket=dict(bars=bars,expectedBars=2)))['sessions']['regularMarket']
    assert result['common_interval_minutes']==[(60.0,1)]
    assert result['positive_volume']==0 and result['date_count']==1
    assert result['local_times']==['09:30','10:30']
