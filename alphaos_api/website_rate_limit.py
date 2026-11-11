"""Shared website login rate limiting through the existing Supabase service role."""
import json
import os
from urllib.parse import urlsplit

import httpx

from .contracts import APIError


_RPC_PATH = "/rest/v1/rpc/consume_website_login_attempt"
_MAX_RESPONSE_BYTES = 512
_TIMEOUT_SECONDS = 5.0


def _rpc_url_and_key():
    base = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    try:
        parsed = urlsplit(base)
        valid_base = (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and (parsed.port is None or 1 <= parsed.port <= 65535)
            and parsed.path in ("", "/")
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError:
        valid_base = False
    if not valid_base or not key:
        raise APIError("login_rate_limiter_unavailable", 503)
    return base.rstrip("/") + _RPC_PATH, key


async def consume_website_login_attempt():
    """Consume one shared attempt; errors fail closed without leaking secrets."""
    url, key = _rpc_url_and_key()
    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT_SECONDS,
            follow_redirects=False,
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
        ) as client:
            async with client.stream("POST", url, json={}) as response:
                if response.status_code != 200:
                    raise APIError("login_rate_limiter_unavailable", 503)
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > _MAX_RESPONSE_BYTES:
                        raise APIError("login_rate_limiter_unavailable", 503)
    except (httpx.HTTPError, ValueError):
        raise APIError("login_rate_limiter_unavailable", 503) from None

    try:
        result = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise APIError("login_rate_limiter_unavailable", 503) from None
    if (
        not isinstance(result, list)
        or len(result) != 1
        or not isinstance(result[0], dict)
        or set(result[0]) != {"allowed", "retry_after_seconds"}
        or type(result[0]["allowed"]) is not bool
        or type(result[0]["retry_after_seconds"]) is not int
        or not 0 <= result[0]["retry_after_seconds"] <= 60
        or (result[0]["allowed"] and result[0]["retry_after_seconds"] != 0)
        or (not result[0]["allowed"] and result[0]["retry_after_seconds"] == 0)
    ):
        raise APIError("login_rate_limiter_unavailable", 503)
    return result[0]
