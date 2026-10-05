"""Collect one point-in-time SPY/QQQ market archive snapshot."""
import sys
import traceback
from datetime import datetime, timezone
import time

from modules.daily_public import DailyPublicProvider
from modules.intraday_archive import collect_symbol, load_config
from modules.market_session_gate import regular_session_slot
from modules.public_intraday import fetch_intraday_bars
from modules.supabase_archive import archive_client, persist_candles, persist_option_snapshot, find_slot_snapshot


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
        f"location={location}",
        file=sys.stderr,
    )


def main(clock=lambda: datetime.now(timezone.utc), sleep=time.sleep):
    config = load_config()
    slot = regular_session_slot(now=clock(), cadence_minutes=int(config["option_snapshot_minutes"]))
    if slot is None:
        print("NYSE regular session is closed; no archive snapshot collected.")
        return 0
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
        succeeded = False
        for attempt in range(1, 3):
            stage = "session_gate"
            try:
                observed = clock()
                if regular_session_slot(observed, int(config["option_snapshot_minutes"])) != slot:
                    raise RuntimeError("Slot no longer active")
                stage = "duplicate_check"
                prior = find_slot_snapshot(database, provider.name, symbol, slot.isoformat())
                if prior:
                    if prior.get("quality_status") != "complete":
                        raise RuntimeError("Existing snapshot is incomplete")
                    print(f"duplicate {symbol}: slot={slot.isoformat()}; attempt={attempt}")
                    succeeded = True
                    break
                stage = "public_intraday_bars"
                bars = fetch_intraday_bars(provider, symbol, "ONE_MINUTE")
                stage = "supabase_candles"
                candle_count = persist_candles(database, bars)
                stage = "public_quote_options"
                if regular_session_slot(clock(), int(config["option_snapshot_minutes"])) != slot:
                    raise RuntimeError("Slot no longer active")
                payload = collect_symbol(provider, symbol, config)
                payload["slot_time"] = slot.isoformat()
                payload["collection_finished_at"] = clock().isoformat()
                if regular_session_slot(clock(), int(config["option_snapshot_minutes"])) is None:
                    raise RuntimeError("Market closed during collection")
                stage = "supabase_option_snapshot"
                snapshot = persist_option_snapshot(database, payload, config)
                if snapshot.get("quality_status") != "complete":
                    raise RuntimeError("Partial or empty options snapshot archived")
                print(f"archived {symbol}: candles={candle_count}; slot={slot.isoformat()}; observed_at={snapshot['observed_at']}; attempt={attempt}")
                succeeded = True
                break
            except Exception as exc:
                _safe_failure(symbol, stage, exc)
                if attempt == 1:
                    sleep(10)
        if not succeeded:
            failures.append(symbol)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
