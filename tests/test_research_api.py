from fastapi.testclient import TestClient
from alphaos_api.app import app

client = TestClient(app)


def test_health_is_read_only():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["read_only"] is True


def test_rejects_unknown_symbol_without_provider_call():
    r = client.get("/v1/market/IWM")
    assert r.status_code == 400


def test_openapi_exposes_research_surface():
    paths = client.get("/openapi.json").json()["paths"]
    assert "/v1/market/{symbol}" in paths
    assert "/v1/quote/{symbol}" in paths
    assert "/v1/options/{symbol}/expirations" in paths
    assert "/v1/options/{symbol}/chain/{expiration}" in paths
    assert "/v1/options/{symbol}/vertical" in paths
    assert "/v1/structure/{symbol}" in paths
    assert "/v1/distribution/{symbol}" in paths
    assert "/v1/trade/research" in paths
    assert "/v1/trade/compare" in paths
    assert not any("order" in p.lower() for p in paths)
