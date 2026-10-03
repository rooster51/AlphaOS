# AlphaOS 2.0 Trade Ledger

The AlphaOS trade ledger is the authoritative record of positions and trading activity across every interface.

## Principles

- AlphaOS owns the journal. ChatGPT, Streamlit, future web, mobile, and API clients are interfaces to the same ledger.
- A position is the clean user-facing lifecycle. Events are the immutable audit trail underneath it.
- Entry research is frozen in a research snapshot so future model changes cannot rewrite what AlphaOS knew at entry.
- The legacy `trades` table remains untouched during migration.
- Critical execution details must never be guessed. Interfaces may resolve unambiguous conversational context, but ambiguous trades require clarification.

## Core records

### trade_positions
One readable position lifecycle: symbol, strategy family, open/closed state, quantity, entry snapshot, notes, metadata.

### trade_position_legs
Normalized option legs for the position. This supports one-leg options through multi-leg structures without strategy-specific database tables.

### trade_events
Immutable lifecycle events: entry, add, partial exit, adjust, roll, close, fee, note, correction.

### trade_research_snapshots
Frozen evidence/model state linked to entry or later events.

## Conversational target

“I entered QQQ 747/746 PCS at .18, 2 contracts.”

When context supplies a unique expiration, AlphaOS should normalize the legs, create the position, freeze the entry research snapshot, append the entry event, and return the persisted position ID. If expiration or another critical field is ambiguous, no write occurs until clarified.

“Closed one at .05.”

AlphaOS appends a partial_exit event and keeps the position open.

“Closed the other at .03.”

AlphaOS appends a close event, closes the position, and performance analytics derive realized results from the event history.

## Interface rule

No interface owns a private journal. All interfaces use the same AlphaOS ledger API.
