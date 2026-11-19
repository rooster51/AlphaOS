"""Replay versioned, entitled candle snapshots with original availability times."""
from collections import defaultdict
from statistics import median

from modules.market_playbook import BAR, evaluate, session_windows, stamp


def _results(history, coverage, split):
    groups = defaultdict(list)
    for item in history:
        thesis = item["thesis"]
        if (thesis["session"] >= split) != coverage["out_of_sample"]:
            continue
        for key in ("all", thesis["symbol"], thesis["family"], thesis["bias"],
                    f'{thesis["symbol"]}/{thesis["family"]}/{thesis["bias"]}'):
            groups[key].append(item)

    result = {}
    for key, items in sorted(groups.items()):
        times = []
        triggered = 0
        counts = {state: 0 for state in ("COMPLETED", "INVALIDATED", "EXPIRED", "UNRESOLVED")}
        for item in items:
            state = item["state"]
            counts[state] += 1
            first = next((event for event in item["events"] if event["state"] == "CONFIRMED"), None)
            if first:
                triggered += 1
                last = item["events"][-1]
                if last["bar_at"]:
                    times.append((stamp(last["bar_at"]) - stamp(first["bar_at"])).total_seconds())
        result[key] = {
            "generated": len(items), "triggered": triggered, "outcomes": counts,
            "trigger_pct": 100 * triggered / len(items),
            "outcome_pct_of_generated": {state: 100 * count / len(items) for state, count in counts.items()},
            "target_pct_of_triggered": 100 * counts["COMPLETED"] / triggered if triggered else None,
            "time_to_verified_outcome_seconds_median": median(times) if times else None,
            "timed_outcomes": len(times),
        }
    return {
        "coverage": coverage, "results": result,
        "status": "measured" if result else "insufficient_data",
    }


def replay(snapshots, journal, *, out_of_sample_start, universe, prior_by_snapshot=None, decision_by_snapshot=None):
    """Replay provider snapshots through a fresh journal; universe is frozen in advance.

    Universe entries are (session date, symbol, provider), including slots with
    no captured data. Snapshot timestamps must represent actual availability.
    Use a fresh database for each run. The split date is fixed by the caller.
    Pass original decision timestamps if other evidence arrived after retrieval.
    """
    universe = set(universe)
    prior_by_snapshot = prior_by_snapshot or {}
    decision_by_snapshot = decision_by_snapshot or {}
    coverage = {}
    history = {}
    ordered = sorted(
        ((stamp(decision_by_snapshot.get(snap.snapshot_id, snap.retrieved_at)), snap.snapshot_id, snap)
         for snap in snapshots),
        key=lambda item: (item[0], item[1]),
    )
    for now, _, snapshot in ordered:
        view, proposals, bars = evaluate(snapshot, now, prior_by_snapshot.get(snapshot.snapshot_id))
        key = (view["session"], snapshot.symbol, snapshot.provider)
        if key not in universe:
            continue
        stats = coverage.setdefault(key, {"snapshots": 0, "freshest_confirmed_prefix": 0})
        stats["snapshots"] += 1
        stats["freshest_confirmed_prefix"] = max(stats["freshest_confirmed_prefix"], len(bars))
        for item in journal.observe(snapshot.symbol, proposals, bars, now, view.get("provenance"), snapshot.provider):
            history[item["thesis"]["id"]] = item

    # Finish each expected symbol/provider stream after its last scheduled session.
    last_sessions = {}
    for session, symbol, provider in sorted(universe):
        last_sessions[symbol, provider] = session
    for (symbol, provider), session in last_sessions.items():
        close = session_windows(stamp(session + "T23:00:00+00:00"))[-1][1]
        for item in journal.observe(symbol, [], [], close + 2 * BAR, None, provider):
            history[item["thesis"]["id"]] = item

    partitions = []
    for out_of_sample in (False, True):
        keys = [key for key in universe if (key[0] >= out_of_sample_start) == out_of_sample]
        observed = [coverage[key] for key in keys if key in coverage]
        partitions.append(_results(history.values(), {
            "out_of_sample": out_of_sample, "expected_symbol_sessions": len(keys),
            "observed_symbol_sessions": len(observed),
            "symbol_sessions_with_confirmed_evidence": sum(
                row["freshest_confirmed_prefix"] > 0 for row in observed
            ),
            "snapshots": sum(row["snapshots"] for row in observed),
        }, out_of_sample_start))
    return {"measure": "underlying-price closes", "split": out_of_sample_start,
            "development": partitions[0], "out_of_sample": partitions[1]}
