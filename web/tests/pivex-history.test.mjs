import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createHash } from "node:crypto";
import { backtestFixture } from "../src/lib/pivex/backtest-fixture.ts";
import { replayWindow, runBacktest } from "../src/lib/pivex/backtest.ts";
import { validateDataset } from "../src/lib/pivex/history.ts";
import {
  prepareDukascopyHistory,
  runProxyBacktest,
} from "../src/lib/pivex/dukascopy-history.ts";

const five = 300_000;
const start = Date.parse("2026-10-30T20:00:00Z");
const at = (n) => new Date(start + n * five).toISOString();
const manifest = () => ({
  providerSymbol: "USATECH.IDX/USD",
  sourceReference: "Synthetic adapter test source",
  exportReference: "Synthetic paired quotes",
  rightsReference: "Generated test input",
  exportedAt: at(1000),
  from: at(0),
  to: at(24),
  quoteDecimals: 2,
  closedPeriods: [{ from: at(12), to: at(23), source: "Test closure" }],
});
const tick = (n, bid = 100 + n, ask = bid + 0.01) => ({ at: at(n), bid, ask });
const hash = () => "a".repeat(64);
const config = () => ({
  from: at(0),
  splitAt: at(12),
  to: at(24),
  startingEquity: 10000,
  riskBudget: 25,
  units: 1,
  spreadFloor: 0.01,
  roundTripSlippage: 0.02,
  roundTripFees: 0,
  costsReference: "Synthetic research assumptions",
});
const ticks = () => [
  ...Array.from({ length: 12 }, (_, i) => tick(i)),
  tick(23),
];

test("proxy normalization preserves quote side, stable same-time order, and complete aligned OHLC", async () => {
  const d = await prepareDukascopyHistory(
    manifest(),
    [tick(0), tick(0), tick(0, 102), tick(0), ...ticks().slice(1)],
    hash,
  );
  assert.equal(d.schema, 2);
  assert.equal(d.mode, "external_proxy");
  assert.equal(d.providerSymbol, "USATECH.IDX/USD");
  assert.equal(d.instrumentType, "index_cfd");
  assert.equal(d.tickSize, 0.005);
  assert.equal(d.quoteBars.bid.m5[0].high, 102);
  assert.equal(d.quoteBars.bid.m5[0].close, 100);
  assert.equal(d.quoteBars.ask.m5[0].open, 100.01);
  assert.equal(d.quoteBars.mid.m5[0].open, 100.005);
  assert.equal(d.quality.duplicateQuoteUpdates, 1);
  assert.deepEqual(d.quality.counts, { m5: 13, m15: 4, h1: 1 });
  assert.equal(d.candles.h1[0].close, d.candles.m15.at(-1).close);
  assert.equal(d.candles.h1[0].high, d.candles.m5[11].high);
  assert.equal(d.quality.gaps[0].slots, 11);
  assert.equal(d.quality.gaps[0].kind, "declared non-trading period");
  assert.throws(() => validateDataset(d));
  assert.throws(() => runBacktest(d, backtestFixture().config));
});

test("weekend gap spans the US fall DST change without changing UTC alignment", async () => {
  const m = manifest();
  m.providerSymbol = "XAU/USD";
  m.to = "2026-11-01T23:10:00Z";
  m.exportedAt = "2026-11-02T00:00:00Z";
  m.closedPeriods = [
    {
      from: "2026-10-30T21:00:00Z",
      to: "2026-11-01T23:00:00Z",
      source: "Fixture using 17:00 Friday / 18:00 Sunday America/New_York",
    },
  ];
  const d = await prepareDukascopyHistory(
    m,
    [
      ...ticks().slice(0, 12),
      { at: m.closedPeriods[0].to, bid: 100, ask: 101 },
    ],
    hash,
  );
  assert.equal(d.instrumentType, "rolling_spot_metal");
  assert.equal(d.quality.gaps[0].slots, 50 * 12);
  assert.equal(d.quality.gaps[0].kind, "declared non-trading period");
  assert.equal(d.quality.gaps[1].slots, 1);
  assert.equal(d.quality.gaps[1].kind, "missing bars");
  assert.equal(d.candles.m5.at(-1).closeTime, "2026-11-01T23:05:00.000Z");
});

test("missing open slots remain distinct from adjacent closures and suppress partial higher bars", async () => {
  const d = await prepareDukascopyHistory(
    manifest(),
    ticks().filter((t) => t.at !== at(11)),
    hash,
  );
  assert.deepEqual(
    d.quality.gaps.map((g) => [g.kind, g.slots]),
    [
      ["missing bars", 1],
      ["declared non-trading period", 11],
    ],
  );
  assert.equal(d.candles.h1.length, 0);
  assert.equal(d.candles.m15.length, 3);
});

test("proxy rejects unsupported instruments, unknown rights, wrong precision, dates and conflicting closures", async () => {
  for (const [m, rows] of [
    [{ ...manifest(), providerSymbol: "QQQ" }, ticks()],
    [{ ...manifest(), rightsReference: " " }, ticks()],
    [manifest(), [tick(0, 100.001)]],
    [manifest(), [tick(0, 100, 99)]],
    [manifest(), [tick(1), tick(0)]],
    [manifest(), [tick(12)]],
    [manifest(), [{ ...tick(0), at: "2026-10-30T16:00:00-04:00" }]],
  ])
    await assert.rejects(prepareDukascopyHistory(m, rows, hash));
});

