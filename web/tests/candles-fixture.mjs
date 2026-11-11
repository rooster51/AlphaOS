/** Test-only synthetic candle snapshots. Never live market observations. */
export function candleSnapshot(overrides = {}) {
  const candles = overrides.candles ?? [
    { time: "2026-11-10T14:30:00Z", open: 600.0, high: 601.0, low: 599.5, close: 600.5, volume: 12_500 },
    { time: "2026-11-10T14:31:00Z", open: 600.5, high: 601.2, low: 600.1, close: 600.9, volume: 9_800 },
  ];
  return {
    schema_version: "alphaos-candles-v1",
    symbol: "SPY",
    interval: "1m",
    provider: "Public",
    session: "regular",
    retrieved_at: "2026-11-10T14:33:00Z",
    latest_candle_at: candles.at(-1)?.time ?? "2026-11-10T14:33:00Z",
    snapshot_id: "a".repeat(64),
    expected_bars: 390,
    received_bars: candles.length,
    returned_bars: candles.length,
    completeness: "complete",
    last_bar_status: "complete",
    freshness: "fresh",
    warnings: [],
    candles,
    provider_capabilities: {
      provider: "Public",
      symbols: ["SPY", "QQQ"],
      intervals: ["1m", "5m", "15m"],
      sessions: ["regular"],
      latest_quotes: true,
      native_candles: true,
      provider_native_intervals: true,
      expected_bar_metadata: true,
      entitlement: {
        provider: "Public",
        public_display: true,
        authorization_reference: "synthetic-test-only",
      },
    },
    entitlement: {
      provider: "Public",
      use_context: "public_display",
      allowed: true,
      code: "allowed",
      reason: "Synthetic display authorization fixture.",
      basis: "Test only; never a provider authorization.",
      policy_version: "alphaos-data-use-v1",
      authorization_required: true,
      authorization_reference_present: true,
    },
    ...overrides,
  };
}
