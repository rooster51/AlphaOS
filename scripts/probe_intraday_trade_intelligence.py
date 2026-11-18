"""Measure the authenticated intraday REST contract using the configured Public account."""
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import os
from secrets import token_urlsafe
from time import perf_counter


def main():
    if not os.environ.get("PUBLIC_API_SECRET"):
        raise SystemExit("public_not_configured")
    os.environ["ALPHAOS_API_TOKEN"] = token_urlsafe(32)
    os.environ["ALPHAOS_TIME_CLOSED_RESEARCH"] = "true"
    logging.disable(logging.CRITICAL)

    from fastapi.testclient import TestClient
    from alphaos_api.app import app

    symbols = ("SPY", "QQQ")
    auth = {"Authorization": f"Bearer {os.environ['ALPHAOS_API_TOKEN']}"}

    with TestClient(app) as client:
        def probe(symbol, sample, snapshot_id=None):
            path = f"/v1/research/trade-intelligence/{symbol}"
            start = perf_counter()
            response = client.get(path, headers=auth, params={"snapshot_id": snapshot_id} if snapshot_id else {})
            elapsed_ms = round((perf_counter() - start) * 1000, 1)
            body = response.json()
            evidence = body.get("evidence", {})
            provisional = evidence.get("provisional_research", {})
            row = {
                "symbol": symbol, "sample": sample, "status": response.status_code,
                "elapsed_ms": elapsed_ms, "error": body.get("error", {}).get("code"),
                "session": evidence.get("session", {}).get("state"),
                "freshness": evidence.get("data", {}).get("freshness"),
                "accepted_bars": evidence.get("data", {}).get("accepted_bars"),
                "confirmed_bars": evidence.get("data", {}).get("confirmed_bars"),
                "state": evidence.get("state"),
                "provisional": {key: provisional.get(key) for key in (
                    "evidence", "reason", "actionable", "provider", "bar_count",
                    "latest_bar_at", "observations_at",
                )},
                "indicators_available": {key: provisional.get(key) is not None for key in (
                    "opening_range", "vwap", "ema9",
                )},
            }
            return row, body.get("meta", {}).get("snapshot_id")

        snapshots = {}
        for symbol in symbols:
            row, snapshots[symbol] = probe(symbol, "first_unpinned")
            print(json.dumps(row), flush=True)
            if not snapshots[symbol]:
                market = client.get(f"/v1/market/{symbol}", headers=auth)
                snapshots[symbol] = market.json().get("meta", {}).get("snapshot_id")
                print(json.dumps({"symbol": symbol, "market_status": market.status_code,
                                  "snapshot_available": bool(snapshots[symbol])}), flush=True)
        for symbol in symbols:
            row, _ = probe(symbol, "warm", snapshots[symbol])
            print(json.dumps(row), flush=True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            for row, _ in pool.map(lambda symbol: probe(symbol, "simultaneous", snapshots[symbol]), symbols):
                print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
