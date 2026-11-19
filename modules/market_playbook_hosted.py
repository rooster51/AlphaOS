"""Durable market playbook storage through AlphaOS's existing Supabase transport."""
from modules.market_playbook import stamp
from modules.market_playbook_store import events_after, journal_record


class MarketPlaybookStorageError(RuntimeError):
    """A sanitized storage failure or exhausted concurrent-write retries."""


class SupabasePlaybookJournal:
    def __init__(self, client):
        self.client = client

    def observe(self, symbol, proposals, bars, now, provenance, provider):
        params = {"p_symbol": symbol, "p_provider": provider, "p_as_of": now.date().isoformat()}
        snapshot = self.client.market_playbook_journal(params, None, [])
        for _ in range(3):
            if not isinstance(snapshot, dict) or not isinstance(snapshot.get("records"), list) or not isinstance(
                snapshot.get("revision"), str
            ):
                raise MarketPlaybookStorageError("Invalid journal response.")
            records = {row["thesis"]["id"]: (row["thesis"], row["events"]) for row in snapshot["records"]}
            new = {thesis["id"]: thesis for thesis in proposals if thesis["id"] not in records}
            records.update({identity: (thesis, []) for identity, thesis in new.items()})
            updates, history = [], []
            for identity, (thesis, events) in sorted(
                records.items(), key=lambda item: (-int(item[1][0]["session"].replace("-", "")), item[0])
            )[:20]:
                if stamp(thesis["created_at"]) > now or (events and stamp(events[-1]["recorded_at"]) > now):
                    continue
                appended = list(events_after(thesis, events, bars, now, provenance))
                if identity in new or appended:
                    change = {"id": identity, "after": len(events), "events": appended}
                    if identity in new:
                        change["thesis"] = thesis
                    updates.append(change)
                history.append(journal_record(thesis, events + appended))

            if not updates:
                return history
            snapshot = self.client.market_playbook_journal(params, snapshot["revision"], updates)
            if isinstance(snapshot, dict) and snapshot.get("applied") is True:
                return history
        raise MarketPlaybookStorageError("Concurrent journal writes did not settle.")
