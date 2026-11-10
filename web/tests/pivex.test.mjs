import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync, readdirSync } from "node:fs";
import { fixture } from "../src/lib/pivex/fixtures.ts";
import {
  ManualHistoricalAdapter,
  timestamp,
} from "../src/lib/pivex/evidence.ts";
import { analyze } from "../src/lib/pivex/strategy.ts";
import {
  defaultRules,
  validateRules,
  validateSnapshot,
  riskState,
  weekStart,
} from "../src/lib/pivex/challenge.ts";
import { plan, validateSpec } from "../src/lib/pivex/planner.ts";
import {
  performance,
  validateTrade,
  loadLedger,
  saveLedger,
  storageKey,
  validateLedger,
} from "../src/lib/pivex/journal.ts";
import {
  protectWebsite,
  issueSession,
  SESSION_COOKIE,
} from "../src/lib/website-auth.ts";
import { authBindings } from "./auth-fixture.mjs";
const now = "2026-11-10T14:00:00Z";
test("manual adapter is source-bound, immutable and never proxies an ETF", async () => {
  const original = fixture(),
    adapter = new ManualHistoricalAdapter(original);
  original.source = "changed";
  const result = await adapter.load("NAS100", "2026-11-09T00:10:00Z");
  assert.match(result.source, /SYNTHETIC/);
  result.source = "changed again";
  assert.match((await adapter.load("NAS100", result.asOf)).source, /SYNTHETIC/);
  await assert.rejects(adapter.load("QQQ", result.asOf));
  await assert.rejects(adapter.load("NAS100", "2026-11-09T00:15:00Z"));
  assert(!timestamp("2026-02-31T00:00:00Z"));
  assert(!timestamp("2026Z"));
});
test("numeric underflow cannot produce a modeled NaN position", () => {
  const p = input();
  p.spec.tickValue = Number.MIN_VALUE;
  p.spec.quoteToAccount = Number.MIN_VALUE;
  p.spec.commissionPerLot = 0;
  assert.equal(plan(p).size, null);
});
test("zero and negative attested equity report breaches instead of disappearing", () => {
  for (const equity of [0, -10]) {
    const s = snapshot();
    s.equity = equity;
    const r = riskState(s, defaultRules, now);
    assert.equal(r.verified, true);
    assert(r.overallHeadroom < 0);
    assert.equal(plan({ ...input(), snapshot: s }).size, null);
  }
});
const snapshot = () => ({
  asOf: now,
  source: "synthetic account fixture, not user data",
  attested: true,
  equity: 10000,
  realizedPnl: 0,
  floatingPnl: 0,
  fees: 0,
  exposure: 0,
  openRisk: 0,
  dailyBaseline: { at: "2026-11-10T00:00:00Z", equity: 10000 },
  weeklyBaseline: { at: "2026-11-09T00:00:00Z", equity: 10000 },
  tradesToday: 0,
  lossesToday: 0,
});
const spec = () => ({
  instrument: "NAS100",
  brokerSymbol: "SYNTHETIC",
  source: "unit test only",
  verifiedAt: now,
  attested: true,
  tickSize: 0.5,
  tickValue: 1,
  quoteToAccount: 1,
  minLot: 0.1,
  maxLot: 100,
  lotStep: 0.1,
  spreadTicks: 1,
  slippageTicks: 1,
  commissionPerLot: 1,
  fixedFees: 0,
  costsSource: "fixture",
  marketHours: "fixture only",
  permitted: true,
});
const input = () => ({
  entry: 100,
  stop: 95,
  target: 120,
  budget: 25,
  spec: spec(),
  snapshot: snapshot(),
  rules: defaultRules,
  now,
});
const trade = (
  id = "t1",
  pnl = 50,
  entryTime = "2026-11-09T14:00:00Z",
  exitTime = "2026-11-09T15:00:00Z",
) => ({
  id,
  ruleVersion: defaultRules.version,
  instrument: "NAS100",
  direction: "long",
  entryTime,
  exitTime,
  entry: 100,
  exit: 110,
  stop: 95,
  target: 115,
  size: 1,
  fees: 0,
  otherCosts: 0,
  realizedPnl: pnl,
  initialRisk: 25,
  setup: "trend-pullback-breakout",
  adherence: "unknown",
  exitReason: "target",
  source: "test statement",
});
for (const direction of ["long", "short"])
  test(`completed ${direction} setup is reproducible and next candle only`, () => {
    const e = fixture(direction),
      s = analyze(e);
    assert.equal(s.status, "CONFIRMED");
    assert.equal(s.direction, direction);
    assert.equal(s.rewardRisk, 2);
    assert.match(s.reason, /next-candle/);
    assert.deepEqual(analyze(e), s);
  });
