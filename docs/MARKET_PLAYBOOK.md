# Market Playbook v1

The existing Trading Workspace has a Market Playbook section below its main panels. It follows the workspace SPY/QQQ selector. Opening the section polls the Render observation endpoint once a minute for the selected symbol. Closing it stops polling. Prior sessions show the original thesis and recorded outcomes. Gaps in observation can leave open theses unresolved.

## Evidence and rules

- Reuses the normalized native five-minute candle service, the NYSE exchange calendar, the existing 15-minute opening-range convention, the cached Public completed-daily dataset, and the website's signed owner session and Render bearer transport.
- Previous-session high, low and close require the immediately preceding NYSE session. The engine uses a fully provider-confirmed five-minute session when present and otherwise uses matching completed daily OHLC. Swing pivots require two confirmed bars on each side. A role flip requires a confirmed close through the zone followed by a confirmed swing retest from the opposite side.
- Fixed levels within 20% of the median range of the latest 14 confirmed five-minute bars cluster, with a one-cent minimum. Zones are bounded by actual observation prices. Ranking sorts by distinct originating timestamps, then distinct swing reactions, then structural weight (prior session, opening range, swing), then recency and price. An opening-range extreme and a pivot from the same candle count once. Each zone retains source, observation times, and native snapshot provenance.
- Session VWAP uses the typical-price weighted average of contiguous bars with positive volume. It is a dynamic reference. A time-closed opening range or VWAP can be labeled provisional when provider finality is missing. Provisional values are excluded from trigger and target selection. Descriptive bias compares the latest confirmed close with VWAP and the close two intervals earlier.
- Each direction requires two verified zones beyond the current close to define the trigger and first target. Strong evidence requires repeated observations at the trigger zone and matching bias. Mixed reflects weaker or conflicting evidence. Insufficient means usable evidence is missing. A directional bias cannot change lifecycle state.
- The first eligible thesis per direction, provider, symbol, session and rules version is frozen. A later, fully post-creation, provider-confirmed five-minute close strictly through the trigger records CONFIRMED. Subsequent confirmed closes can invalidate beyond the opposite zone edge or complete at or beyond the target. The triggering candle cannot also record an outcome. The session window closes on the NYSE schedule, with five minutes to receive the final observation. A fully observed thesis that never triggered expires. Missing coverage or a triggered thesis without a verified outcome becomes unresolved. The journal appends one event per processed candle and terminal decision.

## Storage and hosting

Both research and owner-private-display data-use policies must allow the provider. The browser reaches the endpoint through the existing same-origin owner and CSRF checks. Backend responses use the existing authenticated Render router. The Supabase journal uses private tables and a service-role-only RPC with atomic revision checks. Its service-role grants allow reads and inserts. Store configuration and credentials stay on Render.

After approval, apply the journal migration to the existing nonproduction Supabase environment, set `ALPHAOS_PLAYBOOK_JOURNAL=supabase` on its existing Render backend, and set `ALPHAOS_MARKET_PLAYBOOK_ENABLED=true` on the authorized Netlify context after deploying matching code. Use the existing Supabase URL and service role, Render bearer token, and signed owner session. For local testing only, `ALPHAOS_PLAYBOOK_DB` accepts an absolute SQLite path in a private directory. Confirm that signed-out and viewer requests are denied, switch both symbols during a regular session, verify freshness and provenance, then restart the backend and verify journal readback.

The current Public feed has been observed without provider finality. Verify that production-like data stays in WAIT when no final candles are available. To validate transitions with live data, an entitled feed must supply provider-confirmed candles on time. The first slice implements breakout and breakdown. Retest, reclaim, rejection and continuation families are future work.

## Historical replay

Call `modules.market_playbook_replay.replay` with recorded native snapshots, a fresh `PlaybookJournal` database, a fixed chronological holdout start, and a predefined universe of expected NYSE session, symbol and provider tuples. Include sessions with no data in the universe. Optional `prior_by_snapshot` supplies completed daily OHLC with its original observation time. Replay defaults to each snapshot's recorded retrieval time. Supply original decision timestamps in `decision_by_snapshot` when daily context arrived later. Replay rejects evidence observed after the simulated decision. Use archived snapshots from the original observation stream, including revisions and provider finality; downloading a completed historical series today cannot establish past availability.

The report includes generated and triggered counts, outcome shares, target rate among triggered theses, median elapsed time for verified outcomes, and session coverage. It groups the results by symbol, family and creation-time directional regime and reports development and chronological holdout partitions. Missing observations stay visible in coverage. The fixture tests exercise the replay mechanism. Calibration requires real point-in-time samples across regimes. Outcomes represent underlying five-minute closes and contain no options execution or profitability estimates.

## Deterministic examples

These fixture observations use the November 19, 2026 NYSE session at 10:05 a.m. ET. All scenarios begin in WAIT. For these single-price trigger zones, invalidation is a subsequent close back across the trigger after confirmation.

| Symbol | Bullish trigger and target | Bearish trigger and target | Evidence |
| --- | --- | --- | --- |
| SPY | Close above 505.00 → 512.00 | Close below 500.00 → 498.00 | Opening-range high and prior high above spot. Prior close and confirmed swing low below spot. |
| QQQ | Close above 435.00 → 442.00 | Close below 430.00 → 428.00 | Same fixture structure with independent QQQ observations and journal identities. |
