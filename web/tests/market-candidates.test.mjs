import assert from "node:assert/strict";
import { test } from "node:test";
import { buyingPower, candidateViews, archiveExpirations } from "../src/lib/market-candidates.ts";

test("buying power accepts positive decimals and rejects invalid inputs without defaults", () => {
  for (const amount of [100,150,500,2000,5000,150.75]) assert.equal(buyingPower(String(amount)), amount);
  assert.equal(buyingPower(".50"), .5);
  assert.equal(buyingPower("100."), 100);
  for (const value of ["", " ", "0", "-1", "abc", "Infinity", "NaN", "1e309", "0x10", "1,000"]) assert.equal(buyingPower(value), null);
});
test("all backend families preserve economics, positions and evidence without rankings", () => {
  for (const family of ["long_call","long_put","call_debit_spread","put_debit_spread","put_credit_spread","call_credit_spread","butterfly","bullish_bwb","bearish_bwb","iron_condor"]) {
    const research = {strategy_family: family, max_loss: 120, max_profit: 380, capital_at_risk:120,
      breakevens:[99,101], trade:{expiration:"2030-01-02"}, position:{legs:[{type:"Call",qty:1,strike:100}]},
      historical_economics:{eligible_for_consideration:false,missing_evidence:["quote_evidence_missing"]}};
    const [view] = candidateViews({available_capital:150,candidates:[{research}],excluded:[]});
    assert.equal(view.research.strategy_family, family);
    for (const key of ["max_loss","max_profit","capital_at_risk","breakevens","historical_economics"]) assert.deepEqual(view.research[key], research[key]);
    assert.deepEqual(view.research.legs,research.position.legs);
    assert.match(view.capital_status,/Capital-eligible/);
    assert.equal(view.research.ranking,undefined);
  }
});
test("capital exclusions remain visible; missing risk never becomes affordable", () => {
  const research={capital_at_risk:220,max_loss:220,max_profit:"unlimited",premium_per_share:2.2,trade:{expiration:"2030-01-02",legs:[]}};
  const [low] = candidateViews({available_capital:150,candidates:[],excluded:[{reason:"exceeds_available_capital",research}]});
  const [high] = candidateViews({available_capital:500,candidates:[{research}],excluded:[]});
  assert.equal(low.capital_status,"Capital-ineligible");
  assert.match(high.capital_status,/Capital-eligible/);
  assert.deepEqual(low.research,high.research);
  assert.equal(high.research.max_profit,"unlimited");
  assert.equal(high.research.entry_debit,2.2);
  assert.equal(candidateViews({candidates:[{research:{}}]})[0].capital_status,"Capital eligibility unavailable");
  assert.equal(candidateViews({candidates:[{research:{}}]})[0].research.max_loss,undefined);
  assert.deepEqual(candidateViews({candidates:[],excluded:[]}),[]);
});
test("expiration choices originate only in backend archive diagnostics", () => {
  assert.deepEqual(archiveExpirations({}),[]);
  assert.deepEqual(archiveExpirations({diagnostics:{expiration_selection:{available:["2030-01-04","2030-01-02","invalid","2030-01-02"]}}}),["2030-01-02","2030-01-04"]);
});

test("failed archived expirations are not offered as available chains", () => {
  assert.deepEqual(archiveExpirations({diagnostics:{expiration_selection:{available:["2030-01-02","2030-01-04"]}},
    market:{archive_observation:{expiration_failures:[{expiration:"2030-01-04",reason:"provider_failure"}]}}}),["2030-01-02"]);
});
