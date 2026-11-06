from datetime import datetime, timedelta, timezone
from threading import Event, Thread
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from alphaos_api.app import app
from alphaos_api.contracts import APIError
from alphaos_api.live_options import scenario
from alphaos_api.service import ResearchService
from modules.public_provider import PublicProviderError

NOW = datetime(2026, 11, 4, 16, 0, tzinfo=timezone.utc)
EXPIRATION = "2026-11-06"


def leg(symbol="SPY", right="C", strike=500, bid=2.0, ask=2.1, **changes):
    return dict(contract=f"{symbol}261106{right}{strike * 1000:08d}",
        strike=strike, bid=bid, ask=ask, bid_timestamp=NOW.isoformat(),
        ask_timestamp=NOW.isoformat()) | changes


def chain(symbol, expiration, calls=None, puts=None):
    return dict(symbol=symbol, expiration=expiration,
        calls=[leg(symbol)] if calls is None else calls, puts=[] if puts is None else puts)


@pytest.fixture
def provider():
    result = Mock()
    result.expirations.side_effect = lambda symbol: [EXPIRATION] if symbol == "QQQ" else _fail("provider_unavailable")
    result.chain.side_effect = chain
    result.quote.side_effect = lambda symbol: [dict(symbol=symbol, last=501., bid=500.99, ask=501.01,
        provider_outcome="SUCCESS", updated_at=NOW.isoformat(), bid_timestamp=NOW.isoformat(),
        ask_timestamp=NOW.isoformat(), provider_retrieved_at=NOW.isoformat())]
    return result


def _fail(code):
    raise PublicProviderError(code)


def test_authenticated_discovery_and_dated_chain(monkeypatch, provider):
    monkeypatch.setenv("ALPHAOS_API_TOKEN", "synthetic-api-token")
    monkeypatch.setitem(app.state._state, "service", ResearchService(provider, lambda: NOW))
    client = TestClient(app)
    auth = {"Authorization": "Bearer synthetic-api-token"}
    path = f"/v1/options/SPY/chain/{EXPIRATION}"
    assert client.get(path + "?explicit=true").status_code == 401
    provider.chain.assert_not_called()
    assert client.get("/v1/options/SPY/expirations", headers=auth).status_code == 503
    assert client.get(path, headers=auth).status_code == 503
    assert client.get("/v1/options/QQQ/expirations", headers=auth).json()["evidence"]["expirations"] == [EXPIRATION]
    response = client.get(path, params={"explicit":"true", "buy":leg()["contract"]}, headers=auth)
    assert response.status_code == 200
    evidence = response.json()["evidence"]
    assert evidence["source"] == "Public"
    assert evidence["scenario"]["max_loss"] == pytest.approx(210)
    assert evidence["scenario"]["max_profit"] is None
    assert evidence["chain"]["puts"] == []
    assert evidence["chain"]["calls"][0]["delta"] is None
    assert client.get("/v1/quote/QQQ", headers=auth).json()["evidence"]["quote"]["symbol"] == "QQQ"
    assert client.get("/v1/options/SPY/chain/2026-11-03?explicit=true", headers=auth).status_code == 422
    provider.chain.assert_called_once_with("SPY", EXPIRATION)
    assert client.post(path, headers=auth).status_code == 422


@pytest.mark.parametrize(("rows", "status"), [
    ([leg(bid_timestamp=None)], "missing_timestamp"),
    ([leg(ask_timestamp=(NOW-timedelta(seconds=31)).isoformat())], "stale"),
    ([leg(bid=3, ask=2)], "crossed_market"),
    ([leg(ask=float("nan"))], "invalid_price"),
    ([leg(), leg()], "ambiguous_contract"),
    ([leg(outcome="UNKNOWN")], "provider_quote_failure"),
])
def test_partial_quotes_are_display_only(provider, rows, status):
    provider.chain.side_effect = None
    provider.chain.return_value = chain("SPY", EXPIRATION, calls=rows)
    result = ResearchService(provider, lambda: NOW).chain("SPY", EXPIRATION, explicit=True)
    assert result["chain"]["calls"][0]["status"] == status
    assert scenario(result["chain"], rows[0]["contract"], None, 500)["status"] == "unavailable"


