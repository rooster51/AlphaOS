"""Collect one point-in-time SPY/QQQ market archive snapshot."""
import sys
import traceback

from modules.daily_public import DailyPublicProvider
from modules.intraday_archive import collect_symbol, load_config
from modules.public_intraday import fetch_intraday_bars
from modules.supabase_archive import archive_client, persist_candles, persist_option_snapshot


def _safe_failure(symbol, stage, exc):
    # Type + stage only. Never print provider response bodies, request headers,
    # URLs containing credentials, database errors, or secret values.
    frames = traceback.extract_tb(exc.__traceback__)
    location = "unknown"
    if frames:
        frame = frames[-1]
        location = f"{frame.filename.rsplit('/', 1)[-1]}:{frame.lineno}:{frame.name}"
    print(
        f"failed {symbol}: stage={stage}; error={type(exc).__name__}; "
        f"location={location}; detail={str(exc)}",
        file=sys.stderr,
    )


def main():
    config = load_config()
    try:
        provider = DailyPublicProvider.from_environment()
    except Exception as exc:
        _safe_failure("collector", "public_auth", exc)
        return 1

    try:
        database = archive_client()
    except Exception as exc:
        _safe_failure("collector", "supabase_client", exc)
        return 1

    failures = []
    for symbol in config["symbols"]:
        stage = "start"
        try:
            observed = provider.now()

            stage = "public_intraday_bars"
            bars = fetch_intraday_bars(provider, symbol, "ONE_MINUTE")

            stage = "supabase_candles"
            candle_count = persist_candles(database, bars)

            stage = "public_quote_options"
            payload = collect_symbol(provider, symbol, config, now=observed)

            stage = "supabase_option_snapshot"
            snapshot = persist_option_snapshot(database, payload, config)

            if isinstance(snapshot, dict):
                snapshot_ref = snapshot.get("id") or snapshot.get("archive_path") or "stored"
            else:
                snapshot_ref = "stored"
            print(
                f"archived {symbol}: candles={candle_count}; snapshot={snapshot_ref}"
            )
        except Exception as exc:
            failures.append(symbol)
            _safe_failure(symbol, stage, exc)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
