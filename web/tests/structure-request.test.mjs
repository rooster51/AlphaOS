import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import {
  MAX_COMPARE_STRUCTURES,
  MAX_LEGS,
  buildStructureRequest,
  parseCompareRequest,
  parseStructureRequest,
  structureLabel,
} from "../src/lib/structure-contract.ts";

const fixture = JSON.parse(readFileSync(new URL("./fixtures/structure-parity.json", import.meta.url), "utf8"));

function form(overrides = {}) {
  return {
    symbol: "QQQ",
    expiration: "2030-01-02",
    asOf: "2030-01-02",
    spot: "500",
    side: "debit",
    packagePrice: "1.20",
    fees: "0",
    legs: [
      { type: "Call", action: "Buy", strike: "500", quantity: "1" },
      { type: "Call", action: "Sell", strike: "505", quantity: "1" },
    ],
    ...overrides,
  };
}

test("debit form maps to the backend's signed package cashflow and signed quantities", () => {
  const result = buildStructureRequest(form());
  assert.equal(result.ok, true);
  assert.deepEqual(result.value, {
    symbol: "QQQ",
    expiration: "2030-01-02",
    as_of: "2030-01-02",
    spot: 500,
    credit: -1.2,
    fees: 0,
    legs: [
      { type: "Call", strike: 500, qty: 1 },
      { type: "Call", strike: 505, qty: -1 },
    ],
  });
  // The generated fixture is real backend output for this exact request.
  assert.deepEqual(result.value, fixture.request);
});

test("credit form maps to a positive package cashflow, and fees default to zero", () => {
  const result = buildStructureRequest(form({ side: "credit", packagePrice: "0.95", fees: "" }));
  assert.equal(result.ok, true);
  assert.equal(result.value.credit, 0.95);
  assert.equal(result.value.fees, 0);
  assert.deepEqual(result.value.legs.map((leg) => leg.qty), [1, -1]);
});

test("side and action selectors are the only sign source", () => {
  const credit = buildStructureRequest(form({ side: "credit", legs: [
    { type: "Put", action: "Sell", strike: "495", quantity: "2" },
    { type: "Put", action: "Buy", strike: "490", quantity: "2" },
  ] }));
  assert.equal(credit.ok, true);
  assert.deepEqual(credit.value.legs, [
    { type: "Put", strike: 495, qty: -2 },
    { type: "Put", strike: 490, qty: 2 },
  ]);
  assert.equal(credit.value.credit, 1.2);
});

test("invalid form input is reported without producing a partial request", () => {
  const cases = [
    [{ symbol: "DIA" }, /SPY or QQQ/],
    [{ expiration: "Friday" }, /Expiration must be a valid/],
    [{ asOf: "" }, /Research date must be a valid/],
    [{ expiration: "2030-01-01", asOf: "2030-01-02" }, /must not precede/],
    [{ spot: "0" }, /Spot must be a positive/],
    [{ spot: "abc" }, /Spot must be a positive/],
    [{ packagePrice: "0" }, /positive number/],
    [{ fees: "-1" }, /Fees must be a nonnegative/],
    [{ legs: [] }, /between 1 and/],
    [{ legs: Array.from({ length: MAX_LEGS + 1 }, () => ({ type: "Call", action: "Buy", strike: "500", quantity: "1" })) }, /between 1 and/],
    [{ legs: [{ type: "Straddle", action: "Buy", strike: "500", quantity: "1" }] }, /type must be Call or Put/],
    [{ legs: [{ type: "Call", action: "Buy", strike: "0", quantity: "1" }] }, /strike must be a positive/],
    [{ legs: [{ type: "Call", action: "Hold", strike: "500", quantity: "1" }] }, /action must be Buy or Sell/],
    [{ legs: [{ type: "Call", action: "Buy", strike: "500", quantity: "0" }] }, /quantity must be a whole/],
    [{ legs: [{ type: "Call", action: "Buy", strike: "500", quantity: "1.5" }] }, /quantity must be a whole/],
    [{ legs: [{ type: "Call", action: "Buy", strike: "500", quantity: "101" }] }, /quantity must be a whole/],
  ];
  for (const [overrides, message] of cases) {
    const result = buildStructureRequest(form(overrides));
    assert.equal(result.ok, false, JSON.stringify(overrides));
    assert.ok(result.errors.some((error) => message.test(error)), JSON.stringify(result.errors));
  }
});

test("the wire contract accepts only the documented structure body", () => {
  assert.deepEqual(parseStructureRequest(fixture.request), fixture.request);
  assert.equal(parseStructureRequest({ ...fixture.request, symbol: "qqq" }).symbol, "QQQ");
  for (const invalid of [
    { ...fixture.request, extra: 1 },
    { ...fixture.request, symbol: "SPX" },
    { ...fixture.request, spot: 0 },
    { ...fixture.request, spot: "500" },
    { ...fixture.request, credit: Number.NaN },
    { ...fixture.request, credit: Number.POSITIVE_INFINITY },
    { ...fixture.request, as_of: "2030-01-03" },
    { ...fixture.request, expiration: "2030-02-30" },
    { ...fixture.request, fees: -1 },
    { ...fixture.request, legs: [] },
    { ...fixture.request, legs: [{ type: "Call", strike: 500, qty: 0 }] },
    { ...fixture.request, legs: [{ type: "Call", strike: 500, qty: 1.5 }] },
    { ...fixture.request, legs: [{ type: "Call", strike: 500, qty: 101 }] },
    { ...fixture.request, legs: [{ type: "Call", strike: 500, qty: true }] },
    { ...fixture.request, legs: [{ type: "call", strike: 500, qty: 1 }] },
    { ...fixture.request, legs: [{ type: "Call", strike: 500, qty: 1, delta: 0.5 }] },
    { ...fixture.request, legs: Array.from({ length: MAX_LEGS + 1 }, () => ({ type: "Call", strike: 500, qty: 1 })) },
  ]) {
    assert.equal(parseStructureRequest(invalid), null, JSON.stringify(invalid));
  }
});

