import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import {
  compareView,
  compareViewFor,
  observationSeed,
  structureMessage,
  structureView,
  structureViewFor,
} from "../src/lib/structure-view.ts";

const single = JSON.parse(readFileSync(new URL("./fixtures/structure-parity.json", import.meta.url), "utf8"));
const compared = JSON.parse(readFileSync(new URL("./fixtures/structure-compare-parity.json", import.meta.url), "utf8"));
const spyPutCredit = JSON.parse(readFileSync(new URL("./fixtures/structure-spy-put-credit-parity.json", import.meta.url), "utf8"));
const ironButterfly = JSON.parse(readFileSync(new URL("./fixtures/structure-iron-butterfly-parity.json", import.meta.url), "utf8"));
const zeroCost = JSON.parse(readFileSync(new URL("./fixtures/structure-zero-cost-bwb-parity.json", import.meta.url), "utf8"));

function clone(value) {
  return structuredClone(value);
}

test("a real backend envelope renders only the values it actually returned", () => {
  const view = structureView(single);
  assert.ok(view);
  assert.equal(view.symbol, "QQQ");
  assert.equal(view.family, "call_debit_spread");
  assert.equal(view.direction, "bullish");
  assert.equal(view.expiration, "2030-01-02");
  assert.equal(view.asOf, "2030-01-02");
  assert.equal(view.spot, 500);
  assert.equal(view.dte, 0);
  assert.deepEqual(view.maxProfit, { kind: "value", value: 380 });
  assert.deepEqual(view.maxLoss, { kind: "value", value: 120 });
  assert.deepEqual(view.capitalRequired, { kind: "value", value: 120 });
  assert.deepEqual(view.breakevens, [501.2]);
  assert.equal(view.entryDebit, 1.2);
  assert.equal(view.entryCredit, 0);
  assert.equal(view.fees, 0);
  assert.equal(view.width, 5);
  assert.equal(view.creditWidth, null);
  assert.deepEqual(view.legs, [
    { type: "Call", strike: 500, qty: 1, action: "Buy", quantity: 1 },
    { type: "Call", strike: 505, qty: -1, action: "Sell", quantity: 1 },
  ]);
  assert.equal(view.extremes.length, single.research.payoff.extremes.length);
  assert.equal(view.pricingAssumption, "Supplied signed package cashflow; not a verified quote or fill");
  assert.deepEqual(view.integrity, []);
  assert.equal(view.historical.evidenceStatus, "unavailable");
  assert.deepEqual(view.historical.missing, ["unsupported_expiration_session_horizon"]);
  assert.equal(view.historical.provenance, "unavailable");
  assert.equal(view.historical.capitalStatus, "not_assessed");
  assert.equal(view.historical.sampleSize, 0);
  assert.ok(view.caveats.length >= 4);
});

test("an unlimited backend maximum is preserved and never converted into a number", () => {
  const longCall = {
    ...clone(single),
    request: clone(compared.request.structures[1]),
    research: clone(compared.research.candidates[1]),
  };
  const view = structureView(longCall);
  assert.ok(view);
  assert.equal(view.family, "long_call");
  assert.equal(view.expiration, "2030-01-02");
  assert.equal(view.entryDebit, 2.2);
  assert.equal(view.entryCredit, null);
  assert.deepEqual(view.maxProfit, { kind: "unlimited" });
  assert.deepEqual(view.maxLoss, { kind: "value", value: 221.30000000000004 });
  assert.deepEqual(view.breakevens, [502.213]);
  assert.deepEqual(view.integrity, []);
});

test("missing or unreadable metrics become unavailable", () => {
  const missing = clone(single);
  delete missing.research.max_profit;
  delete missing.research.breakevens;
  delete missing.research.breakeven;
  const view = structureView(missing);
  assert.ok(view);
  assert.equal(view.maxProfit.kind, "unavailable");
  assert.deepEqual(view.breakevens, []);
});

test("envelope tampering fails closed instead of rendering partial evidence", () => {
  const tampers = [
    (copy) => { copy.schema_version = "alphaos-interface-v1"; },
    (copy) => { copy.read_only = false; },
    (copy) => { copy.request.symbol = "SPY"; },
    (copy) => { copy.request.spot = 501; },
    (copy) => { copy.request.credit = 1.2; },
    (copy) => { copy.request.expiration = "2030-01-03"; },
    (copy) => { copy.research.expiration = "2030-01-03"; },
    (copy) => { copy.research.position.expiration = "2030-01-03"; },
    (copy) => { copy.request.legs[0].qty = -1; },
    (copy) => { copy.research.position.symbol = "SPY"; },
    (copy) => { copy.research.position.legs[0].strike = 501; },
    (copy) => { delete copy.research.position; },
    (copy) => { delete copy.research.trade; },
    (copy) => { delete copy.caveats; },
  ];
  for (const tamper of tampers) {
    const copy = clone(single);
    tamper(copy);
    assert.equal(structureView(copy), null, tamper.toString());
  }
  assert.equal(structureView(compared), null);
  assert.equal(structureView(null), null);
  assert.equal(structureView({}), null);
});

