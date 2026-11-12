"""Private authenticated website probe for the native candle display path.

This probe uses the same website session, same-origin candle bridge and quote
bridge a browser uses. It never accepts or prints the backend bearer token, and
it cannot bypass ``ALPHAOS_CANDLE_CHART_ENABLED``. A disabled route is reported
as blocked rather than treated as a data failure.

The probe is read-only and bounded: it requests SPY/QQQ at 1m, 5m and 15m and
one quote per symbol/interval. It does not place orders, write archives, change
credentials, or retry aggressively.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

SCHEMA_VERSION = "alphaos-candle-display-probe-v1"
COOKIE_NAME = "__Host-alphaos_session"
ENTITLEMENT_CONTEXT = "owner_private_display"
SYMBOLS = ("SPY", "QQQ")
INTERVALS = ("1m", "5m", "15m")
INTERVAL_SECONDS = {"1m": 60, "5m": 300, "15m": 900}
MAX_BODY_BYTES = 2_000_000
REQUEST_TIMEOUT_SECONDS = 20


class ProbeTransportError(RuntimeError):
    """The website could not be reached without exposing a raw exception."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes


Transport = Callable[[str, str], HttpResponse]


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_get(url: str, session: str) -> HttpResponse:
    """GET with only the website session cookie, never a backend token."""
    request = Request(
        url,
        headers={"Accept": "application/json", "Cookie": f"{COOKIE_NAME}={session}"},
        method="GET",
    )
    opener = build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read(MAX_BODY_BYTES + 1)
            if len(body) > MAX_BODY_BYTES:
                raise ProbeTransportError("response_too_large")
            return HttpResponse(
                status=response.status,
                headers={key.lower(): value for key, value in response.headers.items()},
                body=body,
            )
    except HTTPError as exc:
        body = exc.read(MAX_BODY_BYTES + 1)
        if len(body) > MAX_BODY_BYTES:
            raise ProbeTransportError("response_too_large") from None
        return HttpResponse(
            status=exc.code,
            headers={key.lower(): value for key, value in exc.headers.items()},
            body=body,
        )
    except (URLError, TimeoutError, OSError):
        raise ProbeTransportError("request_failed") from None


