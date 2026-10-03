from modules.public_intraday import fetch_intraday_bars


class _Auth:
    def refresh_token_if_needed(self):
        return None


class _Api:
    def __init__(self, payload):
        self.payload = payload
        self.path = None

    def get(self, path):
        self.path = path
        return self.payload


class _Client:
    def __init__(self, payload):
        self.auth_manager = _Auth()
        self.api_client = _Api(payload)


class _Provider:
    def __init__(self, payload):
        self.client = _Client(payload)


def test_one_minute_public_route_and_normalization():
    payload = {
        "symbol": "QQQ",
        "period": "DAY",
        "regularMarket": {
            "bars": [{
                "timestamp": "2026-10-02T13:30:00Z",
                "open": 600, "high": 601, "low": 599,
                "close": 600.5, "volume": 12345,
            }]
        },
    }
    provider = _Provider(payload)
    rows = fetch_intraday_bars(provider, "QQQ", "ONE_MINUTE")
    assert provider.client.api_client.path == (
        "/userapigateway/historicdata/EQUITY/QQQ/DAY/ONE_MINUTE"
    )
    assert len(rows) == 1
    assert rows[0]["symbol"] == "QQQ"
    assert rows[0]["aggregation"] == "ONE_MINUTE"
    assert rows[0]["close"] == 600.5
    assert rows[0]["volume"] == 12345.0


def test_incomplete_bar_is_not_fabricated():
    payload = {
        "symbol": "SPY",
        "regularMarket": {
            "bars": [{
                "timestamp": "2026-10-02T13:30:00Z",
                "open": 700, "high": 701, "low": 699,
                "close": None, "volume": 100,
            }]
        },
    }
    rows = fetch_intraday_bars(_Provider(payload), "SPY", "ONE_MINUTE")
    assert rows == []