test("proxy study partitions preserve earlier results when later quotes change", async () => {
  const before = await prepareDukascopyHistory(manifest(), ticks(), hash);
  const after = await prepareDukascopyHistory(
    manifest(),
    [...ticks().slice(0, -1), tick(23, 150)],
    hash,
  );
  const study = runProxyBacktest(before, config());
  assert.deepEqual(
    study.development,
    runProxyBacktest(after, config()).development,
  );
  assert.equal(study.development.evaluated, 12);
  assert.equal(study.validation.evaluated, 1);
  assert.equal(study.validation.curve[0].equity, 10000);
  assert.throws(() =>
    runProxyBacktest(before, { ...config(), spreadFloor: 0 }),
  );
  assert.throws(() =>
    runProxyBacktest(before, {
      ...config(),
      splitAt: new Date(start + 1).toISOString(),
    }),
  );
});

test("the next open can reject a previously qualified setup", () => {
  const { dataset, config } = backtestFixture();
  dataset.candles.m5[2].open = 155;
  const r = runBacktest(dataset, config).development;
  assert.equal(r.setups, 1);
  assert.equal(r.metrics.completed, 0);
  assert.equal(r.diagnostics["Insufficient net reward/risk"], 1);
});

test("observed proxy spread can reject a fill that passes declared broker costs", () => {
  const { dataset, config } = backtestFixture();
  const baseline = runBacktest(dataset, config).development;
  const result = replayWindow(
    dataset,
    config,
    config.from,
    config.splitAt,
    "proxy execution",
    (bar) =>
      Date.parse(bar.closeTime) ===
      Date.parse(baseline.trades[0].confirmationTime)
        ? {
            status: "CONFIRMED",
            direction: "long",
            confirmationTime: bar.closeTime,
            stop: baseline.trades[0].stop,
            target: baseline.trades[0].target,
            reason: "fixture",
          }
        : { status: "NO SETUP", reason: "fixture" },
    { entrySpreadTicks: () => 10 },
  );
  assert.equal(baseline.metrics.completed, 1);
  assert.equal(result.setups, 1);
  assert.equal(result.metrics.completed, 0);
  assert.equal(result.diagnostics["Insufficient net reward/risk"], 1);
});

test("offline CLI emits the input digest, data quality and separate chronological metrics", () => {
  const dir = mkdtempSync(join(tmpdir(), "pivex-history-"));
  try {
    const paths = [
      "manifest.json",
      "ticks.csv",
      "config.json",
      "report.json",
      "dataset.json",
    ].map((f) => join(dir, f));
    const csv =
      [
        "timestamp,bid,ask",
        ...ticks().map((t) => [t.at, t.bid, t.ask].join(",")),
      ].join("\r\n") + "\r\n";
    writeFileSync(paths[0], JSON.stringify(manifest()));
    writeFileSync(paths[1], csv);
    writeFileSync(paths[2], JSON.stringify(config()));
    const child = spawnSync(
      process.execPath,
      ["scripts/pivex-history.mjs", ...paths],
      { encoding: "utf8" },
    );
    assert.equal(child.status, 0, child.stderr);
    const report = JSON.parse(readFileSync(paths[3], "utf8"));
    const dataset = JSON.parse(readFileSync(paths[4], "utf8"));
    assert.equal(
      report.provenance.inputSha256,
      createHash("sha256").update(csv).digest("hex"),
    );
    assert.equal(report.development.evaluated, 12);
    assert.equal(report.validation.evaluated, 1);
    assert.equal(dataset.quoteBars.mid.m5.length, 13);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

for (const direction of ["long", "short", "chop"]) {
  test(`paired-quote replay evaluates ${direction} conditions across a documented warm-up closure`, async () => {
    const prices = [];
    const h1End = 25 * 12;
    const add = (slot, values) => {
      for (const [i, value] of values.entries()) {
        const mid = direction === "short" ? 300 - value : value;
        prices.push({
          at: new Date(start + slot * five + i * 1000).toISOString(),
          bid: mid - 0.01,
          ask: mid + 0.01,
        });
      }
    };
    for (let i = 0; i < h1End - 12; i++) {
      const h = Math.floor(i / 12);
      if (h === 10) continue;
      const mid = direction === "chop" ? 140 : 100 + h * 1.5;
      add(i, i === 0 ? [mid, 180, mid] : [mid]);
    }
    const finalHour = [
      [146],
      [147],
      [147],
      [147, 146, 149],
      [148],
      [148],
      [148, 144, 149],
      [147],
      [146],
      [146, 145, 151],
      [150],
      [150],
    ];
    for (const [i, values] of finalHour.entries()) add(h1End - 12 + i, values);
    add(h1End, [150, 149]);
    add(h1End + 1, [149, 151]);
    add(h1End + 2, [148, 168]);
    add(h1End + 3, [149]);
    const m = {
      ...manifest(),
      to: at(h1End + 4),
      closedPeriods: [
        { from: at(120), to: at(132), source: "Fixture maintenance" },
      ],
    };
    const c = {
      ...config(),
      from: at(h1End),
      splitAt: at(h1End + 3),
      to: m.to,
    };
    const dataset = await prepareDukascopyHistory(m, prices, hash);
    const result = runProxyBacktest(dataset, c);
    if (direction === "chop") {
      assert.equal(result.development.metrics.completed, 0);
      assert(
        result.development.diagnostics[
          "CHOP: EMA20 and completed hourly swing structure do not agree"
        ],
      );
    } else {
      assert.equal(result.development.setups, 1);
      assert.equal(result.development.metrics.completed, 1);
      assert.equal(result.development.trades[0].direction, direction);
      assert.equal(result.development.trades[0].outcome, "target");
      assert(result.development.trades[0].r >= 2);
      assert.equal(result.validation.metrics.completed, 0);
    }
  });
}
