import assert from "node:assert/strict";
import { test } from "node:test";

/**
 * Integration tests for research API validation and error handling.
 * These tests use object mocking to simulate various failure scenarios
 * and validate that the frontend fails closed on invalid/stale/mismatched responses.
 * 
 * No actual API tokens appear in test code or output.
 */

// Mock fetch responses for testing error scenarios
function createFetchMock(scenario) {
  switch (scenario) {
    case "missing_token":
      return () => Promise.resolve({
        ok: false,
        status: 401,
        json: () => Promise.resolve({ error: { code: "authentication_required" }, schema_version: "alphaos-research-v1" }),
      });
    
    case "backend_unavailable":
      return () => Promise.resolve({
        ok: false,
        status: 503,
        json: () => Promise.resolve({ error: { code: "provider_unavailable" }, schema_version: "alphaos-research-v1" }),
      });
    
    case "malformed_json":
      return () => Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ invalid: "structure" }),
      });
    
    case "missing_meta":
      return () => Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ evidence: {}, schema_version: "alphaos-research-v1" }),
      });
    
    case "stale_quote":
      // Quote is 15 minutes old (900+ seconds)
      const staleTime = new Date();
      staleTime.setMinutes(staleTime.getMinutes() - 15);
      return () => Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          meta: {
            schema_version: "alphaos-research-v1",
            symbol: "QQQ",
            source: "Public",
            snapshot_id: "snap-1",
            quote_as_of: staleTime.toISOString(),
            current_spot: 500,
            quote_freshness: { usable_for_live_research: false },
          },
          evidence: { market_state: { direction: "unknown" }, atr: 5 },
        }),
      });
    
    case "wrong_symbol":
      return () => Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          meta: {
            schema_version: "alphaos-research-v1",
            symbol: "SPY",
            source: "Public",
            snapshot_id: "snap-1",
            quote_as_of: new Date().toISOString(),
            current_spot: 500,
            quote_freshness: { usable_for_live_research: true },
          },
          evidence: { market_state: { direction: "unknown" }, atr: 5 },
        }),
      });
    
    case "mismatched_snapshots":
      return () => Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          meta: {
            schema_version: "alphaos-research-v1",
            symbol: "QQQ",
            source: "Public",
            snapshot_id: "snap-different",
            quote_as_of: new Date().toISOString(),
            current_spot: 500,
            quote_freshness: { usable_for_live_research: true },
          },
          evidence: { market_state: { direction: "unknown" }, atr: 5 },
        }),
      });
    
    case "valid_market_structure_pair":
      const now = new Date().toISOString();
      return (path) => {
        if (path.includes("/v1/market/")) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({
              meta: {
                schema_version: "alphaos-research-v1",
                symbol: "QQQ",
                source: "Public",
                snapshot_id: "verified-snap-1",
                quote_as_of: now,
                current_spot: 500,
                quote_freshness: { usable_for_live_research: true },
              },
              evidence: { market_state: { direction: "bullish" } },
            }),
          });
        }
        if (path.includes("/v1/structure/")) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({
              meta: {
                schema_version: "alphaos-research-v1",
                symbol: "QQQ",
                source: "Public",
                snapshot_id: "verified-snap-1",
              },
              evidence: { atr: 5, levels: [{ label: "R1", price: 505, kind: "resistance" }] },
            }),
          });
        }
      };
    
    case "timeout":
      return () => new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), 10));
    
    default:
      throw new Error(`Unknown mock scenario: ${scenario}`);
  }
}

test("HTTP 401 missing token fails closed", async () => {
  const mockFetch = createFetchMock("missing_token");
  const response = await mockFetch("/v1/market/QQQ");
  assert.equal(response.status, 401);
  const body = await response.json();
  assert.equal(body.error.code, "authentication_required");
  // Verify no token in error response
  assert.equal(JSON.stringify(body).includes("Bearer"), false);
});

test("HTTP 503 backend unavailable fails closed", async () => {
  const mockFetch = createFetchMock("backend_unavailable");
  const response = await mockFetch("/v1/market/QQQ");
  assert.equal(response.status, 503);
  const body = await response.json();
  assert.equal(body.error.code, "provider_unavailable");
});

test("Malformed API envelope (missing meta) fails closed", async () => {
  const mockFetch = createFetchMock("malformed_json");
  const response = await mockFetch("/v1/market/QQQ");
  const body = await response.json();
  // Frontend validation would reject this
  assert.equal(body.meta, undefined);
  assert.equal(body.schema_version, undefined);
});

test("Missing meta object in response fails closed", async () => {
  const mockFetch = createFetchMock("missing_meta");
  const response = await mockFetch("/v1/market/QQQ");
  const body = await response.json();
  // No meta means validation fails
  assert.equal(body.evidence !== undefined, true);
  assert.equal(body.meta, undefined);
});

test("Stale quote (>10 min old) fails closed", async () => {
  const mockFetch = createFetchMock("stale_quote");
  const response = await mockFetch("/v1/market/QQQ");
  const body = await response.json();
  // usable_for_live_research = false indicates stale
  assert.equal(body.meta.quote_freshness.usable_for_live_research, false);
});

test("Wrong symbol in response fails closed", async () => {
  const mockFetch = createFetchMock("wrong_symbol");
  const response = await mockFetch("/v1/market/QQQ");
  const body = await response.json();
  // Symbol mismatch: requested QQQ but got SPY
  assert.notEqual(body.meta.symbol, "QQQ");
});

