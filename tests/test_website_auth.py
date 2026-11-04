"""Synthetic credentials only; exercise the real bearer boundary and native bcrypt."""
import importlib
import json
import pytest
from fastapi.testclient import TestClient

api = importlib.import_module('alphaos_api.app')
HASH = '$2b$12$E06IN5AWIp.Dnep75.KsDOhhciZNBaKKidKkydiYqnMo2lGBvBdYG'
PASSWORD = 'test-only-alphaos-password-42'
PATH = '/v1/website-auth/verify'


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('ALPHAOS_API_TOKEN', 'synthetic-api-token')
    # This endpoint does not use MCP; do not restart its one-shot lifespan.
    return TestClient(api.app)


def test_verification_and_no_credential_leakage(client, caplog):
    for password, expected in [(PASSWORD, True), ('incorrect', False)]:
        r = client.post(PATH, headers={'Authorization': 'Bearer synthetic-api-token'},
                        json={'password': password, 'password_hash': HASH})
        assert r.status_code == 200
        assert r.json() == {'verified': expected}
        assert r.headers['cache-control'] == 'no-store'
        assert password not in r.text and HASH not in r.text
    assert PASSWORD not in caplog.text and HASH not in caplog.text


@pytest.mark.parametrize('authorization,status', [('', 401), ('Bearer forged', 403)])
def test_service_authentication_precedes_bcrypt(client, monkeypatch, authorization, status):
    def forbidden(*args):
        pytest.fail('Unauthenticated bcrypt invocation')
    monkeypatch.setattr('alphaos_api.website_auth._verify', forbidden)
    assert client.post(PATH, headers={'Authorization': authorization},
                       json={'password': PASSWORD, 'password_hash': HASH}).status_code == status


@pytest.mark.parametrize('payload', [
    {}, {'password': 'x'*73, 'password_hash': HASH},
    {'password': 'é'*37, 'password_hash': HASH},
    {'password': PASSWORD, 'password_hash': HASH.replace('$12$', '$04$')},
    {'password': PASSWORD, 'password_hash': HASH, 'extra': True},
    {'password': 1, 'password_hash': HASH},
])
def test_invalid_inputs_fail_closed(client, payload):
    r = client.post(PATH, headers={'Authorization': 'Bearer synthetic-api-token'}, json=payload)
    assert r.status_code == 422
    assert PASSWORD not in r.text and HASH not in r.text


def test_duplicate_oversized_and_backend_failure(client, monkeypatch):
    headers = {'Authorization': 'Bearer synthetic-api-token', 'Content-Type': 'application/json'}
    assert client.post(PATH, headers=headers, content='{"password":"a","password":"b"}').status_code == 422
    assert client.post(PATH, headers=headers, content='x'*2049).status_code == 413
    def broken(*args):
        raise RuntimeError(PASSWORD)
    monkeypatch.setattr('alphaos_api.website_auth._verify', broken)
    r = client.post(PATH, headers=headers, content=json.dumps({'password': PASSWORD, 'password_hash': HASH}))
    assert r.status_code == 500 and PASSWORD not in r.text


def test_bcrypt_capacity_fails_closed():
    from alphaos_api.website_auth import _slots, _verify
    from alphaos_api.contracts import APIError
    _slots.acquire(); _slots.acquire()
    try:
        with pytest.raises(APIError) as exc:
            _verify(PASSWORD.encode(), HASH.encode())
        assert exc.value.status == 503
    finally:
        _slots.release(); _slots.release()


def test_worker_render_exchange_integration(client):
    import subprocess
    from pathlib import Path
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            response = client.post(self.path, headers={
                'Authorization': self.headers.get('Authorization', ''),
                'Content-Type': self.headers.get('Content-Type', '')},
                content=self.rfile.read(int(self.headers['Content-Length'])))
            self.send_response(response.status_code)
            self.send_header('Content-Length', str(len(response.content)))
            self.end_headers()
            self.wfile.write(response.content)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(['node', '--experimental-strip-types', 'tests/render-auth-integration.mjs',
                                 f'http://127.0.0.1:{server.server_port}'],
                                cwd=Path(__file__).parents[1] / 'web', capture_output=True, text=True, timeout=30)
        # Only synthetic credentials are used by this isolated bridge.
        assert result.returncode == 0, result.stderr
        assert 'signed session: PASS' in result.stdout
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
