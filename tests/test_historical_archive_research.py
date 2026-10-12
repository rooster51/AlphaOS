from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
from types import SimpleNamespace

import pytest

from modules.historical_archive_research import evaluate_historical_archive_research
from modules.premium_engine import payoff
from modules.structure_research import research_structure
from modules.supabase_archive import read_option_snapshot_window
from tests.test_mcp_api import call, login
from tests.test_research2_api import boundary, post


ENTRY_START = "2026-10-08T14:30:00+00:00"
ENTRY_END = "2026-10-08T14:35:00+00:00"
EXIT_START = "2026-10-08T15:00:00+00:00"
EXIT_END = "2026-10-08T15:05:00+00:00"
NOW = datetime.fromisoformat("2026-10-09T20:00:00+00:00")
EXPIRATION = "2026-10-16"


def contract(symbol, expiration, kind, strike):
    encoded = int(strike * 1000)
    side = "C" if kind == "Call" else "P"
    return f"{symbol}{datetime.fromisoformat(expiration).strftime('%y%m%d')}{side}{encoded:08d}"


def option_row(symbol, expiration, kind, strike, bid, ask, observed_at, quote_at=None):
    quote_at = quote_at or observed_at - timedelta(seconds=5)
    return dict(symbol=symbol, contract=contract(symbol, expiration, kind, strike),
        expiration=expiration, type=kind, strike=float(strike), bid=float(bid), ask=float(ask),
        bid_timestamp=quote_at.isoformat(), ask_timestamp=quote_at.isoformat(),
        observed_at=observed_at.isoformat(), quote_outcome="SUCCESS",
        rejection_reasons=[], quality_warnings=[])


class SnapshotStore:
    def __init__(self):
        self.rows = []
        self.objects = {}
        self.storage = self
        self.filters = {}
        self.orders = []
        self.row_limit = None

    def table(self, name):
        assert name == "option_snapshots"
        self.filters, self.orders, self.row_limit = {}, [], None
        return self

    def select(self, fields):
        assert fields == "*"
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def lte(self, key, value):
        self.filters[key] = ("lte", datetime.fromisoformat(value.replace("Z", "+00:00")))
        return self

    def gte(self, key, value):
        self.filters[key] = ("gte", datetime.fromisoformat(value.replace("Z", "+00:00")))
        return self

    def order(self, key, desc=False):
        self.orders.append((key, desc))
        return self

    def limit(self, value):
        self.row_limit = value
        return self

    def execute(self):
        rows = list(self.rows)
        for key, expected in self.filters.items():
            if isinstance(expected, tuple):
                cutoff = expected[1]
                operator = expected[0]
                rows = [row for row in rows if (
                    datetime.fromisoformat(row[key].replace("Z", "+00:00")) <= cutoff
                    if operator == "lte" else
                    datetime.fromisoformat(row[key].replace("Z", "+00:00")) >= cutoff)]
            else:
                rows = [row for row in rows if row.get(key) == expected]
        for key, descending in reversed(self.orders):
            rows.sort(key=lambda row: row[key], reverse=descending)
        return SimpleNamespace(data=rows[:self.row_limit])

    def from_(self, bucket):
        assert bucket == "market-archive"
        return self

    def download(self, path):
        return self.objects[path]

    def add(self, observed_at, prices, *, status="complete", rejected=(), defect=None):
        observed = datetime.fromisoformat(observed_at)
        session = observed.astimezone(timezone(timedelta(hours=-4))).date().isoformat()
        quote_time = observed - timedelta(seconds=5)
        rows = [option_row("QQQ", EXPIRATION, kind, strike, bid, ask,
            quote_time, quote_time - timedelta(seconds=5))
            for kind, strike, bid, ask in prices]
        options = dict(symbol="QQQ", snapshot_date=session, status=status,
            collection_started_at=(observed + timedelta(seconds=1)).isoformat(),
            generated_at=(observed + timedelta(seconds=8)).isoformat(),
            valid_contracts=rows, questionable_contracts=[],
            rejected_contracts=list(rejected))
        payload = dict(provider="Public", symbol="QQQ", session=session,
            observed_at=observed.isoformat(), collection_finished_at=(observed + timedelta(seconds=10)).isoformat(),
            options=options)
        raw = gzip.compress(json.dumps(payload, sort_keys=True).encode(), mtime=0)
        path = f"options/symbol=QQQ/date={session}/{observed.strftime('%H%M%S')}.json.gz"
        record = dict(id=observed.isoformat(), provider="Public", symbol="QQQ",
            observed_at=observed.isoformat(), session_date=session,
            created_at=(observed + timedelta(seconds=12)).isoformat(),
            quality_status=status, archive_path=path,
            archive_sha256=hashlib.sha256(raw).hexdigest())
        if defect == "checksum":
            record["archive_sha256"] = "0" * 64
        if defect == "metadata_symbol":
            record["symbol"] = "SPY"
        if defect == "metadata_session":
            record["session_date"] = "2026-10-07"
        self.rows.append(record)
        self.objects[path] = raw
        return rows