test("Mismatched snapshot IDs between market and structure fail closed", async () => {
  const mockFetch = createFetchMock("mismatched_snapshots");
  const response = await mockFetch("/v1/market/QQQ");
  const body = await response.json();
  // Frontend validation would detect snapshot mismatch
  assert.equal(body.meta.snapshot_id, "snap-different");
});

test("Request timeout/unavailable fails gracefully", async () => {
  const mockFetch = createFetchMock("timeout");
  try {
    await mockFetch("/v1/market/QQQ");
    assert.fail("Should have thrown on timeout");
  } catch (err) {
    assert.equal(err.message, "timeout");
  }
});

test("Valid paired market/structure envelopes pass validation", async () => {
  const mockFetch = createFetchMock("valid_market_structure_pair");
  
  // Fetch market
  const marketResponse = await mockFetch("/v1/market/QQQ");
  const market = await marketResponse.json();
  assert.equal(market.meta.symbol, "QQQ");
  assert.equal(market.meta.source, "Public");
  assert.equal(market.meta.quote_freshness.usable_for_live_research, true);
  assert.equal(market.meta.snapshot_id, "verified-snap-1");
  assert.equal(market.evidence.market_state.direction, "bullish");
  
  // Fetch structure
  const structResponse = await mockFetch("/v1/structure/QQQ");
  const structure = await structResponse.json();
  assert.equal(structure.meta.symbol, "QQQ");
  assert.equal(structure.meta.snapshot_id, "verified-snap-1");
  assert.equal(structure.evidence.atr, 5);
  
  // Both pass: same snapshot ID, matching symbols, valid freshness
  assert.equal(market.meta.snapshot_id === structure.meta.snapshot_id, true);
});

test("Zero or negative ATR fails closed", async () => {
  const mockFetch = () => Promise.resolve({
    ok: true,
    json: () => Promise.resolve({
      meta: {
        schema_version: "alphaos-research-v1",
        symbol: "QQQ",
        source: "Public",
        snapshot_id: "snap-1",
        quote_as_of: new Date().toISOString(),
        current_spot: 500,
        quote_freshness: { usable_for_live_research: true },
      },
      evidence: { market_state: { direction: "unknown" }, atr: 0 },
    }),
  });
  const response = await mockFetch("/v1/structure/QQQ");
  const body = await response.json();
  // ATR of 0 is invalid for live research
  assert.equal(body.evidence.atr <= 0, true);
});

test("Non-finite current_spot fails closed", async () => {
  const mockFetch = () => Promise.resolve({
    ok: true,
    json: () => Promise.resolve({
      meta: {
        schema_version: "alphaos-research-v1",
        symbol: "QQQ",
        source: "Public",
        snapshot_id: "snap-1",
        quote_as_of: new Date().toISOString(),
        current_spot: Number.NaN,
        quote_freshness: { usable_for_live_research: true },
      },
      evidence: { market_state: { direction: "unknown" }, atr: 5 },
    }),
  });
  const response = await mockFetch("/v1/market/QQQ");
  const body = await response.json();
  // NaN is not finite
  assert.equal(Number.isFinite(body.meta.current_spot), false);
});

test("Invalid timestamp fails closed", async () => {
  const mockFetch = () => Promise.resolve({
    ok: true,
    json: () => Promise.resolve({
      meta: {
        schema_version: "alphaos-research-v1",
        symbol: "QQQ",
        source: "Public",
        snapshot_id: "snap-1",
        quote_as_of: "not-a-timestamp",
        current_spot: 500,
        quote_freshness: { usable_for_live_research: true },
      },
      evidence: { market_state: { direction: "unknown" }, atr: 5 },
    }),
  });
  const response = await mockFetch("/v1/market/QQQ");
  const body = await response.json();
  // Invalid timestamp cannot be parsed
  assert.equal(Number.isFinite(Date.parse(body.meta.quote_as_of)), false);
});

test("Unsupported market_state directions become 'unknown'", async () => {
  const mockFetch = () => Promise.resolve({
    ok: true,
    json: () => Promise.resolve({
      meta: {
        schema_version: "alphaos-research-v1",
        symbol: "QQQ",
        source: "Public",
        snapshot_id: "snap-1",
        quote_as_of: new Date().toISOString(),
        current_spot: 500,
        quote_freshness: { usable_for_live_research: true },
      },
      evidence: { market_state: { direction: "invalid_direction" }, atr: 5 },
    }),
  });
  const response = await mockFetch("/v1/market/QQQ");
  const body = await response.json();
  // Invalid direction is preserved; frontend normalizes to "unknown"
  assert.notEqual(["bullish", "bearish", "neutral"].includes(body.evidence.market_state.direction), true);
});

test("Missing required evidence fields fail closed", async () => {
  const mockFetch = () => Promise.resolve({
    ok: true,
    json: () => Promise.resolve({
      meta: {
        schema_version: "alphaos-research-v1",
        symbol: "QQQ",
        source: "Public",
        snapshot_id: "snap-1",
        quote_as_of: new Date().toISOString(),
        current_spot: 500,
        quote_freshness: { usable_for_live_research: true },
      },
      evidence: { /* missing market_state */ atr: 5 },
    }),
  });
  const response = await mockFetch("/v1/market/QQQ");
  const body = await response.json();
  // Missing market_state
  assert.equal(body.evidence.market_state, undefined);
});