test("choppy hourly structure blocks setup", () =>
  assert.equal(analyze(fixture("chop")).status, "CHOP"));
test("false intrabar breakout does not confirm", () => {
  const e = fixture();
  e.candles.m5.at(-1).close = 148;
  assert.equal(analyze(e).status, "NO SETUP");
});
test("unconfirmed 15m pullback does not qualify", () => {
  const e = fixture();
  e.candles.m15.at(-1).close = 147;
  e.candles.h1.at(-1).close = 147;
  assert.equal(analyze(e).status, "NO SETUP");
});
test("inconsistent cross-timeframe prices fail closed", () => {
  const e = fixture();
  e.candles.h1.at(-1).close = 148;
  assert.equal(analyze(e).status, "UNAVAILABLE");
});
for (const tf of ["h1", "m15", "m5"])
  test(`incomplete/missing ${tf} evidence is unavailable`, () => {
    const e = fixture();
    e.candles[tf].at(-1).complete = false;
    assert.equal(analyze(e).status, "UNAVAILABLE");
    e.candles[tf] = [];
    assert.equal(analyze(e).status, "UNAVAILABLE");
  });
test("gaps, duplicate timestamps and invalid OHLC rejected", () => {
  for (const mutate of [
    (e) => e.candles.h1.splice(4, 1),
    (e) => e.candles.h1.splice(4, 0, e.candles.h1[4]),
    (e) => (e.candles.m5.at(-1).high = 1),
  ]) {
    const e = fixture();
    mutate(e);
    assert.equal(analyze(e).status, "UNAVAILABLE");
  }
});
test("cross timeframe lookahead cannot confirm a signal", () => {
  const e = fixture(),
    expected = analyze(e);
  const future = {
    ...e.candles.m15.at(-1),
    openTime: "2026-11-09T00:00:00Z",
    closeTime: "2026-11-09T00:15:00Z",
    close: 999,
    high: 999,
  };
  e.candles.m15.push(future);
  assert.equal(analyze(e).status, expected.status);
  assert.equal(analyze(e).stop, expected.stop);
  e.candles.h1.pop();
  assert.equal(analyze(e).status, "UNAVAILABLE");
});
test("future target or insufficient target room cannot validate setup", () => {
  const e = fixture();
  e.target.observedAt = e.asOf;
  assert.equal(analyze(e).status, "NO SETUP");
  e.target.observedAt = "2026-11-08T23:00:00Z";
  e.target.price = 152;
  assert.equal(analyze(e).status, "NO SETUP");
});
test("ETF proxies, invalid prices and absent provenance rejected", () => {
  for (const mutate of [
    (e) => (e.instrument = "QQQ"),
    (e) => (e.source = ""),
    (e) => (e.tickSize = 0),
    (e) => (e.candles.m5.at(-1).close = NaN),
  ]) {
    const e = fixture();
    mutate(e);
    assert.equal(analyze(e).status, "UNAVAILABLE");
  }
});
test("risk sizing includes costs, FX and lot rounding", () => {
  const p = input(),
    r = plan(p);
  assert.equal(r.status, "MODELED");
  assert.equal(r.size, 1.9);
  assert.equal(r.loss, 24.7);
  assert(r.rr >= 2);
  assert(r.loss <= 25);
  p.spec.quoteToAccount = 2;
  const converted = plan(p);
  assert.equal(converted.size, 1);
  assert.equal(converted.loss, 25);
});
test("minimum lots, off-tick prices and fee effects fail safely", () => {
  let p = input();
  p.spec.minLot = 10;
  assert.equal(plan(p).status, "NO TRADE");
  p = input();
  p.entry = 100.1;
  assert.equal(plan(p).size, null);
  p = input();
  p.target = 110;
  assert.match(plan(p).reason, /2:1/);
  p = input();
  p.spec.fixedFees = 30;
  assert.equal(plan(p).size, null);
});
test("short direction, max lot and nonzero minimum step anchored correctly", () => {
  const p = input();
  p.stop = 105;
  p.target = 80;
  p.spec.minLot = 0.15;
  p.spec.maxLot = 0.8;
  p.spec.lotStep = 0.2;
  const r = plan(p);
  assert.equal(r.status, "MODELED");
  assert.equal(r.direction, "short");
  assert.equal(r.size, 0.75);
});
for (const key of [
  "tickSize",
  "tickValue",
  "quoteToAccount",
  "minLot",
  "lotStep",
])
  test(`invalid ${key} cannot qualify position size`, () => {
    const p = input();
    p.spec[key] = 0;
    assert.equal(plan(p).size, null);
  });