def reader_for(store):
    return lambda symbol, start, end: read_option_snapshot_window(
        store, symbol, start, end, max_age_seconds=600)


def setup_store(*, include_older=True, defect=None):
    store = SnapshotStore()
    if include_older:
        store.add("2026-10-08T14:32:30+00:00",
            [("Call", 500, 3, 4), ("Put", 500, 2, 3),
             ("Put", 490, 1, 2), ("Call", 510, 1, 2)])
    entry = store.add("2026-10-08T14:34:30+00:00",
        [("Call", 500, 4, 5), ("Put", 500, 3, 4),
         ("Put", 490, 2, 3), ("Call", 510, 2, 3)], defect=defect)
    store.add("2026-10-08T15:02:30+00:00",
        [("Call", 500, 5, 6), ("Put", 500, 3, 4),
         ("Put", 490, 2, 3), ("Call", 510, 2, 3)])
    exit_rows = store.add("2026-10-08T15:04:30+00:00",
        [("Call", 500, 7, 8), ("Put", 500, 2, 3),
         ("Put", 490, 1, 2), ("Call", 510, 3, 4)])
    return store, entry, exit_rows


def rewrite_snapshot(store, observed_at, change):
    record = next(row for row in store.rows if row["observed_at"] == observed_at)
    raw = store.objects[record["archive_path"]]
    payload = json.loads(gzip.decompress(raw).decode())
    change(payload)
    raw = gzip.compress(json.dumps(payload, sort_keys=True).encode(), mtime=0)
    store.objects[record["archive_path"]] = raw
    record["archive_sha256"] = hashlib.sha256(raw).hexdigest()


def trade(legs=None, credit=-1, fees=2):
    return dict(symbol="QQQ", expiration=EXPIRATION, spot=500, credit=credit,
        fees=fees, shares=0, source="Explicit test structure",
        legs=legs or [dict(type="Call", strike=500, qty=1)])


def windows():
    return (dict(start=ENTRY_START, end=ENTRY_END),
            dict(start=EXIT_START, end=EXIT_END))


def evaluate(store, candidate=None, entry=None, exit_=None, now=NOW):
    default_entry, default_exit = windows()
    return evaluate_historical_archive_research(candidate or trade(),
        entry_window=entry or default_entry, exit_window=exit_ or default_exit,
        read_snapshots=reader_for(store), now=now)


def test_latest_snapshot_within_each_caller_window_and_conservative_cashflows():
    store, entry_rows, exit_rows = setup_store()
    calls = []

    def reader(symbol, start, end):
        calls.append((start, end))
        return reader_for(store)(symbol, start, end)

    result = evaluate_historical_archive_research(trade(), entry_window=windows()[0],
        exit_window=windows()[1], read_snapshots=reader, now=NOW)
    assert result["status"] == "complete"
    assert calls == [(ENTRY_START, ENTRY_END), (EXIT_START, EXIT_END)]
    assert result["provenance"]["entry"]["observed_at"] == "2026-10-08T14:34:30+00:00"
    assert result["provenance"]["exit"]["observed_at"] == "2026-10-08T15:04:30+00:00"
    assert result["contracts"][0]["contract"] == entry_rows[0]["contract"]
    assert result["contracts"][0]["entry_quote"]["ask"] == 5
    assert result["contracts"][0]["exit_quote"]["bid"] == 7
    assert result["pnl_dollars"] == pytest.approx(198)
    assert all(len(result["provenance"][key]["archive_sha256"]) == 64 for key in ("entry", "exit"))
    json.dumps(result, allow_nan=False)


def test_latest_eligible_snapshot_falls_back_with_reported_rejection():
    store, _, _ = setup_store()
    rewrite_snapshot(store, "2026-10-08T14:34:30+00:00",
        lambda payload: payload["options"]["valid_contracts"][0].update(
            bid_timestamp="2026-10-08T14:30:00+00:00"))
    result = evaluate(store)
    assert result["status"] == "complete"
    assert result["provenance"]["entry"]["observed_at"] == "2026-10-08T14:32:30+00:00"
    assert "ineligible_snapshots_skipped" in result["warnings"]
    assert "stale_bid_quote" in {
        item["code"] for item in result["rejection_report"]["entry"]}


@pytest.mark.parametrize("legs,credit,family", [
    ([dict(type="Put", strike=500, qty=1), dict(type="Call", strike=500, qty=1)], -4, "long_straddle"),
    ([dict(type="Put", strike=490, qty=1), dict(type="Call", strike=510, qty=1)], -4, "long_strangle"),
    ([dict(type="Put", strike=500, qty=-1), dict(type="Call", strike=500, qty=-1)], 4, "short_straddle"),
    ([dict(type="Put", strike=490, qty=-1), dict(type="Call", strike=510, qty=-1)], 4, "short_strangle"),
])
def test_straddles_and_strangles_reuse_deterministic_payoff_engine(legs, credit, family):
    candidate = trade(legs, credit=credit)
    result = research_structure(candidate, symbol="QQQ", spot=500, as_of="2026-10-08")
    assert result["strategy_family"] == family
    for scenario in result["payoff"]["grid"]:
        assert scenario["Expiration P&L ($)"] == pytest.approx(payoff(
            result["trade"]["legs"], credit, scenario["Terminal underlying ($)"], fees=candidate["fees"]))