test("comparison bodies keep the supplied order and reject out-of-contract shapes", () => {
  const first = fixture.request;
  const second = { ...first, credit: -2.2, fees: 1.3, legs: first.legs.slice(0, 1) };
  const parsed = parseCompareRequest({ structures: [first, second], thesis: "debit versus long" });
  assert.deepEqual(parsed, { structures: [first, second], thesis: "debit versus long" });
  assert.deepEqual(parseCompareRequest({ structures: [first] }), { structures: [first] });
  assert.deepEqual(parseCompareRequest({ structures: [first], thesis: "  " }), { structures: [first] });

  for (const invalid of [
    {},
    { structures: [] },
    { structures: Array.from({ length: MAX_COMPARE_STRUCTURES + 1 }, () => first) },
    { structures: [first], extra: true },
    { structures: [first], thesis: "x".repeat(1001) },
    { structures: [first], thesis: 42 },
    { structures: [{ ...first, legs: [] }] },
  ]) {
    assert.equal(parseCompareRequest(invalid), null, JSON.stringify(invalid).slice(0, 120));
  }
});

/** Mirrors the twelve explicit geometries in Codex's monthly/LEAPS capability matrix. */
const GEOMETRIES = [
  { label: "long call", side: "debit", price: 2, legs: [["Call", "Buy", 100, 1]] },
  { label: "long put", side: "debit", price: 2, legs: [["Put", "Buy", 100, 1]] },
  { label: "call debit spread", side: "debit", price: 2, legs: [["Call", "Buy", 100, 1], ["Call", "Sell", 105, 1]] },
  { label: "put debit spread", side: "debit", price: 2, legs: [["Put", "Buy", 100, 1], ["Put", "Sell", 95, 1]] },
  { label: "put credit spread", side: "credit", price: 2, legs: [["Put", "Buy", 95, 1], ["Put", "Sell", 100, 1]] },
  { label: "call credit spread", side: "credit", price: 2, legs: [["Call", "Sell", 100, 1], ["Call", "Buy", 105, 1]] },
  { label: "call butterfly", side: "debit", price: 2, legs: [["Call", "Buy", 95, 1], ["Call", "Sell", 100, 2], ["Call", "Buy", 105, 1]] },
  { label: "put butterfly", side: "debit", price: 2, legs: [["Put", "Buy", 95, 1], ["Put", "Sell", 100, 2], ["Put", "Buy", 105, 1]] },
  { label: "bullish broken-wing butterfly", side: "credit", price: 1, legs: [["Put", "Buy", 90, 1], ["Put", "Sell", 100, 2], ["Put", "Buy", 105, 1]] },
  { label: "bearish broken-wing butterfly", side: "credit", price: 1, legs: [["Call", "Buy", 95, 1], ["Call", "Sell", 100, 2], ["Call", "Buy", 110, 1]] },
  { label: "iron condor", side: "credit", price: 2, legs: [["Put", "Buy", 90, 1], ["Put", "Sell", 95, 1], ["Call", "Sell", 105, 1], ["Call", "Buy", 115, 1]] },
  { label: "symmetric credit iron butterfly", side: "credit", price: 2, legs: [["Put", "Buy", 95, 1], ["Put", "Sell", 100, 1], ["Call", "Sell", 100, 1], ["Call", "Buy", 105, 1]] },
];

test("all twelve backend-supported geometries are expressible through the form", () => {
  assert.equal(GEOMETRIES.length, 12);
  for (const item of GEOMETRIES) {
    const result = buildStructureRequest(form({
      symbol: "SPY",
      expiration: "2030-01-18",
      asOf: "2030-01-02",
      spot: "100",
      side: item.side,
      packagePrice: String(item.price),
      fees: "0",
      legs: item.legs.map(([type, action, strike, quantity]) => ({
        type, action, strike: String(strike), quantity: String(quantity),
      })),
    }));
    assert.equal(result.ok, true, item.label);
    assert.deepEqual(
      result.value.legs,
      item.legs.map(([type, action, strike, quantity]) => ({
        type, strike, qty: action === "Buy" ? quantity : -quantity,
      })),
      item.label,
    );
    assert.equal(result.value.credit, item.side === "credit" ? item.price : -item.price, item.label);
  }
});

test("unimplemented geometries still reach the backend instead of being guessed client-side", () => {
  const unsupported = [
    { label: "straddle", credit: -4, legs: [{ type: "Call", strike: 100, qty: 1 }, { type: "Put", strike: 100, qty: 1 }] },
    { label: "strangle", credit: -4, legs: [{ type: "Call", strike: 105, qty: 1 }, { type: "Put", strike: 95, qty: 1 }] },
    { label: "naked short call", credit: 2, legs: [{ type: "Call", strike: 100, qty: -1 }] },
    { label: "naked short put", credit: 2, legs: [{ type: "Put", strike: 100, qty: -1 }] },
  ];
  for (const item of unsupported) {
    const parsed = parseStructureRequest({ ...fixture.request, credit: item.credit, legs: item.legs });
    assert.notEqual(parsed, null, item.label);
    assert.deepEqual(parsed.legs, item.legs, item.label);
  }
});

test("scenario labels stay descriptive and deterministic", () => {
  assert.equal(
    structureLabel(fixture.request),
    "QQQ 2030-01-02 · Call 500 Buy 1 · Call 505 Sell 1 · debit 1.2",
  );
});
