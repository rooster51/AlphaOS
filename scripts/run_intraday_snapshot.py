"""Collect one point-in-time SPY/QQQ snapshot from Public."""
import gzip
import json
import sys
from pathlib import Path

from modules.daily_public import DailyPublicProvider
from modules.intraday_archive import collect_symbol, load_config, snapshot_path


def main():
    config = load_config()
    provider = DailyPublicProvider.from_environment()
    failures = []
    for symbol in config["symbols"]:
        try:
            observed = provider.now()
            payload = collect_symbol(provider, symbol, config, now=observed)
            path = snapshot_path(config["storage_root"], symbol, observed)
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                raise RuntimeError("snapshot already exists")
            with gzip.open(path, "wt", encoding="utf-8") as handle:
                json.dump(payload, handle, separators=(",", ":"), sort_keys=True)
            print(f"archived {symbol}: {path}")
        except Exception as exc:
            failures.append(symbol)
            print(f"failed {symbol}: {type(exc).__name__}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
