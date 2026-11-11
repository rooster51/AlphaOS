# Phase D — Gemini candle synchronization contract

Status: contract specification only. No Gemini client, prompt, tool, or frontend
synchronization is implemented in this run.

## Shared source of truth

Gemini and the chart must consume the same server-owned candle snapshot. The
browser must never submit a candle array as authoritative evidence, and Gemini
must never claim to inspect a chart it did not receive. The server selects the
snapshot, verifies its provenance and entitlement, and supplies the bounded
observation payload.

The existing Public policy has `ai_analysis: false`. Therefore Public candle
observations must not be sent to Gemini until a documented authorization exists
and the server entitlement is deliberately updated. The assistant surface must
fail closed when the policy check fails.

## Proposed request envelope

The server builds this envelope from an authenticated `alphaos-candles-v1`
snapshot. It is not accepted verbatim from the browser.

```json
{
  "schema_version": "alphaos-chart-evidence-v1",
  "snapshot_id": "server-owned-sha256",
  "symbol": "SPY",
  "interval": "5m",
  "session": "regular",
  "retrieved_at": "2026-10-02T20:05:00+00:00",
  "latest_candle_at": "2026-10-02T19:55:00+00:00",
  "completeness": "complete",
  "last_bar_status": "complete",
  "freshness": "fresh",
  "warnings": [],
  "candles": [
    {
      "time": "2026-10-02T19:55:00+00:00",
      "open": 600.0,
      "high": 601.0,
      "low": 599.5,
      "close": 600.5,
      "volume": 12500.0
    }
  ],
  "indicators": {
    "ema": [
      {"period": 9, "values": [{"time": "2026-10-02T13:55:00+00:00", "value": 600.2}]}
    ]
  },
  "entitlement": {
    "provider": "Public",
    "use_context": "ai_analysis",
    "allowed": false,
    "policy_version": "alphaos-data-use-v1"
  }
}
```

The actual implementation must reject a nonempty candle array supplied by the
browser and rebuild the evidence envelope server-side from the authenticated
snapshot. `snapshot_id`, symbol, interval, session, timestamps, completeness, and
provider provenance must match the server record.

## Indicator rules

- Indicators are verified server-side derived values, never provider
  observations.
- Include the period, calculation inputs, snapshot ID, and a deterministic
  version/algorithm label.
- Do not present an EMA or other transform as a provider candle.
- If an indicator cannot be calculated from the available native bars, omit it
  or mark it unavailable; do not pad history.

## Assistant behavior

Gemini may describe only what the envelope contains. It must state when the
snapshot is stale, incomplete, has a partial last bar, or is missing expected
bars. It must not claim to have viewed a rendered chart beyond the supplied
evidence. It must not merge a quote into the last candle or treat an overnight
observation as a completed regular-session candle.

## Authorization and audit

- Check `ai_evidence_allowed(provider)` before sending or retaining evidence.
- Never send credentials, account identifiers, or raw provider payloads.
- Keep the existing bounded evidence budget (8.5 seconds) for the dashboard's
  evidence path until a replacement is separately validated.
- Log a safe snapshot ID, symbol, interval, policy version, and outcome; never log
  candle arrays or secrets.

## Future implementation acceptance tests

- Browser-supplied candle arrays are rejected or ignored.
- The server rebuilds evidence from the exact snapshot ID shown to the user.
- A stale/incomplete/partial snapshot produces explicit caveats.
- Public data is denied for AI analysis under the current policy.
- A licensed provider with documented AI authorization can use the same contract
  without changing the chart or assistant payload shape.
- Provider replacement changes provenance fields only, not the candle schema.
