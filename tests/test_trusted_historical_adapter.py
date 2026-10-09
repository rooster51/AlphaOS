"""Contract tests for the provenance-preserving Phase 3 adapter."""
import pandas as pd
import pytest

from modules.trusted_historical_adapter import build_scenario_evidence


def analog():
    dates = pd.to_datetime(["2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08"])
    matches = pd.DataFrame({
        "date": dates[:2], "symbol": ["QQQ", "QQQ"],
        "close": [100.0, 100.0],
        "future_return_1s": [.02, -.01],
        "future_high_excursion_1s": [.03, .01],
        "future_low_excursion_1s": [-.01, -.02],
        "outcome_known_by_target_1s": [True, True],
    })
    return dict(
        config=dict(symbol="QQQ", horizon=1, method="nearest"),
        target=pd.Series(dict(date=dates[-1], symbol="QQQ", close=100.0)),
        analogs=matches, session_dates=pd.Series(dates),
    )


def kwargs():
    return dict(
        symbol="QQQ", expiration="2026-10-09", anchor_spot=100.0,
        as_of="2026-10-08T20:30:00+00:00",
        observed_at="2026-10-08T20:29:00+00:00",
        max_age_seconds=600, archive_id="fixture-archive",
        archive_checksum="fixture-checksum",
        future_exchange_sessions=["2026-10-09"],
        completed_session_times={
            "2026-10-06": "2026-10-06T20:00:00+00:00",
            "2026-10-07": "2026-10-07T20:00:00+00:00",
        },
        minimum_samples=2,
    )


def test_valid_adapter_and_stable_identity():
    a = build_scenario_evidence(analog(), **kwargs())
    b = build_scenario_evidence(analog(), **kwargs())
    assert a.fingerprint == b.fingerprint
    assert len(a.scenarios) == 2
    assert [s.terminal_return for s in a.scenarios] == [.02, -.01]
    assert "fixture-checksum" in a.source


@pytest.mark.parametrize("changes", [
    {"symbol": "SPY"},
    {"anchor_spot": 99.0},
    {"expiration": "2026-10-12"},
    {"future_exchange_sessions": ["2026-10-09", "2026-10-12"]},
    {"observed_at": "2026-10-08T20:00:00+00:00"},
    {"archive_checksum": ""},
    {"minimum_samples": 3},
    {"completed_session_times": {"2026-10-06": "2026-10-06T20:00:00+00:00"}},
    {"completed_session_times": {
        "2026-10-06": "2026-10-09T20:00:00+00:00",
        "2026-10-07": "2026-10-07T20:00:00+00:00",
    }},
])
def test_reject_invalid_evidence(changes):
    params = kwargs()
    params.update(changes)
    with pytest.raises(ValueError):
        build_scenario_evidence(analog(), **params)


def test_reject_false_maturity_flag():
    data = analog()
    data["analogs"].loc[0, "outcome_known_by_target_1s"] = False
    with pytest.raises(ValueError, match="Insufficient"):
        build_scenario_evidence(data, **kwargs())


def test_does_not_guess_missing_completion_times():
    params = kwargs()
    params["completed_session_times"] = {}
    with pytest.raises(ValueError):
        build_scenario_evidence(analog(), **params)


def test_reject_selection_target_mismatch():
    data = analog()
    data["config"]["target_date"] = "2026-10-07"
    with pytest.raises(ValueError, match="selection target mismatch"):
        build_scenario_evidence(data, **kwargs())


def test_reject_duplicate_historical_sessions():
    data = analog()
    data["session_dates"].iloc[1] = data["session_dates"].iloc[0]
    with pytest.raises(ValueError):
        build_scenario_evidence(data, **kwargs())


def test_provenance_does_not_claim_authentication():
    evidence = build_scenario_evidence(analog(), **kwargs())
    assert evidence.source.startswith("caller-supplied-archive:")


def test_config_key_order_does_not_change_fingerprint():
    a=analog(); b=analog(); b['config']=dict(reversed(list(b['config'].items())))
    assert build_scenario_evidence(a,**kwargs()).fingerprint==build_scenario_evidence(b,**kwargs()).fingerprint


def test_intraday_target_and_false_calendar_rejected():
    p=kwargs();p.update(as_of='2026-10-08T18:00:00Z',observed_at='2026-10-08T17:59:00Z')
    with pytest.raises(ValueError,match='Completed-session'):
        build_scenario_evidence(analog(),**p)
    p=kwargs();p.update(expiration='2026-10-10',future_exchange_sessions=['2026-10-10'])
    with pytest.raises(ValueError,match='NYSE calendar'):
        build_scenario_evidence(analog(),**p)


def test_completion_cannot_precede_actual_exchange_close():
    p=kwargs();p['completed_session_times']['2026-10-06']='2026-10-06T19:00:00Z'
    with pytest.raises(ValueError,match='not matured'):
        build_scenario_evidence(analog(),**p)


def test_thanksgiving_holiday_and_early_close_alignment():
    a=analog(); dates=pd.to_datetime(['2026-11-23','2026-11-24','2026-11-25','2026-11-27'])
    a['session_dates']=pd.Series(dates); a['analogs']['date']=dates[:2];a['target']['date']=dates[-1]
    p=kwargs();p.update(expiration='2026-11-30',as_of='2026-11-27T18:00:00Z',
        observed_at='2026-11-27T17:59:00Z',future_exchange_sessions=['2026-11-30'],
        completed_session_times={'2026-11-24':'2026-11-24T21:00:00Z','2026-11-25':'2026-11-25T21:00:00Z'})
    result=build_scenario_evidence(a,**p)
    assert result.expiration_sessions==1