test("backend disagreements are surfaced as integrity warnings", () => {
  const copy = clone(single);
  copy.research.capital_at_risk = 121;
  copy.research.historical_economics.deterministic_expiration.max_loss = 119;
  const view = structureView(copy);
  assert.ok(view);
  assert.deepEqual(view.integrity, [
    "capital_at_risk_disagrees_with_max_loss",
    "historical_max_loss_disagrees_with_position_max_loss",
  ]);
});

test("descriptive historical evidence is labelled as verified rather than estimated", () => {
  const copy = clone(single);
  copy.research.historical_economics.historical_evidence_status = "descriptive_only";
  copy.research.historical_economics.missing_evidence = [];
  copy.research.historical_economics.sample_size = 42;
  copy.research.historical_economics.provenance.verification = "server_verified_archive_reader";
  const view = structureView(copy);
  assert.ok(view);
  assert.equal(view.historical.evidenceStatus, "descriptive_only");
  assert.equal(view.historical.sampleSize, 42);
  assert.equal(view.historical.provenance, "server_verified_archive_reader");
  assert.deepEqual(view.historical.missing, []);
});

test("comparison keeps input order, exclusions and comparability without a winner", () => {
  const view = compareView(compared);
  assert.ok(view);
  assert.equal(view.thesis, "Debit spread versus outright call");
  assert.equal(view.order, "supplied input order; not a ranking");
  assert.equal(view.noCandidate, false);
  assert.deepEqual(view.candidates.map((row) => row.index), [0, 1]);
  assert.deepEqual(view.candidates.map((row) => row.family), ["call_debit_spread", "long_call"]);
  assert.deepEqual(view.candidates[0].maxProfit, { kind: "value", value: 380 });
  assert.deepEqual(view.candidates[1].maxProfit, { kind: "unlimited" });
  assert.deepEqual(view.candidates[0].breakevens, [501.2]);
  assert.deepEqual(view.candidates[0].observedEvidence, []);
  assert.equal(view.candidates[0].historicalStatus, "unavailable");
  assert.deepEqual(view.excluded, []);
  assert.equal(view.groups.length, 1);
  assert.deepEqual(view.groups[0].indices, [0, 1]);
  assert.equal(view.groups[0].directlyComparable, false);
  assert.deepEqual(view.groups[0].missing, ["unsupported_expiration_session_horizon"]);
  assert.equal(view.pairs.length, 1);
  assert.deepEqual(view.pairs[0].indices, [0, 1]);
  assert.equal(view.pairs[0].comparable, false);
  assert.equal(view.pairs[0].reason, "validated_historical_evidence_unavailable");
  assert.ok(view.caveats.length >= 2);
});

test("comparison envelopes are rejected when they rank, recommend or mismatch", () => {
  const winner = clone(compared);
  winner.research.comparison.winner = 0;
  assert.equal(compareView(winner), null);

  const recommendation = clone(compared);
  recommendation.research.comparison.recommendation = "prefer #1";
  assert.equal(compareView(recommendation), null);

  const mismatched = clone(compared);
  mismatched.research.candidates.pop();
  assert.equal(compareView(mismatched), null);

  const excluded = clone(compared);
  excluded.research.comparison.excluded = [{ input_index: 1, reason: "invalid_or_insufficient_research" }];
  const view = compareView(excluded);
  assert.ok(view);
  assert.deepEqual(view.excluded, [{ index: 1, reason: "invalid_or_insufficient_research" }]);
});

test("archive observations prefill only from an explicit observation envelope", () => {
  const observation = {
    research: {
      schema_version: "alphaos-observation-v1",
      read_only: true,
      verified_for_trading: false,
      research_performed: false,
      evidence_scope: "archive_observation_only",
      symbol: "QQQ",
      research_mode: "current",
      as_of: "2026-10-26T14:30:00+00:00",
      requested_as_of: "2026-10-26T14:30:01+00:00",
      expiration: "2026-10-30",
      spot: 505.25,
      session: { open: "2026-10-26T13:30:00+00:00", close: "2026-10-26T20:00:00+00:00" },
      archive: {
        session_date: "2026-10-26",
        provider: "Public",
        freshness: { age_seconds: 120, max_age_seconds: 600 },
      },
      request: { symbol: "QQQ", research_mode: "current" },
      caveats: [],
    },
    verified_for_trading: false,
    source: "alphaos_research_api",
  };
  assert.deepEqual(observationSeed(observation, "QQQ"), {
    symbol: "QQQ",
    spot: 505.25,
    expiration: "2026-10-30",
    asOf: "2026-10-26",
    provider: "Public",
    observedAt: "2026-10-26T14:30:00+00:00",
    ageSeconds: 120,
  });

  const traded = clone(observation);
  traded.verified_for_trading = true;
  assert.equal(observationSeed(traded, "QQQ"), null);

  const researched = clone(observation);
  researched.research.research_performed = true;
  assert.equal(observationSeed(researched, "QQQ"), null);

  assert.equal(observationSeed(observation, "SPY"), null);
  assert.equal(observationSeed(single, "QQQ"), null);
});

