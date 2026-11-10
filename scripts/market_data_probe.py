"""Bounded read-only Public market-data quality probe.

This script never writes an archive, changes credentials, creates candles from
quotes or retries aggressively. It requires existing Public credentials in the
process environment and reports only normalized observations and safe error
codes. Run it during a regular session for meaningful latency measurements.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from datetime import datetime, timezone

from modules.data_entitlements import PRIVATE_RESEARCH, enforce_data_use
from modules.market_data_contracts import SUPPORTED_INTERVALS, SUPPORTED_SYMBOLS
from modules.market_data_gateway import (
    MarketDataError,
    PublicMarketDataProvider,
    build_snapshot,
)


def _summary(values):
    values = [value for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)]
    if not values:
        return None
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "min": ordered[0],
        "median": statistics.median(ordered),
        "max": ordered[-1],
    }


def probe_once(provider, symbol, interval, *, clock, limit=390):
    """Measure one quote and one native candle request without a cache."""
    enforce_data_use(PRIVATE_RESEARCH, provider.name)
    now = clock()
    result = {
        "symbol": symbol,
        "interval": interval,
        "requested_at": now.isoformat(),
        "available": False,
        "error": None,
        "quote_latency_ms": None,
        "candle_latency_ms": None,
        "quote_to_candle_lag_seconds": None,
        "latest_candle_at": None,
        "expected_bars": None,
        "received_bars": None,
        "returned_bars": None,
        "completeness": None,
        "last_bar_status": None,
        "freshness": None,
        "warnings": [],
        "first_candle_at": None,
    }
    try:
        started = time.perf_counter()
        quote = provider.quote(symbol)
        result["quote_latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
        started = time.perf_counter()
        batch = provider.candles(symbol, interval, "regular", limit)
        result["candle_latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
        snapshot = build_snapshot(batch, now=clock())
        result.update(
            available=True,
            latest_candle_at=snapshot.latest_candle_at,
            first_candle_at=snapshot.candles[0].time if snapshot.candles else None,
            expected_bars=snapshot.expected_bars,
            received_bars=snapshot.received_bars,
            returned_bars=snapshot.returned_bars,
            completeness=snapshot.completeness,
            last_bar_status=snapshot.last_bar_status,
            freshness=snapshot.freshness,
            warnings=list(snapshot.warnings),
        )
        if quote.quote_time and snapshot.latest_candle_at:
            quote_time = datetime.fromisoformat(quote.quote_time)
            candle_time = datetime.fromisoformat(snapshot.latest_candle_at)
            result["quote_to_candle_lag_seconds"] = (quote_time - candle_time).total_seconds()
    except MarketDataError as exc:
        result["error"] = exc.code
    except Exception:
        result["error"] = "probe_failure"
    return result


def summarize(observations):
    by_key = {}
    for row in observations:
        by_key.setdefault((row["symbol"], row["interval"]), []).append(row)
    summary = []
    for (symbol, interval), rows in sorted(by_key.items()):
        successful = [row for row in rows if row["available"]]
        summary.append({
            "symbol": symbol,
            "interval": interval,
            "samples": len(rows),
            "available_samples": len(successful),
            "errors": sorted({row["error"] for row in rows if row["error"]}),
            "quote_latency_ms": _summary([row["quote_latency_ms"] for row in successful]),
            "candle_latency_ms": _summary([row["candle_latency_ms"] for row in successful]),
            "quote_to_candle_lag_seconds": _summary(
                [row["quote_to_candle_lag_seconds"] for row in successful]
            ),
            "completeness": sorted({row["completeness"] for row in successful}),
            "last_bar_status": sorted({row["last_bar_status"] for row in successful}),
            "freshness": sorted({row["freshness"] for row in successful}),
            "warning_codes": sorted({warning for row in successful for warning in row["warnings"]}),
        })
    return summary


def main(argv=None, *, provider=None, clock=None, sleep=time.sleep):
    parser = argparse.ArgumentParser(description="Bounded read-only Public candle quality probe.")
    parser.add_argument("--symbols", nargs="+", default=list(SUPPORTED_SYMBOLS), choices=SUPPORTED_SYMBOLS)
    parser.add_argument("--intervals", nargs="+", default=list(SUPPORTED_INTERVALS), choices=SUPPORTED_INTERVALS)
    parser.add_argument("--samples", type=int, default=1)
    parser.add_argument("--interval-seconds", type=float, default=30.0)
    parser.add_argument("--limit", type=int, default=390)
    parser.add_argument("--output", help="Optional JSON output path; must be inside the working tree.")
    args = parser.parse_args(argv)
    if not 1 <= args.samples <= 10:
        parser.error("--samples must be between 1 and 10")
    if not 0 <= args.interval_seconds <= 300:
        parser.error("--interval-seconds must be between 0 and 300")
    if not 1 <= args.limit <= 390:
        parser.error("--limit must be between 1 and 390")
    if args.output and (os.path.isabs(args.output) or ".." in args.output.split(os.sep)):
        parser.error("--output must be a relative path inside the working tree")

    clock = clock or (lambda: datetime.now(timezone.utc))
    if provider is None and not os.environ.get("PUBLIC_API_SECRET"):
        payload = {
            "schema_version": "alphaos-candle-probe-v1",
            "status": "unavailable",
            "reason": "public_not_configured",
            "measured": False,
            "caveat": "No synthetic latency or availability values are reported.",
        }
        text = json.dumps(payload, indent=2, sort_keys=True)
        print(text)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as stream:
                stream.write(text + "\n")
        return 2

    provider = provider or PublicMarketDataProvider(clock=clock)
    observations = []
    for sample in range(args.samples):
        for symbol in args.symbols:
            for interval in args.intervals:
                observations.append(probe_once(provider, symbol, interval, clock=clock, limit=args.limit))
        if sample + 1 < args.samples and args.interval_seconds:
            sleep(args.interval_seconds)
    payload = {
        "schema_version": "alphaos-candle-probe-v1",
        "status": "measured",
        "measured": True,
        "caveat": "Empirical observations only; provider entitlement, exchange latency and rate limits remain unverified.",
        "observations": observations,
        "summary": summarize(observations),
    }
    text = json.dumps(payload, indent=2, sort_keys=True)
    print(text)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as stream:
            stream.write(text + "\n")
    return 0 if any(row["available"] for row in observations) else 1


if __name__ == "__main__":
    raise SystemExit(main())
