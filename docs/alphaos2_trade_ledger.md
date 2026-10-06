# AlphaOS 2.0 Trade Ledger

**Status: FOUNDATION ONLY — NOT DEPLOYED.**

This document describes the intended future journal. The existing
`supabase/alphaos2_trade_ledger.sql` foundation is not applied by API startup or
Render deployment. This milestone does not apply it or enable journal tools.
Live database state has not been independently inspected in the readiness audit.

The future AlphaOS trade ledger will be the authoritative server-side record of
positions and trading activity across every interface. It must persist across
separate ChatGPT conversations, MCP sessions, and future web/mobile interfaces;
ChatGPT memory must never be the system of record.

## Intended future capability

Support opening, closing, partial closes, adjustments and rolls of multi-leg
positions. Persist entry and exit credit/debit, fees, quantity, symbol, strategy,
strikes, expiration, timestamps, user thesis/notes, realized P&L and final outcome.
Retain position lifecycle events and frozen research snapshots both at entry and
during the position's life.

Future queries should show open and closed trades, running P&L, iron-condor
performance, win rate by strategy, average winner/loser, expectancy, performance
by symbol and DTE, capital efficiency, drawdown, and research-at-entry versus
actual outcome. These are planned capabilities, not available API/MCP tools.

Implementation order: Persistent Trade Journal -> Journal Analytics -> Position
Monitor -> Portfolio/Scenario Risk Engine -> Calibration / research-vs-outcome
analysis. No part of that implementation is included in the production-readiness
documentation task.

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