test("missing specs, costs, equity and stale evidence cannot qualify sizing", () => {
  for (const change of [
    (p) => (p.spec = null),
    (p) => (p.spec.costsSource = ""),
    (p) => (p.snapshot = null),
    (p) => (p.snapshot.attested = false),
    (p) => (p.spec.verifiedAt = "2026-11-08T00:00:00Z"),
    (p) => (p.now = "2026-11-10T14:16:00Z"),
  ]) {
    const p = input();
    change(p);
    assert.equal(plan(p).size, null);
  }
  assert.throws(() => validateSpec({ ...spec(), spreadTicks: undefined }));
  assert.throws(() =>
    validateSnapshot({ ...snapshot(), floatingPnl: undefined }),
  );
});
test("daily reset requires new exact 00:00 UTC equity, never prior day carry", () => {
  const s = snapshot();
  s.asOf = "2026-11-11T00:00:00Z";
  assert.equal(riskState(s, defaultRules, s.asOf).verified, false);
  s.dailyBaseline = { at: "2026-11-11T00:00:00Z", equity: 10200 };
  s.equity = 10200;
  const r = riskState(s, defaultRules, s.asOf);
  assert.equal(r.verified, true);
  assert.equal(r.dailyHeadroom, 408);
  assert.equal(r.overallFloor, 9400);
  assert.equal(weekStart("2026-11-15T23:59:00Z"), "2026-11-09T00:00:00.000Z");
});
test("overall floor is original-balance based and floating losses breach equity limits", () => {
  const s = snapshot();
  s.equity = 9399;
  s.realizedPnl = 200;
  s.floatingPnl = -801;
  const r = riskState(s, defaultRules, now);
  assert.equal(r.overallHeadroom, -1);
  assert(r.reasons.some((x) => x.includes("Overall")));
  assert(r.reasons.some((x) => x.includes("Daily")));
  assert.equal(plan({ ...input(), snapshot: s }).size, null);
});
test("internal stops, counts and aggregate exposure reject proposed risk", () => {
  for (const change of [
    (s) => (s.equity = 9940),
    (s) => (s.weeklyBaseline.equity = 10150),
    (s) => (s.tradesToday = 3),
    (s) => {
      s.tradesToday = 2;
      s.lossesToday = 2;
    },
    (s) => (s.openRisk = 25),
  ]) {
    const p = input();
    change(p.snapshot);
    assert.equal(plan(p).status, "NO TRADE");
  }
  const p = input();
  p.snapshot.openRisk = 20;
  assert(plan(p).loss <= 5);
});
test("daily profits cannot increase internal loss budget", () => {
  const s = snapshot();
  s.equity = 11000;
  assert.equal(riskState(s, defaultRules, now).dailyAllowance, 60);
});
test("rule versions are configurable and invalid percentages rejected", () => {
  assert.equal(
    validateRules({ ...defaultRules, version: "v2", startingBalance: 20000 })
      .startingBalance,
    20000,
  );
  assert.throws(() => validateRules({ ...defaultRules, dailyDrawdown: 1 }));
});
test("net consistency, distinct entry days, costs, R and grouped results", () => {
  const trades = [
    trade("a", 100),
    trade("b", 50, "2026-11-10T01:00:00Z", "2026-11-10T02:00:00Z"),
    trade("c", -25, "2026-11-10T14:00:00Z", "2026-11-10T15:00:00Z"),
  ];
  trades[0].fees = 5;
  const s = performance(trades);
  assert.equal(s.tradingDays, 2);
  assert.equal(s.net, 120);
  assert.equal(s.largestDay, 95);
  assert.equal(s.consistency, 95 / 120);
  assert.equal(s.profitFactor, 145 / 25);
  assert.equal(s.maxDrawdown, 25);
  assert(Math.abs(s.averageR - 1.6) < 1e-12);
  assert(Math.abs(s.expectancyR - 1.6) < 1e-12);
  assert.equal(s.byInstrument.NAS100.count, 3);
  assert.equal(Object.keys(s.bySession).length, 2);
  assert.equal(performance([]).winRate, null);
  assert.equal(performance([trade("x", -5)]).consistency, null);
});
test("5-day count is unique UTC entry days, overnight exits do not add days", () => {
  const trades = Array.from({ length: 5 }, (_, i) =>
    trade(
      `t${i}`,
      50,
      `2026-11-${String(i + 1).padStart(2, "0")}T23:00:00Z`,
      `2026-11-${String(i + 2).padStart(2, "0")}T01:00:00Z`,
    ),
  );
  assert.equal(performance(trades).tradingDays, 5);
  assert.equal(performance(trades).consistency, 0.2);
});
test("journal persists in explicit Pivex namespace with challenge isolation and validation", () => {
  const data = new Map(),
    store = {
      getItem: (k) => data.get(k) ?? null,
      setItem: (k, v) => data.set(k, v),
    },
    ledger = {
      schema: 1,
      rules: [defaultRules],
      snapshot: null,
      trades: [trade()],
      specs: [],
    };
  saveLedger(store, "a", ledger);
  assert.deepEqual(loadLedger(store, "a"), ledger);
  assert.equal(loadLedger(store, "b"), null);
  assert.match(storageKey("a"), /^alphaos:pivex:local:v1:/);
  assert.throws(() =>
    saveLedger(store, "a", { ...ledger, trades: [trade(), trade()] }),
  );
  assert.throws(() => loadLedger(store, "../options"));
  assert.throws(() => validateTrade({ ...trade(), initialRisk: 0 }));
  assert.throws(() => validateTrade({ ...trade(), stop: 110 }));
  data.set(storageKey("bad"), "invalid JSON");
  assert.throws(() => loadLedger(store, "bad"));
  assert.equal(data.size, 2);
});
test("imported account observations cannot understate known journal activity", () => {
  const ledger = {
    schema: 1,
    rules: [defaultRules],
    snapshot: snapshot(),
    trades: [
      trade("today", -25, "2026-11-10T12:00:00Z", "2026-11-10T13:00:00Z"),
    ],
    specs: [],
  };
  assert.throws(() => validateLedger(ledger), /understates/);
  ledger.snapshot.tradesToday = 1;
  ledger.snapshot.lossesToday = 1;
  assert.equal(validateLedger(ledger), ledger);
  ledger.snapshot.asOf = "2026-11-10T12:30:00Z";
  assert.throws(() => validateLedger(ledger), /predates/);
  const p = input();
  p.snapshot.lossesToday = 2;
  p.snapshot.tradesToday = 0;
  assert.match(plan(p).reason, /Two losing/);
});
test("Pivex uses existing auth gate; no anonymous access or cross-origin cookie authorization", async () => {
  const env = { ...authBindings },
    options = {
      externalLoginRateLimiter: {
        limit: async () => ({ allowed: true, retryAfterSeconds: 0 }),
      },
    },
    origin = "https://website.test";
  let reached = false;
  const next = async () => {
    reached = true;
    return new Response("private Pivex");
  };
  const response = await protectWebsite(
    new Request(origin + "/pivex"),
    env,
    next,
    options,
  );
  assert.equal(response.status, 303);
  assert.equal(reached, false);
  const cookie = `${SESSION_COOKIE}=${await issueSession(env, origin)}`;
  const authorized = await protectWebsite(
    new Request(origin + "/pivex", { headers: { cookie } }),
    env,
    next,
    options,
  );
  assert.equal(authorized.status, 200);
  assert.equal(reached, true);
  assert.match(authorized.headers.get("cache-control"), /no-store/);
  reached = false;
  await protectWebsite(
    new Request("https://other.test/pivex", { headers: { cookie } }),
    env,
    next,
    options,
  );
  assert.equal(reached, false);
});
test("isolated layers have no network/broker execution capability or options-engine imports", () => {
  for (const name of readdirSync("src/lib/pivex").filter((n) =>
    n.endsWith(".ts"),
  )) {
    const source = readFileSync(`src/lib/pivex/${name}`, "utf8");
    assert.doesNotMatch(
      source,
      /\bfetch\s*\(|\bWebSocket\b|robinhood|structure-bridge|strategy-opportunities|placeOrder|submitOrder/,
    );
  }
  const dashboard = readFileSync(
    "src/components/pivex/PivexDashboard.tsx",
    "utf8",
  );
  assert.doesNotMatch(dashboard, /\bfetch\s*\(|\/api\//);
});
