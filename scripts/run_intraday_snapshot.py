"""Collect one point-in-time SPY/QQQ snapshot from Public."""
import gzip
import json
import sys
from datetime import datetime
from pathlib import Path

from modules.daily_public import DailyPublicProvider
from modules.intraday_archive import collect_symbol, load_config, snapshot_path
from modules.public_intraday import fetch_intraday_bars


def _bar_path(root, bar):
    stamp = datetime.fromisoformat(str(bar["timestamp"]).replace("Z", "+00:00"))
    return (Path(root) / "bars" / f"symbol={bar['symbol']}" /
            f"date={stamp.date().isoformat()}" / f"{stamp.strftime('%H%M%S')}.json.gz")


def _write_new_bars(root, bars):
    written = 0
    for bar in bars:
        path = _bar_path(root, bar)
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            json.dump(bar, handle, separators=(",", ":"), sort_keys=True)
        written += 1
    return written


def main():
    config = load_config()
    provider = DailyPublicProvider.from_environment()
    failures = []
    for symbol in config["symbols"]:
        try:
            observed = provider.now()

            # Public documents DAY/ONE_MINUTE. Fetch the provider's regular-market
            # bars and persist only bars not already archived.
            bars = fetch_intraday_bars(provider, symbol, "ONE_MINUTE")
            bar_count = _write_new_bars(config["storage_root"], bars)

            payload = collect_symbol(provider, symbol, config, now=observed)
            path = snapshot_path(config["storage_root"], symbol, observed)
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                raise RuntimeError("snapshot already exists")
            with gzip.open(path, "wt", encoding="utf-8") as handle:
                json.dump(payload, handle, separators=(",", ":"), sort_keys=True)
            print(f"archived {symbol}: {path}; new one-minute bars={bar_count}")
        except Exception as exc:
            failures.append(symbol)
            print(f"failed {symbol}: {type(exc).__name__}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
