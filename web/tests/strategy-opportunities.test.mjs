import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { assessStrategyCandidates } from "../src/lib/strategy-opportunities.ts";

const fixtures = JSON.parse(readFileSync(new URL("./fixtures/market-parity.json", import.meta.url), "utf8"));

function fixture(symbol, capital) {
  const found = fixtures.find((item) => item.request.symbol === symbol && item.request.available_capital === capital);
  assert.ok(found, `missing fixture for ${symbol} and ${capital}`);
  const research = found.response.research;
  return {
    session: research.research_session,
    archive: research.archive,
    asOf: research.as_of,
  };
}

function assess(data, symbol, capital, mode = "current") {
  return assessStrategyCandidates(data.session, data.archive, symbol, capital, mode, data.asOf);
}

test("SPY and QQQ candidates use backend max-loss decisions and verified exact quote evidence", () => {
  for (const symbol of ["SPY", "QQQ"]) {
    const data = fixture(symbol, 150);
    const results = assess(data, symbol, 150);
    assert.ok(results.some((item) => item.status === "eligible"));
    assert.ok(results.every((item) => item.status !== "unavailable"));
    assert.ok(results.every((item) => item.candidate.research.legs.every((leg) =>
      leg.contract && leg.archive_quality === "valid_contracts" && leg.bid_timestamp && leg.ask_timestamp)));
  }
});

test("changing buying power does not promote a contract the backend rejected", () => {
  const lowerBudget = fixture("SPY", 150);
  const initial = assess(lowerBudget, "SPY", 150);
  assert.equal(initial.filter((item) => item.status === "eligible").length, 1);
  assert.equal(initial.filter((item) => item.status === "unaffordable").length, 1);

  const editedBudgetWithoutBackendResearch = assess(lowerBudget, "SPY", 500);
  assert.equal(editedBudgetWithoutBackendResearch.filter((item) => item.status === "eligible").length, 0);
  assert.ok(editedBudgetWithoutBackendResearch.every((item) => item.status !== "unaffordable"));

  const rerunAtNewBudget = assess(fixture("SPY", 500), "SPY", 500);
  assert.equal(rerunAtNewBudget.filter((item) => item.status === "eligible").length, 2);
});

test("missing, stale, questionable, or mismatched archive and quote evidence fail closed", () => {
  const staleQuote = structuredClone(fixture("SPY", 150));
  delete staleQuote.session.candidates[0].research.position.legs[0].ask_timestamp;
  const staleQuoteResults = assess(staleQuote, "SPY", 150);
  assert.equal(staleQuoteResults.filter((item) => item.status === "eligible").length, 0);
  assert.equal(staleQuoteResults[0].status, "unavailable");

  const staleArchive = structuredClone(fixture("SPY", 150));
  staleArchive.archive.freshness.age_seconds = staleArchive.archive.freshness.max_age_seconds + 1;
  assert.ok(assess(staleArchive, "SPY", 150).every((item) => item.status === "unavailable"));

  const questionableArchive = structuredClone(fixture("SPY", 150));
  questionableArchive.archive.observation.options_status = "partial";
  assert.ok(assess(questionableArchive, "SPY", 150).every((item) => item.status === "unavailable"));

  const changedRisk = structuredClone(fixture("SPY", 150));
  changedRisk.session.candidates[0].research.historical_economics.capital_eligibility.status = "not_assessed";
  const riskResults = assess(changedRisk, "SPY", 150);
  assert.equal(riskResults.filter((item) => item.status === "eligible").length, 0);
  assert.equal(riskResults[0].status, "unavailable");

  const unsupported = structuredClone(fixture("SPY", 150));
  unsupported.session.candidates[0].classification_supported = false;
  const unsupportedResults = assess(unsupported, "SPY", 150);
  assert.equal(unsupportedResults.filter((item) => item.status === "eligible").length, 0);
  assert.equal(unsupportedResults[0].status, "unavailable");
});

test("historical snapshots and budget-mismatched API responses never produce current eligibility", () => {
  const data = fixture("QQQ", 150);
  assert.ok(assess(data, "QQQ", 150, "historical").every((item) => item.status === "unavailable"));
  assert.ok(assess(data, "QQQ", 2000).every((item) => item.status === "unavailable"));
});

test("capital-excluded contracts require an explicit backend reason and verified risk", () => {
  const data = fixture("SPY", 150);
  const unaffordable = assess(data, "SPY", 150).filter((item) => item.status === "unaffordable");
  assert.equal(unaffordable.length, 1);
  assert.equal(unaffordable[0].candidate.reason, "exceeds_available_capital");
  assert.equal(unaffordable[0].candidate.required_capital, 481.3);

  const untrusted = structuredClone(data);
  untrusted.session.excluded[0].required_capital = 100;
  assert.equal(assess(untrusted, "SPY", 150).filter((item) => item.status === "unaffordable").length, 0);
});
