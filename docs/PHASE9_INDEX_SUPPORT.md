# Phase 9 index support

Extends Phase 9A (`92ed110`) using verified direct Public SPX/XSP observations. The same 14 MCP tools and REST endpoints now accept SPY, QQQ, SPX and XSP. OAuth, consent, CSP, CIMD, DCR, quote-freshness rules and quantitative calculations are unchanged.

## Verified mapping

| Canonical | Request symbol/type | History/chain response | Accepted option root | Default wing | Multiplier |
|---|---|---|---|---|---|
| SPY | SPY / EQUITY | SPY | SPY | 1 | 100 |
| QQQ | QQQ / EQUITY | QQQ | QQQ | 1 | 100 |
| SPX | SPX / INDEX | SPX-INDEX | SPXW | 5 | 100 |
| XSP | XSP / INDEX | XSP-INDEX | XSP | 1 | 100 |

Public's documented UNDERLYING_SECURITY_FOR_INDEX_OPTION type returned HTTP 400 for both indices. INDEX requests succeeded for quotes, history, expirations and chains. The implementation uses observed behavior, not a documentation-only assumption. No proxy or price scaling is applied. Public's index quotes use canonical SPX/XSP, while history and option envelopes use the exact -INDEX identifiers; only the verified mappings are accepted.

September 29, 2026 audit: SPX 7671.67 at 15:16:26 UTC, XSP 767.20 at 15:16:28 UTC; bid/ask absent, previous closes 7683.69/768.37. Both returned 1,255 daily observations from September 29, 2021. Expiration counts were 41/48, including same-day, 1-day and 2-day chains. Both sides contained quote timestamps and Greeks. Minimum observed strike intervals were 5/1 points; intervals varied across the chain. Audit: https://github.com/rooster51/AlphaOS/actions/runs/36588903687

## Research and safeguards

`modules/symbol_registry.py` centralizes supported identities, provider type/response mapping, accepted roots, wing defaults and contract characteristics. Existing eligibility checks consume it; analog selection, structure detection, threshold research, distributions and scenario formulas are unchanged. Direct index history receives the existing full-history coverage validation; today's incomplete bar is excluded. Provider identifiers remain in history diagnostics.

Fresh last index values can anchor research even without underlying bid/ask. Execution-sensitive underlying bid/ask usability stays false. Existing quote age/session policy is reused; this does not verify index-option global-hours availability or real-time entitlement. Option-leg bid/ask validity and timestamps remain separate evidence.

Live SPX contracts must have root SPXW; XSP must have root XSP. Date, put/call and strike validation remain strict. Unverified roots return unsupported_contract_root. Public does not expose per-contract settlement timing in the consumed quote/chain responses. Cash settlement and European exercise are exchange-specification descriptions, not provider-verified settlement metadata. Daily terminal-price scenarios are not official settlement-value backtests. SPX AM-settled roots are not silently treated as SPXW.

Both index products use a 100-dollar multiplier per point. Existing credit*100, (width-credit)*100, breakeven and RoR formulas therefore remain unchanged. XSP prices are already in XSP units: never divide them by ten again. Sources: https://www.cboe.com/tradable-products/sp-500/spx-options/spx-specifications and https://www.cboe.com/tradable-products/sp-500/xsp-options/specifications

Run SPX defaults to a 5-point wing; other registered symbols retain 1. A requested unavailable index wing is excluded with requested_wing_unavailable; no synthetic strike or nearest-width substitution is presented. All candidates retain generator order. Index defaults do not change SPY/QQQ generator behavior.

DTE uses America/New_York dates. A 0DTE request must specify dte_min=0 and dte_max=0 (or today's explicit listed expiration). The default Run workflow retains 1-7 calendar DTE and 3 observed research sessions. Daily analog horizons do not become intraday or expiration-matched profit probabilities.

All five unified sections retain live/research-state separation. Instrument metadata appears in unified snapshots, orchestration and granular REST metadata. The existing Streamlit research selectors accept the registry symbols; no Streamlit cloud branch change is implied by a Render deployment. Scheduled archives remain scoped to their existing SPY/QQQ configuration.

## Validation

Deterministic tests cover registry, exact provider mappings, complete direct history, strict roots, option calls/puts/Greeks/timestamps, missing bid/ask, stale stops, UTC/local date boundaries, 0/1/2 DTE, PCS/CCS economics, actual wing widths, structure scale, analogs, unified level/payoff evidence and REST/MCP serialization with 14 tools. Live validation uses the existing GitHub secrets inside the runner; credentials never leave it. PUBLIC_API contains whitespace, so diagnostic scripts strip outer whitespace before authentication. This does not alter production authentication.

Production remains pinned until regression tests and CI pass. Never merge automatically. Actual ChatGPT natural-language validation is separate from server tests.
