"""Collect one point-in-time SPY/QQQ market archive snapshot."""
import sys

from modules.daily_public import DailyPublicProvider
from modules.intraday_archive import collect_symbol, load_config
from modules.public_intraday import fetch_intraday_bars
from modules.supabase_archive import archive_client, persist_candles, persist_option_snapshot


def main():
    config = load_config()
    provider = DailyPublicProvider.from_environment()
    database = archive_client()
    failures = []

    for symbol in config["symbols"]:
        try:
            observed = provider.now()
            bars = fetch_intraday_bars(provider, symbol, "ONE_MINUTE")
            candle_count = persist_candles(database, bars)

            payload = collect_symbol(provider, symbol, config, now=observed)
            snapshot = persist_option_snapshot(database, payload)
            print(
                f"archived {symbol}: candles={candle_count}; "
                f"snapshot={snapshot.get('id', snapshot.get('archive_path'))}"
            )
        except Exception as exc:
            failures.append(symbol)
            # Do not print provider/database exception bodies: they may contain
            # request details. Diagnostics stay deliberately credential-safe.
            print(f"failed {symbol}: {type(exc).__name__}", file=sys.stderr)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