def _json_body(response: HttpResponse) -> dict | None:
    try:
        value = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _error_code(value: dict | None) -> str | None:
    if value is None:
        return None
    direct = value.get("code")
    if isinstance(direct, str):
        return direct
    error = value.get("error")
    if isinstance(error, dict) and isinstance(error.get("code"), str):
        return error["code"]
    return None


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp")
    return parsed.astimezone(timezone.utc)


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def analyze_snapshot(snapshot: object, *, symbol: str, interval: str, now: datetime) -> dict:
    """Validate one returned snapshot and measure its timestamp/data quality."""
    if not isinstance(snapshot, dict):
        raise ValueError("snapshot")
    if snapshot.get("symbol") != symbol or snapshot.get("interval") != interval:
        raise ValueError("snapshot identity")
    if snapshot.get("session") != "regular":
        raise ValueError("session")
    if snapshot.get("schema_version") != "alphaos-candles-v1":
        raise ValueError("schema")
    candles = snapshot.get("candles")
    if not isinstance(candles, list) or not candles:
        raise ValueError("candles")

    times: list[datetime] = []
    bars_valid = True
    for bar in candles:
        if not isinstance(bar, dict):
            raise ValueError("bar")
        times.append(_timestamp(bar.get("time")))
        if not all(_number(bar.get(key)) for key in ("open", "high", "low", "close", "volume")):
            bars_valid = False
        elif not (
            bar["open"] > 0
            and bar["high"] > 0
            and bar["low"] > 0
            and bar["close"] > 0
            and bar["volume"] >= 0
            and bar["high"] >= max(bar["open"], bar["close"], bar["low"])
            and bar["low"] <= min(bar["open"], bar["close"], bar["high"])
        ):
            bars_valid = False

    retrieved_at = _timestamp(snapshot.get("retrieved_at"))
    latest_candle_at = _timestamp(snapshot.get("latest_candle_at"))
    step = INTERVAL_SECONDS[interval]
    deltas = [
        int((times[index] - times[index - 1]).total_seconds())
        for index in range(1, len(times))
    ]
    monotonic = all(delta > 0 for delta in deltas)
    aligned = all(delta > 0 and delta % step == 0 for delta in deltas)
    missing_bars = sum(max(0, delta // step - 1) for delta in deltas) if monotonic else None
    latest_matches = _timestamp(candles[-1].get("time")) == latest_candle_at
    retrieved_after_latest = retrieved_at >= latest_candle_at
    returned = snapshot.get("returned_bars")
    received = snapshot.get("received_bars")
    expected = snapshot.get("expected_bars")
    counts_valid = (
        isinstance(returned, int)
        and returned == len(candles)
        and isinstance(received, int)
        and received >= returned
        and (expected is None or isinstance(expected, int))
    )
    entitlement = snapshot.get("entitlement")
    entitlement_allowed = isinstance(entitlement, dict) and entitlement.get("allowed") is True
    entitlement_context = entitlement.get("use_context") if isinstance(entitlement, dict) else None
    valid = (
        bars_valid
        and monotonic
        and aligned
        and missing_bars is not None
        and latest_matches
        and retrieved_after_latest
        and counts_valid
        and entitlement_allowed
        and entitlement_context == ENTITLEMENT_CONTEXT
    )

    return {
        "available": True,
        "status": "valid" if valid else "invalid",
        "schema_version": snapshot.get("schema_version"),
        "symbol": snapshot.get("symbol"),
        "interval": snapshot.get("interval"),
        "provider": snapshot.get("provider"),
        "snapshot_id": snapshot.get("snapshot_id"),
        "latest_candle_at": latest_candle_at.isoformat(),
        "retrieved_at": retrieved_at.isoformat(),
        "data_age_seconds": max(0, round((now - latest_candle_at).total_seconds())),
        "snapshot_age_seconds": max(0, round((now - retrieved_at).total_seconds())),
        "coverage": {
            "expected_bars": expected,
            "received_bars": received,
            "returned_bars": returned,
            "first_candle_at": times[0].isoformat(),
            "last_candle_at": times[-1].isoformat(),
            "missing_bars": missing_bars,
            "completeness": snapshot.get("completeness"),
        },
        "timestamps": {
            "strictly_increasing": monotonic,
            "interval_aligned": aligned,
            "latest_matches_last_bar": latest_matches,
            "retrieved_after_latest": retrieved_after_latest,
            "bars_valid": bars_valid,
            "counts_valid": counts_valid,
        },
        "quality": {
            "last_bar_status": snapshot.get("last_bar_status"),
            "freshness": snapshot.get("freshness"),
            "warnings": snapshot.get("warnings") if isinstance(snapshot.get("warnings"), list) else [],
        },
        "entitlement": {
            "allowed": entitlement_allowed,
            "use_context": entitlement_context,
            "policy_version": entitlement.get("policy_version") if isinstance(entitlement, dict) else None,
        },
    }


def _blocked(http_status: int, code: str | None, *, cache_control: str | None = None) -> dict:
    return {
        "available": False,
        "status": "blocked" if http_status in (401, 403, 503) else "error",
        "http_status": http_status,
        "error": code or "http_error",
        "cache_control": cache_control,
    }


def probe_interval(
    transport: Transport,
    base_url: str,
    session: str,
    symbol: str,
    interval: str,
    *,
    now: datetime,
) -> dict:
    query = urlencode({"interval": interval, "session": "regular", "limit": 390})
    url = f"{base_url}/api/candles/{symbol}?{query}"
    try:
        response = transport(url, session)
    except ProbeTransportError as exc:
        return {"available": False, "status": "error", "error": str(exc)}
    payload = _json_body(response)
    cache_control = response.headers.get("cache-control")
    if response.status != 200:
        return _blocked(response.status, _error_code(payload), cache_control=cache_control)
    if payload is None or payload.get("status") != "ok":
        return {
            "available": False,
            "status": "error",
            "http_status": response.status,
            "error": "invalid_response",
            "cache_control": cache_control,
        }
    try:
        result = analyze_snapshot(payload.get("snapshot"), symbol=symbol, interval=interval, now=now)
    except (ValueError, TypeError):
        return {
            "available": False,
            "status": "error",
            "http_status": response.status,
            "error": "snapshot_schema_mismatch",
            "cache_control": cache_control,
        }
    result.update(http_status=response.status, cache_control=cache_control)
    return result


def probe_quote(
    transport: Transport,
    base_url: str,
    session: str,
    symbol: str,
) -> dict:
    url = f"{base_url}/api/current-quote?symbol={symbol}"
    try:
        response = transport(url, session)
    except ProbeTransportError as exc:
        return {"status": "unavailable", "error": str(exc)}
    payload = _json_body(response)
    if response.status != 200 or payload is None:
        return {
            "status": "unavailable",
            "http_status": response.status,
            "error": _error_code(payload) or "quote_unavailable",
        }
    if payload.get("status") == "fresh":
        return {
            "status": "fresh",
            "last_at": payload.get("lastAt"),
            "retrieved_at": payload.get("retrievedAt"),
            "age_seconds": payload.get("ageSeconds"),
        }
    return {
        "status": "unavailable",
        "code": payload.get("code"),
        "reason": payload.get("reason"),
        "age_seconds": payload.get("ageSeconds"),
    }


def probe_pair(
    transport: Transport,
    base_url: str,
    session: str,
    symbol: str,
    interval: str,
    *,
    now: datetime,
) -> dict:
    candle = probe_interval(transport, base_url, session, symbol, interval, now=now)
    candle["symbol"] = symbol
    candle["interval"] = interval
    candle["quote"] = probe_quote(transport, base_url, session, symbol)
    return candle


def summarize(observations: list[dict]) -> list[dict]:
    summary = []
    for row in observations:
        quote = row.get("quote") if isinstance(row.get("quote"), dict) else {}
        coverage = row.get("coverage") if isinstance(row.get("coverage"), dict) else {}
        timestamps = row.get("timestamps") if isinstance(row.get("timestamps"), dict) else {}
        summary.append({
            "symbol": row.get("symbol"),
            "interval": row.get("interval"),
            "status": row.get("status"),
            "available": bool(row.get("available")),
            "error": row.get("error"),
            "data_age_seconds": row.get("data_age_seconds"),
            "missing_bars": coverage.get("missing_bars"),
            "completeness": coverage.get("completeness"),
            "timestamps_consistent": (
                timestamps.get("strictly_increasing") is True
                and timestamps.get("interval_aligned") is True
                and timestamps.get("latest_matches_last_bar") is True
                and timestamps.get("retrieved_after_latest") is True
            ) if timestamps else False,
            "quote_status": quote.get("status"),
            "quote_age_seconds": quote.get("age_seconds"),
        })
    return summary


def _validate_base(value: str) -> str:
    parsed = urlparse(value)
    if (
        not parsed.scheme
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ValueError("base_url")
    if parsed.scheme != "https" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("base_url")
    return value.rstrip("/")


def _write(payload: dict, output: str | None) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True)
    print(text)
    if output:
        with open(output, "w", encoding="utf-8") as stream:
            stream.write(text + "\n")


def main(
    argv=None,
    *,
    transport: Transport = http_get,
    now: datetime | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Private authenticated probe for the AlphaOS candle display path."
    )
    parser.add_argument("--symbols", nargs="+", default=list(SYMBOLS), choices=SYMBOLS)
    parser.add_argument("--intervals", nargs="+", default=list(INTERVALS), choices=INTERVALS)
    parser.add_argument("--output", help="Optional JSON path inside the working tree.")
    args = parser.parse_args(argv)
    if args.output and (os.path.isabs(args.output) or ".." in args.output.split(os.sep)):
        parser.error("--output must be a relative path inside the working tree")

    base_value = os.environ.get("ALPHAOS_SITE_URL", "").strip()
    session = os.environ.get("ALPHAOS_WEBSITE_SESSION", "").strip()
    if not base_value or not session:
        _write({
            "schema_version": SCHEMA_VERSION,
            "status": "blocked",
            "measured": False,
            "reason": "configuration_missing",
            "required_env": ["ALPHAOS_SITE_URL", "ALPHAOS_WEBSITE_SESSION"],
            "caveat": "No network request or synthetic measurement was attempted.",
        }, args.output)
        return 2
    try:
        base_url = _validate_base(base_value)
    except ValueError:
        _write({
            "schema_version": SCHEMA_VERSION,
            "status": "blocked",
            "measured": False,
            "reason": "invalid_site_url",
            "caveat": "Use an HTTPS site URL; loopback HTTP is allowed only for local tests.",
        }, args.output)
        return 2

    current = now or datetime.now(timezone.utc)
    observations = [
        probe_pair(transport, base_url, session, symbol, interval, now=current)
        for symbol in args.symbols
        for interval in args.intervals
    ]
    summary = summarize(observations)
    measured = any(row.get("available") for row in observations)
    feature_blocked = any(row.get("error") == "feature_disabled" for row in observations)
    valid = all(
        row.get("status") == "valid" and row.get("quote", {}).get("status") == "fresh"
        for row in observations
    )
    if valid:
        status = "complete"
        exit_code = 0
    elif feature_blocked or not measured:
        status = "blocked"
        exit_code = 2
    else:
        status = "incomplete"
        exit_code = 1
    _write({
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "measured": measured,
        "site": urlparse(base_url).netloc,
        "measured_at": current.isoformat(),
        "caveat": (
            "Read-only website-path observations only. Availability, timestamps and quote "
            "freshness are measured; provider licensing and redistribution rights are not "
            "inferred from a successful request."
        ),
        "observations": observations,
        "summary": summary,
    }, args.output)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