test("a SPY put credit spread renders backend credit economics without local math", () => {
  const view = structureView(spyPutCredit);
  assert.ok(view);
  assert.equal(view.symbol, "SPY");
  assert.equal(view.family, "put_credit_spread");
  assert.equal(view.direction, "bullish");
  assert.deepEqual(view.maxProfit, { kind: "value", value: 109.35000000000001 });
  assert.deepEqual(view.maxLoss, { kind: "value", value: 390.65 });
  assert.deepEqual(view.capitalRequired, { kind: "value", value: 390.65 });
  assert.deepEqual(view.breakevens, [603.9065]);
  assert.equal(view.entryCredit, 1.1);
  assert.equal(view.entryDebit, 0);
  assert.equal(view.fees, 0.65);
  assert.deepEqual(view.legs.map((leg) => [leg.action, leg.type, leg.strike, leg.quantity]), [
    ["Sell", "Put", 605, 1],
    ["Buy", "Put", 600, 1],
  ]);
  assert.equal(view.pricingAssumption, "Supplied signed package cashflow; not a verified quote or fill");
});

test("a four-leg symmetric iron butterfly keeps the backend family, credit and roots", () => {
  const view = structureView(ironButterfly);
  assert.ok(view);
  assert.equal(view.family, "butterfly");
  assert.equal(view.direction, "neutral");
  assert.equal(view.expiration, "2030-01-18");
  assert.equal(view.dte, 16);
  assert.deepEqual(view.maxProfit, { kind: "value", value: 200 });
  assert.deepEqual(view.maxLoss, { kind: "value", value: 300 });
  assert.deepEqual(view.breakevens, [98, 102]);
  assert.equal(view.entryCredit, 2);
  assert.equal(view.entryDebit, 0);
  assert.deepEqual(view.legs.map((leg) => [leg.action, leg.type, leg.strike, leg.quantity]), [
    ["Buy", "Put", 95, 1],
    ["Sell", "Put", 100, 1],
    ["Sell", "Call", 100, 1],
    ["Buy", "Call", 105, 1],
  ]);
  assert.equal(view.historical.evidenceStatus, "unavailable");
  assert.deepEqual(view.historical.missing, ["unsupported_expiration_session_horizon"]);
});

test("no expected value, probability or eligibility claim is exposed for a supplied scenario", () => {
  for (const envelope of [ironButterfly, single, spyPutCredit]) {
    const view = structureView(envelope);
    assert.ok(view);
    const keys = Object.keys(view).join(" ");
    assert.equal(/expected.?value|probability|pop|eligible_for_consideration/i.test(keys), false, keys);
    const historicalKeys = Object.keys(view.historical).join(" ");
    assert.equal(/expected.?value|probability|pop|candidate/i.test(historicalKeys), false, historicalKeys);
    assert.equal(JSON.stringify(view).includes("expected_value_dollars"), false);
    assert.equal(JSON.stringify(view).includes("eligible_for_consideration"), false);
  }
});

test("missing archive evidence stays unavailable while supplied-cashflow economics remain labelled", () => {
  const copy = clone(spyPutCredit);
  copy.research.historical_economics.missing_evidence = ["verified_archive_unavailable"];
  copy.research.historical_economics.evidence = null;
  copy.research.historical_economics.sample_size = 0;
  const view = structureView(copy);
  assert.ok(view);
  assert.equal(view.historical.evidenceStatus, "unavailable");
  assert.deepEqual(view.historical.missing, ["verified_archive_unavailable"]);
  assert.equal(view.historical.sampleSize, 0);
  assert.deepEqual(view.maxLoss, { kind: "value", value: 390.65 });

  const missingInputs = clone(spyPutCredit);
  missingInputs.request.spot = 609;
  assert.equal(structureView(missingInputs), null);
});

