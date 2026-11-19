from dataclasses import replace
from datetime import datetime, timedelta, timezone
import sqlite3

import pandas as pd
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from alphaos_api.app import app
from modules.market_data_contracts import CandleBar, CandleSnapshot
from modules.market_playbook import BAR, PriorSession, evaluate, ranked_levels
from modules.market_playbook_replay import replay
from modules.market_playbook_hosted import SupabasePlaybookJournal
from modules.market_playbook_store import PlaybookJournal

OPEN = datetime(2026, 11, 19, 14, 30, tzinfo=timezone.utc)
PRIOR = OPEN - timedelta(days=1)
AS_OF = OPEN + 7 * BAR
CLOSE = OPEN + 78 * BAR


def fixture(symbol="SPY", now=AS_OF, *, final=True, breakout=False, breakdown=False):
    base = 500 if symbol == "SPY" else 430
    previous = tuple(
        CandleBar((PRIOR + index * BAR).isoformat(), base, base + 12, base - 12, base, 50, True)
        for index in range(78)
    )
    closes = [0, 0, 0, -1, 1, 0, 1, 0, 7 if breakout else -7 if breakdown else 0,
              12 if breakout else 0]
    current = []
    for index in range(int((now - OPEN) // BAR)):
        close = base + (closes[index] if index < len(closes) else 0)
        width = 5 if index == 0 else 1
        current.append(CandleBar((OPEN + index * BAR).isoformat(), close, close + width,
                                 close - width, close, 100, final))
    return CandleSnapshot(
        schema_version="alphaos-candles-v1", symbol=symbol, interval="5m", provider="Public",
        session="regular", retrieved_at=now.isoformat(), latest_candle_at=current[-1].time,
        snapshot_id=f"fixture-{symbol}-{now.isoformat()}", expected_bars=None,
        received_bars=len(previous) + len(current), returned_bars=len(previous) + len(current),
        completeness="unknown", last_bar_status="complete" if final else "unknown",
        freshness="fresh", warnings=(), candles=previous + tuple(current),
        provider_capabilities={}, entitlement={},
    )


@pytest.mark.parametrize("symbol,base", [("SPY", 500), ("QQQ", 430)])
def test_ranked_evidence_and_both_directions(symbol, base):
    view, theses, bars = evaluate(fixture(symbol), AS_OF)
    assert view["status"] == "WAIT"
    assert view["vwap"]["status"] == "confirmed"
    assert view["coverage"]["provider_confirmed"] == 7
    assert [level["rank"] for level in view["levels"]] == list(range(1, len(view["levels"]) + 1))
    assert {kind for level in view["levels"] for kind in level["types"]} >= {
        "previous session high", "previous session low", "previous session close",
        "opening range high", "opening range low",
    }
    assert [(thesis["family"], thesis["trigger"], thesis["target"]) for thesis in theses] == [
        ("breakout", base + 5, base + 12), ("breakdown", base, base - 2),
    ]
    assert len(bars) == 7


def test_shared_candle_counts_once_with_repeat_confirmation_and_role_flip():
    # High pivot at bar 2 and a later low pivot at the same price. The opening
    # range high shares the first pivot's timestamp.
    quotes = [(98, 95), (99, 96), (100, 97), (99, 96), (99, 97), (103, 101),
              (105, 102), (104, 100), (105, 102), (106, 103)]
    rows = [
        CandleBar((OPEN + i * BAR).isoformat(), (h + l) / 2, h, l, (h + l) / 2, 100, True)
        for i, (h, l) in enumerate(quotes)
    ]
    levels = ranked_levels(rows, [], OPEN, None, {})
    same = next(level for level in levels if level["low"] == 100)
    assert same["observations"] == 2
    assert same["reactions"] == 2
    assert set(same["types"]) == {"opening range high", "swing high", "swing low", "resistance to support"}
    assert same["rank"] == 1


def test_provisional_missing_delayed_and_stale_never_confirm():
    provisional = fixture(final=None)
    view, theses, bars = evaluate(provisional, AS_OF)
    assert view["vwap"]["status"] == "provisional"
    assert view["provisional_range"] == {"low": 495, "high": 505}
    assert view["status"] == "INSUFFICIENT DATA"
    assert not theses and not bars
    original = fixture()
    for snapshot, now in (
        (original, AS_OF + timedelta(minutes=12)),
        (replace(original, warnings=("provider_delayed",)), AS_OF),
        (replace(original, candles=original.candles[:-4] + original.candles[-3:]), AS_OF),
        (replace(original, retrieved_at=(AS_OF + BAR).isoformat()), AS_OF),
    ):
        assert evaluate(snapshot, now)[1:] == ([], [])


def observe(journal, now, **options):
    snap = fixture(now=now, **options)
    view, proposals, bars = evaluate(snap, now)
    return journal.observe(snap.symbol, proposals, bars, now, view["provenance"], snap.provider)


def test_immutable_lifecycle_duplicate_poll_restart_and_revisions(tmp_path):
    database = tmp_path / "journal.sqlite"
    journal = PlaybookJournal(database)
    original = observe(journal, AS_OF)
    assert {row["state"] for row in original} == {"WAITING"}
    first = observe(journal, AS_OF + 2 * BAR, breakout=True)
    up = next(row for row in first if row["thesis"]["direction"] == "bullish")
    assert [event["state"] for event in up["events"]] == ["WAITING", "CONFIRMED"]

    restarted = PlaybookJournal(database)
    assert observe(restarted, AS_OF + 2 * BAR, breakout=True) == first
    resolved = observe(restarted, AS_OF + 3 * BAR, breakout=True)
    up = next(row for row in resolved if row["thesis"]["direction"] == "bullish")
    assert up["state"] == "COMPLETED"
    assert up["thesis"] == next(row["thesis"] for row in original if row["thesis"]["direction"] == "bullish")
    assert observe(restarted, AS_OF + 3 * BAR, breakout=False) == resolved
    with sqlite3.connect(database) as connection, pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute("DELETE FROM playbook_thesis")


def test_replay_uses_original_availability_and_counts_unobserved_sessions(tmp_path):
    # A late QQQ snapshot already shows a breakdown. Its past candles cannot
    # become validation events for a scenario created from that snapshot.
    universe = [("2026-11-19", symbol, "Public") for symbol in ("SPY", "QQQ")]
    universe.append(("2026-11-18", "SPY", "Public"))
    result = replay([
        fixture("SPY", AS_OF + 3 * BAR, breakout=True),
        fixture("SPY", AS_OF),
        fixture("QQQ", AS_OF + 2 * BAR, breakdown=True),
    ], PlaybookJournal(tmp_path / "replay.sqlite"),
        out_of_sample_start="2026-11-19", universe=universe)
    report = result["out_of_sample"]
    assert report["results"]["SPY"]["outcomes"]["COMPLETED"] == 1
    assert report["results"]["QQQ"]["triggered"] == 0
    assert report["results"]["SPY"]["time_to_verified_outcome_seconds_median"] == 300
    assert result["development"]["coverage"]["expected_symbol_sessions"] == 1
    assert result["development"]["coverage"]["observed_symbol_sessions"] == 0


def test_api_requires_bearer_owner_use_and_entitlement(monkeypatch, tmp_path):
    monkeypatch.setenv("ALPHAOS_API_TOKEN", "fixture-backend-bearer")
    monkeypatch.setenv("ALPHAOS_PLAYBOOK_DB", str(tmp_path / "api.sqlite"))
    requests = []

    def get(symbol, interval, **kwargs):
        requests.append((symbol, interval, kwargs["use_context"]))
        return fixture(symbol)

    service = SimpleNamespace(provider=SimpleNamespace(name="Public"), get=get)
    monkeypatch.setattr(app.state, "candles", service)
    monkeypatch.setattr(app.state, "service", SimpleNamespace(
        completed_history=lambda symbol: {"features": pd.DataFrame(
            [{"date": "2026-11-18", "high": 450, "low": 410, "close": 430}]
        )},
    ))
    client = TestClient(app)
    endpoint = "/v1/market-playbook/QQQ"
    bearer = {"Authorization": "Bearer fixture-backend-bearer"}
    owner = {**bearer, "X-AlphaOS-Data-Use": "owner_private_display"}
    assert client.post(endpoint).status_code == 401
    assert client.post(endpoint, headers=bearer).status_code == 403
    service.provider.name = "not-entitled"
    assert client.post(endpoint, headers=owner).status_code == 403
    assert requests == []
    service.provider.name = "Public"
    result = client.post(endpoint, headers=owner)
    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"
    assert result.json()["symbol"] == "QQQ"
    assert requests == [("QQQ", "5m", "owner_private_display")]


def test_daily_context_requires_immediate_prior_session_and_original_availability():
    snap = fixture(final=None)
    snap = replace(snap, candles=snap.candles[78:])
    daily = PriorSession("SPY", "2026-11-18", "Public", AS_OF.isoformat(), 511, 489, 500)
    view, theses, _ = evaluate(snap, AS_OF, daily)
    assert {level["low"] for level in view["levels"]} == {489, 500, 511}
    assert not theses
    for wrong in (replace(daily, session="2026-11-17"), replace(daily, symbol="QQQ"),
                  replace(daily, observed_at=(AS_OF + BAR).isoformat())):
        assert not evaluate(snap, AS_OF, wrong)[0]["levels"]


def test_bearish_invalidation_and_complete_vs_missing_expiration(tmp_path):
    journal = PlaybookJournal(tmp_path / "terminal.sqlite")
    observe(journal, AS_OF)
    first = observe(journal, AS_OF + 2 * BAR, breakdown=True)
    down = next(row for row in first if row["thesis"]["family"] == "breakdown")
    assert down["state"] == "CONFIRMED"
    now = AS_OF + 3 * BAR
    snap = fixture(now=now, breakdown=True)
    old_bar = snap.candles[-1]
    snap = replace(snap, candles=snap.candles[:-1] + (replace(old_bar, high=502, close=501),))
    view, _, bars = evaluate(snap, now)
    records = journal.observe("SPY", [], bars, now, view["provenance"], "Public")
    assert next(row for row in records if row["thesis"]["family"] == "breakdown")["state"] == "INVALIDATED"
    # Poll every remaining bar for SPY but leave QQQ without coverage.
    observe(journal, AS_OF, symbol="QQQ")
    now += BAR
    while now <= CLOSE:
        observe(journal, now, breakdown=True)
        now += BAR
    assert {row["state"] for row in journal.observe("SPY", [], [], now + BAR, None, "Public")} == {
        "EXPIRED", "INVALIDATED",
    }
    assert {row["state"] for row in journal.observe("QQQ", [], [], now + BAR, None, "Public")} == {"UNRESOLVED"}


def test_hosted_journal_recomputes_on_revision_conflict_and_preserves_thesis():
    from copy import deepcopy

    class Transport:
        records = []
        revision = 0
        first_write = True

        def market_playbook_journal(self, params, expected, updates):
            assert params["p_symbol"] == "SPY"
            reply = {"records": deepcopy(self.records), "revision": str(self.revision), "applied": False}
            if expected != str(self.revision):
                return reply
            for update in updates:
                if "thesis" in update:
                    self.records.append({"thesis": update["thesis"], "events": []})
                record = next(row for row in self.records if row["thesis"]["id"] == update["id"])
                assert update["after"] == len(record["events"])
                record["events"].extend(update["events"])
            self.revision += 1
            if self.first_write:
                # Model another writer committing the same proposal first.
                self.first_write = False
                return {"records": deepcopy(self.records), "revision": str(self.revision), "applied": False}
            return {**reply, "applied": True}

    transport = Transport()
    original = observe(SupabasePlaybookJournal(transport), AS_OF)
    latest = observe(SupabasePlaybookJournal(transport), AS_OF + 2 * BAR, breakout=True)
    assert [row["thesis"] for row in latest] == [row["thesis"] for row in original]
    assert {row["state"] for row in latest} == {"CONFIRMED", "WAITING"}
    assert observe(SupabasePlaybookJournal(transport), AS_OF + 2 * BAR, breakout=True) == latest
