import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import {
  validateQuickReport,
  indicativeProgress,
} from "../src/lib/pivex/progress.ts";
import { defaultRules, riskState } from "../src/lib/pivex/challenge.ts";
import {
  validateLedger,
  mergeLocalBackup,
  saveLedger,
  loadLedger,
} from "../src/lib/pivex/journal.ts";
import { backtestFixture } from "../src/lib/pivex/backtest-fixture.ts";
import { runBacktest, backtestMetrics } from "../src/lib/pivex/backtest.ts";
import {
  HistoricalExportAdapter,
  validateDataset,
} from "../src/lib/pivex/history.ts";
import {
  protectWebsite,
  issueSession,
  SESSION_COOKIE,
} from "../src/lib/website-auth.ts";
import { authBindings } from "./auth-fixture.mjs";
const now = "2026-11-10T14:00:00Z";
const report = () => ({
  schema: 1,
  id: "quick-1",
  kind: "user_reported",
  source: "Manual test report",
  observedAt: now,
  valueType: "equity",
  value: 10250,
  realizedToday: 20,
  floatingPnl: null,
  fees: null,
  openRisk: null,
});
const ledger = () => ({
  schema: 1,
  rules: [defaultRules],
  snapshot: null,
  trades: [],
  specs: [],
});
const replay = (f = backtestFixture()) => runBacktest(f.dataset, f.config);

test("quick progress is indicative, source-bound, and cannot authorize risk", () => {
  const q = validateQuickReport(report(), now),
    p = indicativeProgress(q, defaultRules);
  assert.equal(p.remaining, 750);
  assert.equal(p.progress, 0.25);
  assert.equal(p.compliance, "UNVERIFIED");
  assert.equal(p.riskAllowance, null);
  assert.equal(riskState(q, defaultRules, now).verified, false);
  assert.equal(q.source, "Manual test report");
  assert.equal(p.observedAt, now);
});
test("reported balance without floating equity remains balance-based", () => {
  const q = { ...report(), valueType: "balance" },
    p = indicativeProgress(q, defaultRules);
  assert.equal(p.equity, null);
  assert.equal(p.balance, 10250);
  assert.equal(p.basis, "reported balance");
  q.floatingPnl = -300;
  assert.equal(indicativeProgress(q, defaultRules).equity, 9950);
  assert.equal(indicativeProgress(q, defaultRules).remaining, 1050);
});
for (const [name, change] of [
  ["nonfinite", (q) => (q.value = Infinity)],
  ["negative fees", (q) => (q.fees = -1)],
  ["negative risk", (q) => (q.openRisk = -1)],
  ["future time", (q) => (q.observedAt = "2026-11-11T00:00:00Z")],
  ["missing source", (q) => (q.source = "")],
  ["invalid date", (q) => (q.observedAt = "2026-02-31T00:00:00Z")],
  ["false verified source", (q) => (q.kind = "broker_verified")],
  ["missing optional evidence", (q) => delete q.floatingPnl],
])
  test(`quick input rejects ${name}`, () => {
    const q = report();
    change(q);
    assert.throws(() => validateQuickReport(q, now));
  });
