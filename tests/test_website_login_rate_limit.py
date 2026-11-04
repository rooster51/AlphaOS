"""Shared Supabase login limiter API tests; synthetic credentials only."""
import asyncio
import importlib
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from alphaos_api import website_rate_limit
from alphaos_api.contracts import APIError

api = importlib.import_module("alphaos_api.app")
PATH = "/v1/website-auth/rate-limit"


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def aiter_bytes(self):
        yield self.body


class FakeClient:
    response = None
    error = None
    request = None

    def __init__(self, **kwargs):
        self.headers = kwargs["headers"]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    def stream(self, method, url, json):
        type(self).request = (method, str(url), json, self.headers)
        if type(self).error is not None:
            raise type(self).error
        return type(self).response


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://supabase.example")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "synthetic-supabase-service-key")
    monkeypatch.setattr(website_rate_limit.httpx, "AsyncClient", FakeClient)
    FakeClient.error = None
    FakeClient.request = None


def test_authenticated_rpc_uses_service_role_and_accepts_only_strict_decisions(configured):
    for decision in (
        {"allowed": True, "retry_after_seconds": 0},
        {"allowed": False, "retry_after_seconds": 17},
    ):
        FakeClient.response = FakeResponse(200, json.dumps([decision]).encode())
        assert asyncio.run(website_rate_limit.consume_website_login_attempt()) == decision
        method, url, payload, headers = FakeClient.request
        assert method == "POST"
        assert url == "https://supabase.example/rest/v1/rpc/consume_website_login_attempt"
        assert payload == {}
        assert headers["apikey"] == "synthetic-supabase-service-key"
        assert headers["Authorization"] == "Bearer synthetic-supabase-service-key"


@pytest.mark.parametrize("url", [
    "",
    "http://supabase.example",
    "https://user:password@supabase.example",
    "https://supabase.example/path",
    "https://supabase.example:invalid",
    "https://supabase.example?key=private",
    "https://supabase.example/#fragment",
])
def test_invalid_or_missing_supabase_configuration_fails_closed(configured, monkeypatch, url):
    monkeypatch.setenv("SUPABASE_URL", url)
    with pytest.raises(APIError) as exc:
        asyncio.run(website_rate_limit.consume_website_login_attempt())
    assert exc.value.status == 503


@pytest.mark.parametrize("status,body", [
    (307, b"redirect"),
    (401, b"unauthorized"),
    (503, b"database unavailable"),
    (200, b"not-json"),
    (200, b"[]"),
    (200, b'[{"allowed":"true","retry_after_seconds":0}]'),
    (200, b'[{"allowed":false,"retry_after_seconds":0}]'),
    (200, b'[{"allowed":true,"retry_after_seconds":1}]'),
    (200, b'[{"allowed":true,"retry_after_seconds":0,"secret":"no"}]'),
    (200, b"x" * 513),
])
def test_untrusted_or_failed_rpc_responses_fail_closed(configured, status, body):
    FakeClient.response = FakeResponse(status, body)
    with pytest.raises(APIError) as exc:
        asyncio.run(website_rate_limit.consume_website_login_attempt())
    assert exc.value.status == 503
    assert "synthetic-supabase-service-key" not in str(exc.value)


def test_rpc_network_failure_fails_closed(configured):
    FakeClient.error = httpx.ConnectError("private connection details")
    with pytest.raises(APIError) as exc:
        asyncio.run(website_rate_limit.consume_website_login_attempt())
    assert exc.value.status == 503
    assert "private connection details" not in str(exc.value)


def test_render_endpoint_requires_service_bearer_before_supabase(configured, monkeypatch):
    monkeypatch.setenv("ALPHAOS_API_TOKEN", "synthetic-api-token")
    client = TestClient(api.app)
    response = client.post(PATH)
    assert response.status_code == 401
    assert FakeClient.request is None

def test_render_endpoint_returns_fail_closed_status_and_safe_success(configured, monkeypatch):
    monkeypatch.setenv("ALPHAOS_API_TOKEN", "synthetic-api-token")
    client = TestClient(api.app)
    headers = {"Authorization": "Bearer synthetic-api-token"}
    FakeClient.response = FakeResponse(503, b"private backend credentials")
    failed = client.post(PATH, headers=headers)
    assert failed.status_code == 503
    assert "synthetic" not in failed.text

    FakeClient.response = FakeResponse(200, b'[{"allowed":true,"retry_after_seconds":0}]')
    success = client.post(PATH, headers=headers)
    assert success.status_code == 200
    assert success.json() == {"allowed": True, "retry_after_seconds": 0}
    assert success.headers["cache-control"] == "no-store"
