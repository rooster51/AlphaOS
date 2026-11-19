"""Append-only SQLite journal for one durable Render service instance."""
from __future__ import annotations

from contextlib import closing
from datetime import datetime
import json
from pathlib import Path
import sqlite3

from modules.market_playbook import BAR, MAX_AGE, next_interval, stamp


def events_after(thesis, events, bars, now, provenance):
    """Use post-creation, contiguous confirmed closes and record each decision once."""
    last = events[-1] if events else None
    if last and last["state"] not in ("WAITING", "CONFIRMED"):
        return
    state = last["state"] if last else "WAITING"
    expected = stamp(last["bar_at"]) + BAR if last else next_interval(stamp(thesis["created_at"]))
    expires = stamp(thesis["expires_at"])
    direction = 1 if thesis["direction"] == "bullish" else -1
    timely = stamp(provenance["retrieved_at"]) if provenance else now
    for bar in bars:
        at = stamp(bar.time)
        if at < expected:
            continue
        if at != expected or at >= expires or timely - (at + BAR) > MAX_AGE:
            break
        close = bar.close
        if state == "WAITING":
            if direction * (close - thesis["trigger"]) > 0:
                state = "CONFIRMED"
        elif direction * (close - thesis["invalidation"]) < 0:
            state = "INVALIDATED"
        elif direction * (close - thesis["target"]) >= 0:
            state = "COMPLETED"
        yield {"state": state, "recorded_at": now.isoformat(), "bar_at": bar.time,
               "close": close, "provenance": provenance}
        expected += BAR
        if state in ("INVALIDATED", "COMPLETED"):
            return

    if now > expires + BAR:
        terminal = "EXPIRED" if state == "WAITING" and expected >= expires else "UNRESOLVED"
        reason = (
            "A complete observation window ended without a confirmed trigger." if terminal == "EXPIRED"
            else "The session ended before a verified target or invalidation."
            if expected >= expires else "The observation window has missing or late confirmed candles."
        )
        yield {"state": terminal, "recorded_at": now.isoformat(), "bar_at": None, "reason": reason}


def journal_record(thesis, events):
    return {
        "thesis": thesis, "events": events,
        "state": events[-1]["state"] if events else "WAITING",
        "updated_at": events[-1]["recorded_at"] if events else thesis["created_at"],
    }


class PlaybookJournal:
    def __init__(self, database):
        self.path = Path(database)
        if not self.path.is_absolute() or not self.path.parent.is_dir():
            raise ValueError("An absolute journal path in an existing private durable directory is required.")

    def observe(self, symbol, proposals, bars, now: datetime, provenance, provider):
        with closing(sqlite3.connect(self.path, timeout=5)) as connection, connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS playbook_thesis (
                    id TEXT PRIMARY KEY, symbol TEXT NOT NULL, provider TEXT NOT NULL,
                    session TEXT NOT NULL, snapshot TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS playbook_history
                    ON playbook_thesis(symbol, provider, session);
                CREATE TABLE IF NOT EXISTS playbook_event (
                    thesis_id TEXT NOT NULL, sequence INTEGER NOT NULL, event TEXT NOT NULL,
                    PRIMARY KEY (thesis_id, sequence)
                );
                CREATE TRIGGER IF NOT EXISTS thesis_no_update BEFORE UPDATE ON playbook_thesis
                    BEGIN SELECT RAISE(ABORT, 'append-only thesis'); END;
                CREATE TRIGGER IF NOT EXISTS thesis_no_delete BEFORE DELETE ON playbook_thesis
                    BEGIN SELECT RAISE(ABORT, 'append-only thesis'); END;
                CREATE TRIGGER IF NOT EXISTS event_no_update BEFORE UPDATE ON playbook_event
                    BEGIN SELECT RAISE(ABORT, 'append-only event'); END;
                CREATE TRIGGER IF NOT EXISTS event_no_delete BEFORE DELETE ON playbook_event
                    BEGIN SELECT RAISE(ABORT, 'append-only event'); END;
            """)
            connection.execute("BEGIN IMMEDIATE")
            for thesis in proposals:
                connection.execute(
                    "INSERT INTO playbook_thesis VALUES (?, ?, ?, ?, ?) ON CONFLICT(id) DO NOTHING",
                    (thesis["id"], symbol, provider, thesis["session"], json.dumps(thesis)),
                )
            history = []
            rows = connection.execute(
                """SELECT id, snapshot FROM playbook_thesis WHERE symbol = ? AND provider = ?
                   AND session <= ? ORDER BY session DESC, id LIMIT 20""",
                (symbol, provider, now.date().isoformat()),
            )
            for identity, stored in rows:
                thesis = json.loads(stored)
                if stamp(thesis["created_at"]) > now:
                    continue
                events = [
                    json.loads(row[0]) for row in connection.execute(
                        "SELECT event FROM playbook_event WHERE thesis_id = ? ORDER BY sequence",
                        (identity,),
                    )
                ]
                if events and stamp(events[-1]["recorded_at"]) > now:
                    continue
                for event in events_after(thesis, events, bars, now, provenance):
                    connection.execute(
                        "INSERT INTO playbook_event VALUES (?, ?, ?)",
                        (identity, len(events), json.dumps(event)),
                    )
                    events.append(event)
                history.append(journal_record(thesis, events))
        return history
