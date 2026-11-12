import { test } from "node:test";
import assert from "node:assert/strict";
import { auditEntry } from "../src/lib/pivex/entry-audit.ts";

const spec = {
  tickSize: 1,
  tickValue: 1,
  quoteToAccount: 1,
  spreadTicks: 1,
  slippageTicks: 0.5,
  commissionPerLot: 0,
  fixedFees: 0.25,
};
const setup = {
  status: "CONFIRMED",
  direction: "long",
  entryReference: 100,
  stop: 75,
  target: 150,
  confirmationTime: "2025-01-02T13:00:00Z",
  reason: "fixture",
};
const bar = (open) => ({ open, openTime: setup.confirmationTime });
const audit = (overrides, open, quantity = 1) =>
  auditEntry({ ...setup, ...overrides }, bar(open), spec, quantity, 25, 10000);

test("audit counts overlapping net RR and dollar risk with deterministic primary priority", () => {
  const r = audit({}, 100);
  assert.deepEqual(r.rejectionReasons, [
    "Insufficient net reward/risk",
    "Planned risk above $25",
  ]);
  assert.equal(r.primaryRejectionReason, "Insufficient net reward/risk");
  assert.equal(r.confirmationPrice, 100);
  assert.equal(r.grossRewardRisk, 2);
  assert.equal(r.netRewardRisk, 48.25 / 26.75);
  assert.equal(r.plannedRisk, 26.75);
  assert.deepEqual(r.costs, {
    spread: 1,
    slippage: 0.5,
    fees: 0.25,
    total: 1.75,
    basis: "modeled entry costs",
  });
  assert.equal(r.feasibleQuantity, null);
});

test("audit diagnoses both geometry sides and nonfinite or missing opens", () => {
  assert.deepEqual(audit({}, 75).rejectionReasons, ["Invalid stop geometry"]);
  assert.deepEqual(audit({}, 150).rejectionReasons, [
    "Invalid target geometry",
    "Planned risk above $25",
  ]);
  assert.deepEqual(
    audit({ direction: "short", stop: 99, target: 101 }, 100).rejectionReasons,
    ["Invalid stop geometry", "Invalid target geometry"],
  );
  assert.deepEqual(audit({}, Infinity).rejectionReasons, [
    "Invalid or nonfinite economics",
  ]);
  const missing = auditEntry(setup, null, spec, 1, 25, 10000);
  assert.deepEqual(missing.rejectionReasons, [
    "Missing contiguous next candle",
  ]);
  assert.equal(missing.nextOpen, null);
  assert.equal(missing.netRewardRisk, null);
});

test("hypothetical size range reflects minimum fixed-fee economics and maximum risk", () => {
  const r = audit({ target: 158 }, 100);
  assert.deepEqual(r.rejectionReasons, ["Planned risk above $25"]);
  assert.deepEqual(r.feasibleQuantity, {
    minimum: 0.75 / 3.5,
    maximum: 24.75 / 26.5,
  });
  assert.deepEqual(audit({ target: 158 }, 100, 0.5).rejectionReasons, []);
  assert.deepEqual(audit({ target: 158 }, 100, 0.1).rejectionReasons, [
    "Insufficient net reward/risk",
  ]);
});

test("experimental target uses the next open and the nearest executable tick meeting net 2R", () => {
  const attempt = (
    direction,
    open,
    stop,
    price,
    observedAt = "2025-01-02T12:55:00Z",
  ) =>
    auditEntry(
      {
        ...setup,
        direction,
        stop,
        evidence: { target: { price, observedAt } },
      },
      bar(open),
      spec,
      1,
      25,
      10000,
      undefined,
      "net_2r_structure",
    );

  for (const [direction, open, stop, boundary] of [
    ["long", 101, 95, 119],
    ["short", 99, 105, 81],
  ]) {
    const accepted = attempt(direction, open, stop, boundary);
    assert.equal(accepted.target, boundary);
    assert.equal(accepted.plannedRisk, 7.75);
    assert(accepted.netRewardRisk >= 2);
    assert.deepEqual(accepted.rejectionReasons, []);
    const tighter = boundary + (direction === "long" ? -1 : 1);
    assert.deepEqual(attempt(direction, open, stop, tighter).rejectionReasons, [
      "Net 2R target exceeds available structure",
    ]);
    assert.deepEqual(
      attempt(direction, open, stop, boundary, "2025-01-02T12:56:00Z")
        .rejectionReasons,
      ["Net 2R target exceeds available structure"],
    );
  }
  assert.deepEqual(attempt("long", 100, 75, 200).rejectionReasons, [
    "Planned risk above $25",
  ]);
});