@pytest.mark.parametrize("rows", [[], [leg("QQQ")], [leg(contract="SPY261109C00500000")]])
def test_no_identity_evidence_rejected(provider, rows):
    provider.chain.side_effect = None
    provider.chain.return_value = chain("SPY", EXPIRATION, calls=rows)
    with pytest.raises(APIError, match="unverified_option_chain"):
        ResearchService(provider, lambda: NOW).chain("SPY", EXPIRATION, explicit=True)


@pytest.mark.parametrize(("right", "buy_strike", "sell_strike", "buy_ask", "sell_bid", "net", "gain", "loss", "root"), [
    ("C", 500, 505, 3, 1, -200, 300, 200, 502),
    ("P", 505, 500, 3, 1, -200, 300, 200, 503),
    ("C", 505, 500, 1, 3, 200, 200, 300, 502),
    ("P", 500, 505, 1, 3, 200, 200, 300, 503),
])
def test_vertical_uses_ask_and_bid(provider, right, buy_strike, sell_strike, buy_ask, sell_bid, net, gain, loss, root):
    buy = leg(right=right, strike=buy_strike, bid=buy_ask-.2, ask=buy_ask)
    sell = leg(right=right, strike=sell_strike, bid=sell_bid, ask=sell_bid+.2)
    provider.chain.side_effect = lambda symbol, expiration: chain(symbol, expiration,
        calls=[buy, sell] if right=="C" else [], puts=[buy, sell] if right=="P" else [])
    result = ResearchService(provider, lambda: NOW).chain("SPY", EXPIRATION, explicit=True)
    output = scenario(result["chain"], buy["contract"], sell["contract"], 500)
    assert output["status"] == "available"
    assert (output["net_cash"], output["max_profit"], output["max_loss"], output["width"]) == (net, gain, loss, 5)
    assert output["breakevens"] == pytest.approx([root])


def test_slow_spy_request_does_not_hold_qqq_cache(provider):
    started, release = Event(), Event()

    def load(symbol, expiration):
        if symbol == "SPY":
            started.set()
            release.wait(3)
        return chain(symbol, expiration)

    provider.chain.side_effect = load
    service = ResearchService(provider, lambda: NOW)
    spy = Thread(target=service.chain, args=("SPY", EXPIRATION), kwargs={"explicit":True})
    spy.start()
    try:
        assert started.wait(1)
        assert service.chain("QQQ", EXPIRATION, explicit=True)["chain"]["symbol"] == "QQQ"
        assert spy.is_alive()
    finally:
        release.set()
        spy.join()


def test_slow_spy_underlying_does_not_block_qqq(provider):
    started, release = Event(), Event()
    underlying = provider.quote.side_effect

    def load(symbol):
        if symbol == "SPY":
            started.set()
            release.wait(3)
        return underlying(symbol)

    provider.quote.side_effect = load
    service = ResearchService(provider, lambda: NOW)
    spy = Thread(target=service.quote, args=("SPY", True))
    spy.start()
    try:
        assert started.wait(1)
        assert service.quote("QQQ", True)["quote"]["symbol"] == "QQQ"
        assert spy.is_alive()
    finally:
        release.set()
        spy.join()


def test_timeout_has_no_cached_price_fallback(provider):
    service = ResearchService(provider, lambda: NOW)
    service.chain("SPY", EXPIRATION, explicit=True)
    provider.chain.side_effect = TimeoutError
    with pytest.raises(APIError, match="provider_timeout"):
        service.chain("SPY", EXPIRATION, refresh=True, explicit=True)
