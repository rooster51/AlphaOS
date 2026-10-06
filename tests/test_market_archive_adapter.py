from copy import deepcopy
import pytest
from modules.market_archive_adapter import normalize_archive_snapshot
from modules.opportunity_session import research_market_opportunities


def payload():
    observed = "2030-01-02T20:30:00+00:00"
    rows = [
        dict(contract="QQQ300102C00500000", symbol="QQQ", expiration="2030-01-02", type="call",
             strike=500, bid=2.0, ask=2.2, delta=.5, bid_timestamp=observed, ask_timestamp=observed,
             observed_at=observed, rejection_reasons=[], quality_warnings=[]),
        dict(contract="QQQ300102C00505000", symbol="QQQ", expiration="2030-01-02", type="call",
             strike=505, bid=.8, ask=1.0, delta=.2, bid_timestamp=observed, ask_timestamp=observed,
             observed_at=observed, rejection_reasons=[], quality_warnings=[]),
        dict(contract="QQQ300102P00495000", symbol="QQQ", expiration="2030-01-02", type="put",
             strike=495, bid=.35, ask=.40, delta=-.2, bid_timestamp=observed, ask_timestamp=observed,
             observed_at=observed, rejection_reasons=[], quality_warnings=[]),
        dict(contract="QQQ300102P00490000", symbol="QQQ", expiration="2030-01-02", type="put",
             strike=490, bid=.10, ask=.15, delta=-.1, bid_timestamp=observed, ask_timestamp=observed,
             observed_at=observed, rejection_reasons=[], quality_warnings=[]),
    ]
    return {
        "schema_version": "intraday-archive-v1", "provider": "Public", "symbol": "QQQ",
        "session": "2030-01-02", "observed_at": observed,
        "underlying": {"last": 500, "last_timestamp": observed},
        "options": {"schema_version": "options-archive-v1", "symbol": "QQQ",
            "snapshot_date": "2030-01-02", "status": "complete",
            "quote_timing": "last_available_not_guaranteed_close",
            "requested_expirations": ["2030-01-02"], "expiration_failures": [],
            "valid_contracts": rows, "questionable_contracts": [], "rejected_contracts": []},
    }


def test_archive_adapter_normalizes_one_expiration_without_interpretation():
    result = normalize_archive_snapshot(payload(), "2030-01-02")
    assert result["symbol"] == "QQQ"
    assert result["market_research"]["spot"] == 500
    assert len(result["chain"]["calls"]) == 2
    assert len(result["chain"]["puts"]) == 2
    assert result["chain"]["puts"][0]["type"] == "Put"
    assert result["market_research"].get("opportunity_state") is None


def test_archive_snapshot_can_drive_existing_opportunity_session():
    archived = normalize_archive_snapshot(payload(), "2030-01-02")
    market = dict(archived["market_research"],
                  opportunity_state={"direction": "bullish", "premium_state": "rich",
                                     "movement_state": "breakout", "time_state": "late_0dte"})
    result = research_market_opportunities(
        "QQQ", market, archived["chain"], as_of=archived["observed_at"],
        expiration=archived["expiration"], available_capital=500, width=5,
    )
    families = {x["strategy_family"] for x in result["candidates"]}
    assert "call_debit_spread" in families
    assert "put_credit_spread" in families
    assert result["comparison"]["winner"] is None
    assert result["comparison"]["recommendation"] is None


def test_quality_and_actual_timestamps_survive_without_imputed_quote_time():
    p = payload()
    p['slot_time'] = '2030-01-02T20:25:00+00:00'
    p['collection_finished_at'] = '2030-01-02T20:32:00+00:00'
    row = p['options']['valid_contracts'].pop(0)
    row.update(bid_timestamp=None, ask_timestamp=None, quality_warnings=['bid_timestamp_missing'])
    p['options']['questionable_contracts'] = [row]
    rejected = dict(row, contract='rejected', rejection_reasons=['crossed_bid_ask'])
    p['options']['rejected_contracts'] = [rejected]
    before = deepcopy(p)
    result = normalize_archive_snapshot(p)
    question = next(x for x in result['chain']['calls'] if x['strike'] == 500)
    assert question['quote_timestamp'] is None
    assert question['observation_timestamp'] == row['observed_at']
    assert question['quality_warnings'] == ['bid_timestamp_missing']
    assert result['excluded'][0]['contract'] == 'rejected'
    obs = result['market_research']['archive_observation']
    assert obs['slot_time'] == p['slot_time']
    assert obs['collection_finished_at'] == p['collection_finished_at']
    assert p == before


@pytest.mark.parametrize('field,value', [('symbol', 'SPY'), ('bid_timestamp', '2030-01-02T21:00:00Z'),
                                       ('observed_at', 'bad'), ('rejection_reasons', ['invalid'])])
def test_invalid_contract_never_promoted(field, value):
    p = payload()
    p['options']['valid_contracts'][0][field] = value
    result = normalize_archive_snapshot(p)
    assert len(result['chain']['calls']) == 1
    assert result['excluded'][0]['reason'] == 'invalid_archive_contract'


def test_failed_expiration_not_researchable():
    p = payload()
    p['options']['expiration_failures'] = [{'expiration': '2030-01-02', 'reason': 'chain_retrieval_failed'}]
    result = normalize_archive_snapshot(p)
    assert result['chain']['calls'] == result['chain']['puts'] == []
    assert result['market_research']['archive_observation']['expiration_failures']


def test_new_york_session_date_used_for_offset_timestamp():
    p = payload()
    p['observed_at'] = '2030-01-03T01:30:00+05:00'  # Same instant as fixture.
    assert normalize_archive_snapshot(p)['session_date'] == '2030-01-02'
