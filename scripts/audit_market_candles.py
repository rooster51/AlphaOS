"""Read-only audit of the Supabase ``market_candles`` archive.

Fetches archived 1-minute SPY/QQQ observations and reports duplicate, conflicting
and invalid buckets using modules.candle_integrity. It performs GET requests only:
no insert, upsert, update or delete is issued. Credentials are read from the
server-side environment and are never printed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from modules.candle_integrity import audit_candle_rows, summarize_report

PAGE_SIZE = 1000
SELECT = "provider,symbol,aggregation,bar_time,open,high,low,close,volume,retrieved_at"


def fetch_rows(url, key, symbols, aggregation, since, max_rows):
    """Page through archived rows with read-only GET requests."""
    base = url.rstrip("/") + "/rest/v1/market_candles"
    rows = []
    while len(rows) < max_rows:
        params = {
            "select": SELECT,
            "aggregation": f"eq.{aggregation}",
            "order": "symbol.asc,bar_time.asc",
            "limit": PAGE_SIZE,
            "offset": len(rows),
        }
        if len(symbols) == 1:
            params["symbol"] = f"eq.{symbols[0]}"
        else:
            params["symbol"] = "in.(" + ",".join(symbols) + ")"
        if since:
            params["bar_time"] = f"gte.{since}"
        request = urllib.request.Request(
            f"{base}?{urllib.parse.urlencode(params)}",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            page = json.loads(response.read().decode("utf-8"))
        if not isinstance(page, list):
            raise RuntimeError("Unexpected archive response")
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
    return rows[:max_rows]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--symbol",
        dest="symbols",
        action="append",
        choices=("SPY", "QQQ"),
        help="Symbol to audit; repeatable. Defaults to SPY and QQQ.",
    )
    parser.add_argument("--aggregation", default="ONE_MINUTE")
    parser.add_argument("--since", help="Optional ISO-8601 lower bound for bar_time")
    parser.add_argument("--max-rows", type=int, default=20000)
    parser.add_argument(
        "--output",
        help="Write the full report (including raw rows) to this path instead of stdout",
    )
    args = parser.parse_args(argv)

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print(
            "Supabase archive credentials are not configured; no query was made.",
            file=sys.stderr,
        )
        return 2

    symbols = args.symbols or ["SPY", "QQQ"]
    try:
        rows = fetch_rows(url, key, symbols, args.aggregation, args.since, args.max_rows)
    except Exception as exc:  # type and stage only; never response bodies or URLs
        print(f"candle audit failed: {type(exc).__name__}", file=sys.stderr)
        return 1

    report = audit_candle_rows(rows)
    summary = summarize_report(report)
    if args.output:
        destination = Path(args.output)
        destination.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