test("risk metrics the backend omits are unavailable rather than inferred", () => {
  const copy = clone(spyPutCredit);
  delete copy.research.max_loss;
  delete copy.research.capital_at_risk;
  const view = structureView(copy);
  assert.ok(view);
  assert.deepEqual(view.maxLoss, { kind: "unavailable", reason: "not provided by the backend" });
  assert.deepEqual(view.capitalRequired, { kind: "unavailable", reason: "not provided by the backend" });
  assert.deepEqual(view.integrity, []);

  const noProfit = clone(spyPutCredit);
  delete noProfit.research.max_profit;
  const withoutProfit = structureView(noProfit);
  assert.equal(withoutProfit.maxProfit.kind, "unavailable");
});

test("a zero-cost broken-wing butterfly keeps its real zero cashflow", () => {
  const view = structureView(zeroCost);
  assert.ok(view);
  assert.equal(view.family, "bullish_bwb");
  assert.equal(view.direction, "bullish");
  assert.equal(view.packageCashflow, 0);
  assert.equal(view.entryDebit, 0);
  assert.equal(view.entryCredit, 0);
  assert.deepEqual(view.maxProfit, { kind: "value", value: 200 });
  assert.deepEqual(view.maxLoss, { kind: "value", value: 400 });
  assert.deepEqual(view.capitalRequired, { kind: "value", value: 400 });
  assert.deepEqual(view.breakevens, [98, 102]);
  assert.equal(view.historical.evidenceStatus, "unavailable");
  assert.deepEqual(view.historical.missing, ["as_of_session_not_complete"]);
});

test("a validated envelope must describe the exact submitted scenario", () => {
  assert.ok(structureViewFor(single, single.request));
  assert.ok(structureViewFor(zeroCost, zeroCost.request));

  const mismatched = [
    { ...single.request, symbol: "SPY" },
    { ...single.request, expiration: "2030-01-03" },
    { ...single.request, as_of: "2030-01-03" },
    { ...single.request, spot: 501 },
    { ...single.request, credit: -1.25 },
    { ...single.request, fees: 1 },
    { ...single.request, legs: [single.request.legs[0]] },
    { ...single.request, legs: [...single.request.legs].reverse() },
    { ...single.request, legs: [{ ...single.request.legs[0], strike: 501 }, single.request.legs[1]] },
    { ...single.request, legs: [{ ...single.request.legs[0], qty: 2 }, single.request.legs[1]] },
  ];
  for (const submitted of mismatched) {
    assert.equal(structureViewFor(single, submitted), null, JSON.stringify(submitted).slice(0, 120));
  }
  // A reordered comparison is not the submitted comparison, even if self-consistent.
  const reordered = {
    ...compared,
    request: { ...compared.request, structures: [...compared.request.structures].reverse() },
  };
  assert.ok(compareView(reordered));
  assert.equal(compareViewFor(reordered, compared.request), null);
});

test("a comparison must return each submitted scenario at its supplied position", () => {
  assert.ok(compareViewFor(compared, compared.request));
  assert.ok(compareViewFor(compared, {
    structures: compared.request.structures,
    thesis: compared.request.thesis,
  }));
  // An echoed thesis the caller never sent is also a mismatch.
  assert.equal(compareViewFor(compared, { structures: compared.request.structures }), null);

  // Internally valid, but the researched candidates no longer match their slots.
  const swapped = clone(compared);
  [swapped.research.candidates[0], swapped.research.candidates[1]] =
    [swapped.research.candidates[1], swapped.research.candidates[0]];
  assert.ok(compareView(swapped));
  assert.equal(compareViewFor(swapped, compared.request), null);

  const wrongLegs = clone(compared);
  wrongLegs.research.candidates[1].position.legs[0].strike = 501;
  assert.equal(compareViewFor(wrongLegs, compared.request), null);

  const wrongSymbol = clone(compared);
  wrongSymbol.research.candidates[0].underlying = "SPY";
  assert.equal(compareViewFor(wrongSymbol, compared.request), null);

  const wrongExpiration = clone(compared);
  wrongExpiration.research.candidates[0].expiration = "2030-01-03";
  assert.equal(compareViewFor(wrongExpiration, compared.request), null);

  assert.equal(compareViewFor(compared, {
    structures: [compared.request.structures[1], compared.request.structures[0]],
    thesis: compared.request.thesis,
  }), null);
  assert.equal(compareViewFor(compared, {
    structures: compared.request.structures,
    thesis: "a different thesis",
  }), null);
});

test("error codes map to safe operator-facing messages", () => {
  assert.match(structureMessage("invalid_structure"), /does not support this leg combination/);
  assert.match(structureMessage("backend_timeout"), /timed out/);
  assert.match(structureMessage("archive_unavailable"), /No substitute economics/);
  assert.equal(structureMessage("some_new_code"), structureMessage("research_unavailable"));
  assert.equal(JSON.stringify(structureMessage("some_new_code")).includes("some_new_code"), false);
});