test("reported fees are never silently subtracted twice or converted into daily risk", () => {
  const q = { ...report(), fees: 5, openRisk: 10 };
  const p = indicativeProgress(q, defaultRules);
  assert.equal(p.dailyResult, 20);
  assert.equal(p.riskAllowance, null);
});
test("old local backup remains compatible and duplicate quick IDs fail", () => {
  assert.deepEqual(validateLedger(ledger()), ledger());
  const l = { ...ledger(), quickReports: [report()] };
  assert.equal(validateLedger(l), l);
  assert.throws(() =>
    validateLedger({ ...l, quickReports: [report(), report()] }),
  );
});
test("local merge is idempotent, conflict-safe and profile-isolated", () => {
  const incoming = { ...ledger(), quickReports: [report()] },
    merged = mergeLocalBackup(ledger(), incoming);
  assert.deepEqual(mergeLocalBackup(merged, incoming), merged);
  assert.equal(merged.quickReports.length, 1);
  assert.equal(merged.snapshot, null);
  assert.throws(
    () =>
      mergeLocalBackup(merged, {
        ...incoming,
        quickReports: [{ ...report(), value: 9999 }],
      }),
    /Conflicting/,
  );
  const map = new Map(),
    store = {
      getItem: (k) => map.get(k) ?? null,
      setItem: (k, v) => map.set(k, v),
    };
  saveLedger(store, "one", merged);
  assert.deepEqual(loadLedger(store, "one"), merged);
  assert.equal(loadLedger(store, "two"), null);
});
test("current active rule survives merging older distinct rule provenance", () => {
  const current = {
    ...ledger(),
    rules: [defaultRules, { ...defaultRules, version: "current-v2" }],
  };
  const incoming = {
    ...ledger(),
    rules: [{ ...defaultRules, version: "older" }],
  };
  assert.equal(
    mergeLocalBackup(current, incoming).rules.at(-1).version,
    "current-v2",
  );
});
test("historical adapter cuts future bars and targets while preserving source", async () => {
  const { dataset: d } = backtestFixture(),
    a = new HistoricalExportAdapter(d),
    e = await a.load("NAS100", "2026-11-09T00:10:00Z");
  assert.equal(e.source, d.source);
  assert(
    e.candles.h1.every(
      (c) => Date.parse(c.closeTime) <= Date.parse("2026-11-09T00:05:00Z"),
    ),
  );
  assert.equal(e.target.observedAt, d.targets[0].observedAt);
  await assert.rejects(a.load("QQQ", e.asOf));
});
for (const [name, change] of [
  ["ETF proxy", (d) => (d.mapping.providerSymbol = "QQQ")],
  ["wrong instrument", (d) => (d.mapping.instrument = "XAUUSD")],
  ["missing license", (d) => (d.mapping.rightsReference = "")],
  ["spot substitution", (d) => (d.mapping.instrumentType = "spot")],
  ["unfinished", (d) => (d.candles.m5[0].complete = false)],
  ["misaligned", (d) => (d.candles.m15[0].openTime = "2026-11-08T23:16:00Z")],
  ["off-tick", (d) => (d.candles.m5[0].open = 149.1)],
])
  test(`historical import rejects ${name}`, () => {
    const f = backtestFixture();
    change(f.dataset);
    assert.throws(() => validateDataset(f.dataset));
  });
for (const direction of ["long", "short"])
  test(`deterministic ${direction} replay uses next open, fixed original strategy and independent partitions`, () => {
    const f = backtestFixture(direction),
      r = replay(f);
    assert.deepEqual(replay(f), r);
    assert.equal(r.development.setups, 1);
    assert.equal(r.development.metrics.completed, 1);
    const t = r.development.trades[0];
    assert.equal(t.entryTime, "2026-11-09T00:10:00Z");
    assert.equal(t.entry, direction === "long" ? 149 : 151);
    assert.equal(t.costs, 3);
    assert.equal(t.initialRisk, 15);
    assert.equal(t.netPnl, 33);
    assert.equal(t.r, 2.2);
    assert.equal(r.validation.metrics.netPnl, -15);
    assert.equal(r.validation.curve[0].equity, 10000);
    assert.equal(r.validation.metrics.maxDrawdown, 15);
    assert.equal(r.validation.metrics.consecutiveLosses, 1);
  });