@pytest.mark.parametrize("defect,code", [
    ("checksum", "archive_unavailable"),
    ("metadata_symbol", "no_snapshot_in_window"),
    ("metadata_session", "archive_unavailable"),
])
def test_checksum_and_archive_identity_failures_are_reported(defect, code):
    store, _, _ = setup_store(include_older=False, defect=defect)
    result = evaluate(store)
    assert result["status"] == "rejected"
    assert code in {entry["code"] for entry in result["rejection_report"]["entry"]}
    assert result["pnl_dollars"] is None


@pytest.mark.parametrize("defect,code", [
    ("contract_symbol", "contract_identity_mismatch"),
    ("stale_quote", "stale_bid_quote"),
    ("future_quote", "future_bid_timestamp"),
    ("missing_quote", "missing_bid_timestamp"),
    ("rejected", "archived_contract_rejected"),
])
def test_contract_identity_freshness_and_archive_rejections_are_visible(defect, code):
    store, entry_rows, _ = setup_store(include_older=False)
    if defect == "contract_symbol":
        rewrite_snapshot(store, "2026-10-08T14:34:30+00:00",
            lambda payload: payload["options"]["valid_contracts"][0].update(symbol="SPY"))
    elif defect in ("stale_quote", "future_quote", "missing_quote"):
        if defect == "stale_quote":
            value = "2026-10-08T14:30:00+00:00"
        elif defect == "future_quote":
            value = "2026-10-08T14:35:00+00:00"
        else:
            value = None
        rewrite_snapshot(store, "2026-10-08T14:34:30+00:00",
            lambda payload: payload["options"]["valid_contracts"][0].update(bid_timestamp=value))
    elif defect == "rejected":
        def reject_target(payload):
            target = payload["options"]["valid_contracts"].pop(0)
            payload["options"]["rejected_contracts"].append(dict(target,
                rejection_reasons=["crossed_bid_ask"]))
        rewrite_snapshot(store, "2026-10-08T14:34:30+00:00", reject_target)
    result = evaluate(store)
    assert result["status"] == "rejected"
    assert code in {entry["code"] for entry in result["rejection_report"]["entry"]}
    assert result["pnl_dollars"] is None


@pytest.mark.parametrize("entry,exit_,code", [
    (dict(start="2026-10-08T20:00:00+00:00", end="2026-10-08T20:01:00+00:00"),
     dict(start=EXIT_START, end=EXIT_END), "window_outside_regular_nyse_session"),
    (dict(start="2026-10-08T19:59:00+00:00", end="2026-10-09T14:31:00+00:00"),
     dict(start=EXIT_START, end=EXIT_END), "window_outside_regular_nyse_session"),
    (dict(start="2026-10-08T14:35:00+00:00", end=ENTRY_END),
     dict(start="2026-10-08T14:34:00+00:00", end=EXIT_END), "windows_not_chronological"),
])
def test_windows_must_be_ordered_and_inside_exchange_sessions(entry, exit_, code):
    store, _, _ = setup_store()
    result = evaluate(store, entry=entry, exit_=exit_)
    assert code in {item["code"] for rows in result["rejection_report"].values() for item in rows}
    assert result["pnl_dollars"] is None


def test_rest_mcp_archive_evaluation_is_additive_and_identical(boundary):
    client, _, service, _ = boundary
    store, _, _ = setup_store()
    service.read_snapshots = reader_for(store)
    structure = dict(symbol="QQQ", expiration=EXPIRATION, as_of="2026-10-08",
        spot=500, credit=-1, fees=2, legs=[dict(type="Call", strike=500, qty=1)])
    body = dict(structure=structure,
        entry_window=dict(start=ENTRY_START, end=ENTRY_END),
        exit_window=dict(start=EXIT_START, end=EXIT_END))
    response = post(client, "structure/historical-archive", body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["research"]["historical_archive_research"]["status"] == "complete"
    assert result["research"]["historical_archive_research"]["pnl_dollars"] == pytest.approx(198)

    _, tokens = login(client)
    tool_result = call(client, tokens["access_token"], "research_historical_archive",
        {"research": body})
    assert not tool_result.get("isError"), tool_result
    assert tool_result["structuredContent"] == result

    legacy = post(client, "structure", structure)
    assert legacy.status_code == 200
    assert "historical_archive_research" not in legacy.json()["research"]
    assert set(legacy.json()["request"]) == set(structure)
