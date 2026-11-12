import assert from "node:assert/strict";
import { test } from "node:test";
import {
  fetchCandles,
  formatAge,
  parseCandleSnapshot,
  warningLabel,
} from "../src/lib/candles.ts";
import { emaValues, toChartSeries } from "../src/lib/candle-chart.ts";
import { candleSnapshot } from "./candles-fixture.mjs";

test("validates SPY and QQQ snapshots for all native intervals without resampling", () => {
  for (const symbol of ["SPY", "QQQ"]) {
    for (const interval of ["1m", "5m", "15m"]) {
      const value = candleSnapshot({ symbol, interval });
      const parsed = parseCandleSnapshot(value, { symbol, interval });
      assert.ok(parsed, `${symbol} ${interval}`);
      assert.equal(parsed.symbol, symbol);
      assert.equal(parsed.interval, interval);
      assert.equal(parsed.snapshot_id, "a".repeat(64));
    }
  }
});

test("rejects mismatched symbols/intervals, incomplete counts, denied entitlement and unsorted bars", () => {
  const base = candleSnapshot();
  const cases = [
    candleSnapshot({ symbol: "QQQ" }),
    candleSnapshot({ interval: "5m" }),
    candleSnapshot({ returned_bars: 1 }),
    candleSnapshot({ entitlement: { ...base.entitlement, allowed: false } }),
    candleSnapshot({ provider: "Other" }),
    candleSnapshot({ candles: [
      base.candles[1],
      base.candles[0],
    ] }),
    candleSnapshot({ candles: [{ ...base.candles[0], high: 599 }] }),
    candleSnapshot({ schema_version: "alphaos-candles-v0" }),
  ];
  for (const [index, value] of cases.entries()) {
    assert.equal(
      parseCandleSnapshot(value, { symbol: "SPY", interval: "1m" }),
      null,
      `case ${index}`,
    );
  }
});

test("a missing native bar stays a timestamp gap; the adapter inserts nothing", () => {
  const snapshot = candleSnapshot({
    candles: [
      { time: "2026-11-10T14:30:00Z", open: 600, high: 601, low: 599, close: 600.5, volume: 100 },
      { time: "2026-11-10T14:32:00Z", open: 600.5, high: 602, low: 600, close: 601.5, volume: 200 },
    ],
    warnings: ["missing_bars", "incomplete_session"],
  });
  const parsed = parseCandleSnapshot(snapshot, { symbol: "SPY", interval: "1m" });
  assert.ok(parsed);
  const series = toChartSeries(parsed);
  assert.equal(series.candles.length, 2);
  assert.equal(series.volume.length, 2);
  assert.equal(series.candles[1].time - series.candles[0].time, 120);
  assert.equal(series.candles.some((bar) => bar.time === Date.parse("2026-11-10T14:31:00Z") / 1000), false);
  assert.equal(series.snapshotId, snapshot.snapshot_id);
});

test("EMA is derived only after a complete period and never backfilled", () => {
  assert.deepEqual(emaValues([1, 2], 3), []);
  assert.deepEqual(emaValues([1, 2, 3, 4, 5], 3), [
    { timeIndex: 2, value: 2 },
    { timeIndex: 3, value: 3 },
    { timeIndex: 4, value: 4 },
  ]);
  assert.deepEqual(emaValues([1, Number.NaN, 3], 2), []);
  assert.equal(emaValues([1, 2, 3], 0).length, 0);
});

test("warning labels are explicit and unknown server warnings remain visible", () => {
  assert.equal(warningLabel("last_bar_window_open"), "Last-bar window open");
  assert.equal(warningLabel("provider_incomplete_bars_skipped"), "Provider skipped incomplete bars");
  assert.equal(warningLabel("new_server_warning"), "New server warning");
  assert.equal(formatAge(0), "0s old");
  assert.equal(formatAge(61), "1m 1s old");
});

function okResponse(snapshot) {
  return Response.json({ status: "ok", snapshot });
}

test("client calls only the same-origin bridge and never carries a backend token", async () => {
  let captured;
  const result = await fetchCandles("SPY", "5m", {
    request: async (url, options) => {
      captured = { url, options };
      return okResponse(candleSnapshot({ interval: "5m" }));
    },
  });
  assert.equal(result.ok, true);
  assert.equal(captured.url, "/api/candles/SPY?interval=5m&session=regular&limit=390");
  assert.equal(captured.options.method, "GET");
  assert.equal(captured.options.credentials, "same-origin");
  assert.equal(captured.options.cache, "no-store");
  assert.equal(captured.options.headers.Authorization, undefined);
  assert.equal(JSON.stringify(captured).includes("test-token"), false);
});

test("client maps auth, policy, throttling, provider and timeout states distinctly", async () => {
  const cases = [
    [401, { status: "unavailable", code: "authentication_required" }, "authentication_required"],
    [403, { status: "unavailable", code: "owner_only" }, "owner_only"],
    [403, { status: "unavailable", code: "data_use_denied" }, "data_use_denied"],
    [429, { status: "unavailable", code: "provider_rate_limited" }, "provider_rate_limited"],
    [503, { status: "unavailable", code: "public_not_configured" }, "provider_unavailable"],
    [503, { status: "unavailable", code: "no_candles" }, "provider_unavailable"],
    [504, { status: "unavailable", code: "provider_timeout" }, "provider_timeout"],
    [502, { status: "unavailable", code: "provider_schema_error" }, "provider_unavailable"],
    [400, { status: "unavailable", code: "invalid_request" }, "invalid_request"],
  ];
  for (const [status, body, code] of cases) {
    const result = await fetchCandles("SPY", "1m", {
      request: async () => Response.json(body, { status }),
    });
    assert.equal(result.ok, false);
    assert.equal(result.error.code, code, `${status} ${body.code}`);
    assert.equal(JSON.stringify(result).includes("provider-token"), false);
  }
});

test("429 exposes a bounded Retry-After and does not retry internally", async () => {
  let calls = 0;
  const result = await fetchCandles("SPY", "1m", {
    request: async () => {
      calls += 1;
      return Response.json(
        { status: "unavailable", code: "provider_rate_limited" },
        { status: 429, headers: { "Retry-After": "30" } },
      );
    },
  });
  assert.equal(result.ok, false);
  assert.equal(result.error.code, "provider_rate_limited");
  assert.equal(result.error.retryAfterSeconds, 30);
  assert.equal(calls, 1);
});

test("client rejects a valid HTTP response whose snapshot violates the contract", async () => {
  const result = await fetchCandles("SPY", "1m", {
    request: async () => okResponse(candleSnapshot({ returned_bars: 1 })),
  });
  assert.equal(result.ok, false);
  assert.equal(result.error.code, "response_schema_mismatch");
});

test("client distinguishes timeout, caller cancellation and transport failure", async () => {
  const timeout = await fetchCandles("SPY", "1m", {
    request: async () => { throw new DOMException("deadline", "TimeoutError"); },
  });
  assert.equal(timeout.ok, false);
  assert.equal(timeout.error.code, "request_timeout");

  const controller = new AbortController();
  controller.abort();
  const cancelled = await fetchCandles("SPY", "1m", {
    signal: controller.signal,
    request: async () => { throw new DOMException("cancelled", "AbortError"); },
  });
  assert.equal(cancelled.ok, false);
  assert.equal(cancelled.error.code, "cancelled");

  const unreachable = await fetchCandles("SPY", "1m", {
    request: async () => { throw new TypeError("network"); },
  });
  assert.equal(unreachable.ok, false);
  assert.equal(unreachable.error.code, "backend_unreachable");
});