test("unseen future candles and targets cannot change development results", () => {
  const f = backtestFixture(),
    before = replay(f).development;
  f.dataset.candles.h1.at(-1).close = 149;
  f.dataset.targets.at(-1).price = 999;
  assert.deepEqual(replay(f).development, before);
});
test("EMA warm-up and missing higher-timeframe coverage cannot create setups", () => {
  const f = backtestFixture();
  f.dataset.candles.h1 = f.dataset.candles.h1.slice(2);
  assert.equal(replay(f).development.setups, 0);
  assert(
    Object.keys(replay(f).development.diagnostics).some((k) =>
      /Missing completed/.test(k),
    ),
  );
});
test("wick-only breakout remains unconfirmed", () => {
  const f = backtestFixture();
  f.dataset.candles.m5[1].close = 148;
  assert.equal(replay(f).development.setups, 0);
});
test("extra commission rejects a nominally attractive entry after costs", () => {
  const f = backtestFixture();
  f.config.spec.commissionPerLot = 3;
  const r = replay(f);
  assert.equal(r.development.metrics.completed, 0);
  assert(r.development.diagnostics["Insufficient net reward/risk"] === 1);
});
test("FX, ticks and declared lots affect net results exactly once", () => {
  const f = backtestFixture();
  f.config.lots = 0.5;
  f.config.spec.quoteToAccount = 2;
  const t = replay(f).development.trades[0];
  assert.equal(t.costs, 2.5);
  assert.equal(t.initialRisk, 14.5);
  assert.equal(t.netPnl, 33.5);
});
test("invalid lot increment or contract mapping cannot run", () => {
  for (const change of [
    (f) => (f.config.lots = 0.15),
    (f) => (f.config.spec.brokerSymbol = "WRONG"),
    (f) => (f.config.spec.tickSize = 1),
    (f) => (f.config.riskBudget = 26),
  ]) {
    const f = backtestFixture();
    change(f);
    assert.throws(() => replay(f));
  }
});
test("same-bar stop and target is ambiguous and conservatively a modeled loss", () => {
  const f = backtestFixture();
  f.dataset.candles.m5[2].low = 142;
  const r = replay(f).development;
  assert.equal(r.trades[0].outcome, "ambiguous_stop_first");
  assert.equal(r.trades[0].netPnl, -15);
  assert.equal(r.metrics.winRate, 0);
});
test("no exact next candle means no fabricated entry", () => {
  const f = backtestFixture();
  f.dataset.candles.m5[2].openTime = "2026-11-09T00:15:00Z";
  f.dataset.candles.m5[2].closeTime = "2026-11-09T00:20:00Z";
  const r = replay(f).development;
  assert.equal(r.metrics.completed, 0);
  assert.equal(r.trades.length, 0);
  assert(r.diagnostics["missing bars"]);
  assert.equal(r.entryAudit.length, r.setups);
  assert.equal(
    r.entryAudit[0].primaryRejectionReason,
    "Missing contiguous next candle",
  );
  assert.equal(r.entryAudit[0].nextOpen, null);
});
function flatEntry(f) {
  Object.assign(f.dataset.candles.m5[2], { high: 150, low: 148, close: 149 });
}
test("missing bar during a position stops replay with unresolved P&L", () => {
  const f = backtestFixture();
  flatEntry(f);
  f.dataset.candles.m5.splice(3, 0, {
    openTime: "2026-11-09T00:20:00Z",
    closeTime: "2026-11-09T00:25:00Z",
    open: 149,
    high: 150,
    low: 142,
    close: 143,
    complete: true,
  });
  const r = replay(f).development;
  assert.equal(r.terminated, true);
  assert.equal(r.trades[0].netPnl, null);
  assert.equal(r.metrics.completed, 0);
  assert.equal(r.curve.length, 1);
});
test("gapped stop uses an observed adverse open and can exceed planned risk", () => {
  const f = backtestFixture();
  flatEntry(f);
  f.dataset.candles.m5.splice(3, 0, {
    openTime: "2026-11-09T00:15:00Z",
    closeTime: "2026-11-09T00:20:00Z",
    open: 140,
    high: 141,
    low: 139,
    close: 140,
    complete: true,
  });
  const t = replay(f).development.trades[0];
  assert.equal(t.outcome, "gap_stop");
  assert.equal(t.exit, 140);
  assert.equal(t.netPnl, -21);
  assert(t.netPnl < -t.initialRisk);
});
test("window-end open position is not forcibly closed", () => {
  const f = backtestFixture();
  flatEntry(f);
  const r = replay(f).development;
  assert.equal(r.incomplete, true);
  assert.equal(r.trades[0].outcome, "unresolved");
  assert.equal(r.trades[0].exit, null);
  assert.equal(r.metrics.completed, 0);
});
test("coverage edges and declared closures are explicit rather than silently filled", () => {
  const f = backtestFixture();
  f.dataset.closedPeriods = [
    {
      from: "2026-11-09T00:15:00Z",
      to: "2026-11-10T00:00:00Z",
      source: "Synthetic closed-period declaration, not broker calendar",
    },
  ];
  const r = replay(f);
  assert.equal(r.development.incomplete, true);
  assert(r.development.diagnostics["Trailing declared non-trading period"]);
  assert(r.validation.diagnostics["Leading declared non-trading period"]);
  f.dataset.closedPeriods[0].from = "2026-11-09T00:10:00Z";
  assert.throws(() => validateDataset(f.dataset), /conflicts/);
});
test("chronological equity drawdown and consecutive losses include fees", () => {
  const template = replay().development.trades[0],
    trades = [33, -15, -21, 10].map((netPnl, i) => ({
      ...template,
      exitTime: `2026-11-09T01:${String(i * 5).padStart(2, "0")}:00Z`,
      netPnl,
      r: netPnl / 15,
    }));
  const m = backtestMetrics(trades, 10000);
  assert.equal(m.maxDrawdown, 36);
  assert.equal(m.consecutiveLosses, 2);
  assert.equal(m.profitFactor, 43 / 36);
  assert.equal(m.netPnl, 7);
  assert.equal(m.winRate, 0.5);
  assert.equal(m.averageWinner, 21.5);
  assert.equal(m.averageLoser, -18);
  assert.equal(m.expectancyR, m.averageR);
});
test("split cannot overlap or bisect a bar", () => {
  for (const splitAt of [
    "2026-11-08T00:00:00Z",
    "2026-11-10T01:00:00Z",
    "2026-11-09T00:07:00Z",
  ]) {
    const f = backtestFixture();
    f.config.splitAt = splitAt;
    assert.throws(() => replay(f));
  }
});
test("unauthorized persistence remains blocked; no cloud journal route or service key is introduced", async () => {
  const env = { ...authBindings },
    limiter = {
      externalLoginRateLimiter: {
        limit: async () => ({ allowed: true, retryAfterSeconds: 60 }),
      },
    },
    origin = "https://website.test";
  let reached = false;
  const next = async () => {
    reached = true;
    return new Response(null, { status: 404 });
  };
  assert.equal(
    (
      await protectWebsite(
        new Request(origin + "/api/pivex/journal"),
        env,
        next,
        limiter,
      )
    ).status,
    401,
  );
  assert.equal(reached, false);
  const cookie = `${SESSION_COOKIE}=${await issueSession(env, origin)}`;
  assert.equal(
    (
      await protectWebsite(
        new Request(origin + "/api/pivex/journal", {
          method: "POST",
          headers: { cookie, origin: "https://evil.test" },
        }),
        env,
        next,
        limiter,
      )
    ).status,
    403,
  );
  assert.equal(reached, false);
  assert(!existsSync("src/app/api/pivex/journal/route.ts"));
  const ui =
    readFileSync("src/components/pivex/QuickAccountUpdate.tsx", "utf8") +
    readFileSync("src/components/pivex/BacktestResearch.tsx", "utf8");
  assert.doesNotMatch(ui, /SERVICE_ROLE|fetch\s*\(|submitOrder|placeOrder/);
});
