import { test } from "node:test";
import assert from "node:assert/strict";
import { prepareHistDataGold } from "../src/lib/pivex/histdata-history.ts";
import { runProxyBacktest } from "../src/lib/pivex/proxy-history.ts";
import { validateDataset } from "../src/lib/pivex/history.ts";

const bounds = {
  from: "2025-07-07T05:00:00Z",
  to: "2025-07-07T07:00:00Z",
  exportedAt: "2025-07-08T00:00:00Z",
  exportReference: "Synthetic HistData layout test",
};
const row = (i, price = 2000 + i) =>
  `20250707 ${String(Math.floor(i / 60)).padStart(2, "0")}${String(i % 60).padStart(2, "0")}00;${price};${price + 1};${price - 1};${price};0`;
const input = (rows) => Buffer.from(rows.join("\r\n") + "\r\n");
const all = Array.from({ length: 120 }, (_, i) => row(i));

test("HistData bid candles use fixed EST in summer, deduplicate and aggregate only complete windows", () => {
  const dataset = prepareHistDataGold(
    input([...all.filter((_, i) => i !== 64), all[2]]),
    bounds,
  );
  assert.equal(dataset.candles.m5[0].openTime, "2025-07-07T05:00:00.000Z");
  assert.equal(dataset.candles.m5[0].high, 2005);
  assert.equal(dataset.candles.m5[0].low, 1999);
  assert.equal(dataset.candles.m5[0].close, 2004);
  assert.deepEqual(dataset.quality.counts, { m5: 23, m15: 7, h1: 1 });
  assert.equal(dataset.quality.duplicates, 1);
  assert.equal(dataset.quality.outOfOrderTransitions, 1);
  assert.equal(dataset.quality.minutesExcludedFromIncompleteFiveMinuteBars, 4);
  assert.equal(dataset.quality.gaps[0].kind, "missing bars");
  assert.equal(dataset.quoteBasis, "bid");
  assert.equal(dataset.quoteBars, undefined);
  assert.throws(() => validateDataset(dataset));
  const result = runProxyBacktest(dataset, {
    ...bounds,
    splitAt: "2025-07-07T06:00:00Z",
    startingEquity: 10000,
    units: 1,
    riskBudget: 25,
    spreadFloor: 1,
    roundTripSlippage: 0.5,
    roundTripFees: 0.25,
    costsReference: "Synthetic fixed-cost test",
  });
  assert.equal(result.observationType, "bid_candles");
  assert.equal(result.development.bars, 12);
  assert.equal(result.validation.bars, 11);
  assert.equal(result.validation.incomplete, true);
});

test("HistData import rejects conflicting duplicates and invalid OHLC", () => {
  assert.throws(
    () => prepareHistDataGold(input([...all, row(2, 100)]), bounds),
    /Conflicting HistData/,
  );
  assert.throws(
    () =>
      prepareHistDataGold(
        input(["20250707 000000;2000;1999;1998;2001;0"]),
        bounds,
      ),
    /Invalid HistData/,
  );
  assert.throws(
    () =>
      prepareHistDataGold(
        input(["20250707 000000;2000;2001;1999;2000.0001;0"]),
        bounds,
      ),
    /Invalid HistData/,
  );
});
