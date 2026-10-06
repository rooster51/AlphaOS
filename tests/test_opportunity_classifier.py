import pandas as pd
import pytest
from modules.opportunity_classifier import classify_opportunity, history_evidence, expected_move_context

NOW='2030-01-02T20:30:00Z'
SESSION={'open':'2030-01-02T14:30:00Z','close':'2030-01-02T21:00:00Z'}

@pytest.mark.parametrize('prices,direction', [([104,103,102,101],'bullish'),([101,102,103,104],'bearish'),([104,102,103,101],'unknown')])
def test_direction(prices,direction):
    row=dict(zip(('close','ema_9','ema_21','ema_50'),prices),date='2030-01-01')
    result=classify_opportunity({'latest':row},observed_at=NOW)
    assert result['direction']==direction
    assert result['evidence']['direction']['observations']['latest']==row


def test_conflicting_breakout():
    row=dict(close=104,ema_9=103,ema_21=102,ema_50=101,date='2030-01-01')
    result=classify_opportunity({'latest':row,'previous':dict(date='2029-12-31',high_20=110,low_20=105)},observed_at=NOW)
    assert result['direction']=='unknown'
    assert result['movement_state']=='unknown'
    assert result['evidence']['direction']['conflicts']


def test_breakout_precedence():
    result=classify_opportunity({'latest':dict(close=104,ema_9=103,ema_21=102,ema_50=101,date='2030-01-01'),
        'previous':dict(date='2029-12-31',high_20=103,low_20=95)},observed_at=NOW)
    assert result['movement_state']=='breakout'

@pytest.mark.parametrize('iv,rv',[(.9,.1),(.1,.9),(.2,.2),(None,None)])
def test_no_uncalibrated_premium_or_volatility_labels(iv,rv):
    result=classify_opportunity({'volatility':{'iv':iv,'realized_vol_20d':rv}})
    assert result['premium_state']==result['volatility_state']=='unknown'
    assert result['movement_state']=='unknown'

@pytest.mark.parametrize('now,expiry,expected',[(NOW,'2030-01-02','late_0dte'),('2030-01-02T15:00:00Z','2030-01-02','standard'),
    (NOW,'2030-01-03','standard'),('2030-01-02T22:00:00Z','2030-01-02','unknown'),(None,'2030-01-02','unknown')])
def test_time(now,expiry,expected):
    assert classify_opportunity(observed_at=now,expiration=expiry,session=SESSION)['time_state']==expected


def test_horizon():
    assert expected_move_context(5,None,NOW,'2030-01-02')[1] is None
    assert expected_move_context(5,{'start':NOW,'end':'2030-01-04T21:00:00Z'},NOW,'2030-01-02')[1] is None
    assert expected_move_context(5,{'start':NOW,'end':SESSION['close']},NOW,'2030-01-02')[1]==5


def test_history_excludes_uncompleted():
    days=pd.bdate_range('2029-09-01','2030-01-03')
    frame=pd.DataFrame(dict(date=days,symbol='QQQ',open=range(100,100+len(days)),close=range(100,100+len(days)),high=range(101,101+len(days)),low=range(99,99+len(days))))
    evidence=history_evidence(frame,'QQQ',NOW)
    assert evidence['latest']['date']<'2030-01-02'
    assert evidence['audit']['excluded_uncompleted']==2
    assert classify_opportunity(evidence,observed_at=NOW)['direction']=='bullish'


def test_public_pipeline(monkeypatch):
    import modules.public_observations as public
    days=pd.bdate_range('2029-09-01','2030-01-01')
    history=pd.DataFrame(dict(date=days,symbol='QQQ',open=range(100,100+len(days)),close=range(100,100+len(days)),high=range(101,101+len(days)),low=range(99,99+len(days))))
    quote={'symbol':'QQQ','last':200,'updated_at':NOW}
    chain={'symbol':'QQQ','expiration':'2030-01-04','calls':[
        dict(type='Call',strike=200,bid=3,ask=3.2,delta=.5,quote_timestamp=NOW),
        dict(type='Call',strike=205,bid=1,ask=1.2,delta=.2,quote_timestamp=NOW)]}
    monkeypatch.setattr(public,'get_public_quotes',lambda symbols:[quote])
    monkeypatch.setattr(public,'get_public_option_chain',lambda *args:chain)
    result=public.research_public_opportunities('QQQ','2030-01-04',observed_at=NOW,history=history,session_context=SESSION)['research_session']
    assert result['opportunity_state']['direction']=='bullish'
    assert result['candidates']
    assert result['comparison']['winner'] is None
    assert result['comparison']['recommendation'] is None


def test_partial_missing_and_mixed_future_quote_sides():
    from modules.public_observations import normalize_public_observations
    quote={'symbol':'QQQ','last':200,'updated_at':NOW}
    row=dict(type='Call',strike=200,bid=1,ask=2,bid_timestamp=NOW,ask_timestamp='2030-01-02T20:31:00Z')
    chain={'symbol':'QQQ','expiration':'2030-01-04','calls':[row]}
    result=normalize_public_observations('QQQ','2030-01-04',quote,chain,observed_at=NOW)
    assert not result['fresh']
    assert 'future_option_quote_timestamp' in result['issues']
    chain['calls']=[dict(type='Call',strike=200,bid=1,ask=2),dict(row,ask_timestamp=NOW)]
    assert not normalize_public_observations('QQQ','2030-01-04',quote,chain,observed_at=NOW)['fresh']
