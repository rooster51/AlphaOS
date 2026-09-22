import pandas as pd
import pytest

from modules.option_scenario_ev import scenario_economics


def analog_result(returns, spot=100.0, symbol='QQQ'):
    dates=pd.date_range('2026-01-02',periods=len(returns)+5,freq='B')
    rows=[]
    for i,r in enumerate(returns):
        rows.append(dict(date=dates[i],symbol=symbol,close=90+i,
            future_return_1s=r,future_return_2s=r,future_return_3s=r,
            future_return_5s=r,future_return_10s=r,
            outcome_known_by_target_1s=True,outcome_known_by_target_2s=True,
            outcome_known_by_target_3s=True,outcome_known_by_target_5s=True,
            outcome_known_by_target_10s=True))
    return dict(target=pd.Series(dict(date=dates[-1],symbol=symbol,close=spot)),
        analogs=pd.DataFrame(rows),session_dates=pd.Series(dates),target_index=len(dates)-1,
        config=dict(method='tolerance',target_date=str(dates[-1].date()),horizon=3))


def pcs(spot=100.0,credit=.20,fees=0.0):
    return dict(symbol='QQQ',strategy='Bull put spread',expiration='2026-01-30',source='Manual entry',
        spot=spot,stock_basis=spot,shares=0,fees=fees,credit=credit,
        legs=[dict(type='Put',strike=99.,qty=-1),dict(type='Put',strike=98.,qty=1)])


def ccs(spot=100.0,credit=.20):
    return dict(symbol='QQQ',strategy='Bear call spread',expiration='2026-01-30',source='Manual entry',
        spot=spot,stock_basis=spot,shares=0,fees=0.,credit=credit,
        legs=[dict(type='Call',strike=101.,qty=-1),dict(type='Call',strike=102.,qty=1)])


def test_pcs_full_partial_and_max_loss_scenarios():
    result=scenario_economics(analog_result([.02,-.005,-.015,-.03]),pcs(),3)
    pnl=result['observations'].gross_expiration_pnl.tolist()
    assert pnl[0] == pytest.approx(20)
    assert pnl[1] == pytest.approx(20)
    assert pnl[2] == pytest.approx(-30)
    assert pnl[3] == pytest.approx(-80)
    assert result['trade_analysis']['max_loss'] == pytest.approx(80)


def test_ccs_full_partial_and_max_loss_scenarios():
    result=scenario_economics(analog_result([-.02,.005,.015,.03]),ccs(),3)
    assert result['observations'].gross_expiration_pnl.tolist() == pytest.approx([20,20,-30,-80])


def test_expected_payoff_and_frequencies_are_arithmetic_scenario_results():
    result=scenario_economics(analog_result([.02,-.005,-.015,-.03]),pcs(),3)
    s=result['gross_summary']
    assert s['expected_payoff'] == pytest.approx(-17.5)
    assert s['median_payoff'] == pytest.approx(-5)
    assert s['positive_frequency'] == pytest.approx(.5)
    assert s['negative_frequency'] == pytest.approx(.5)
    assert s['expected_payoff_on_max_risk'] == pytest.approx(-17.5/80)
    assert s['average_winner'] == pytest.approx(20)
    assert s['average_loser'] == pytest.approx(-55)
    assert s['profit_factor'] == pytest.approx(40/110)


def test_extra_friction_is_separate_from_existing_trade_fees():
    trade=pcs(fees=1.30)
    result=scenario_economics(analog_result([.02]),trade,3,commission_per_contract=.65,entry_slippage=1.,terminal_friction=2.)
    row=result['observations'].iloc[0]
    assert row.gross_expiration_pnl == pytest.approx(18.70)
    assert row.modeled_extra_friction == pytest.approx(4.30)
    assert row.net_expiration_pnl == pytest.approx(14.40)
    assert result['friction']['existing_trade_fees'] == pytest.approx(1.30)


def test_units_scale_payoff_and_friction():
    result=scenario_economics(analog_result([.02]),pcs(),3,units=2,commission_per_contract=.50)
    row=result['observations'].iloc[0]
    assert row.gross_expiration_pnl == pytest.approx(40)
    assert row.modeled_extra_friction == pytest.approx(2)
    assert row.net_expiration_pnl == pytest.approx(38)


def test_missing_or_unknown_outcomes_are_excluded():
    data=analog_result([.02,-.02])
    data['analogs'].loc[0,'future_return_3s']=float('nan')
    data['analogs'].loc[1,'outcome_known_by_target_3s']=False
    result=scenario_economics(data,pcs(),3)
    assert result['net_summary']['n'] == 0
    assert result['net_summary']['expected_payoff'] is None


def test_symbol_and_spot_must_match_point_in_time_research():
    with pytest.raises(ValueError,match='symbol'):
        scenario_economics(analog_result([.01],symbol='SPY'),pcs(),3)
    with pytest.raises(ValueError,match='spot'):
        scenario_economics(analog_result([.01],spot=101),pcs(),3)


def test_target_date_or_future_analog_is_rejected():
    data=analog_result([.01])
    data['analogs'].loc[0,'date']=data['target']['date']
    with pytest.raises(ValueError,match='strictly before'):
        scenario_economics(data,pcs(),3)


def test_invalid_horizon_and_friction_rejected():
    with pytest.raises(ValueError):
        scenario_economics(analog_result([.01]),pcs(),4)
    with pytest.raises(ValueError):
        scenario_economics(analog_result([.01]),pcs(),3,entry_slippage=-1)
