import { finite, positive, timestamp, instruments } from "./evidence.ts";
import { day, validateRules, validateSnapshot } from "./challenge.ts";
import type { Rules, Snapshot } from "./challenge.ts";
import { validateSpec } from "./planner.ts";
import type { ContractSpec } from "./planner.ts";
import { validateQuickReport } from "./progress.ts";
import type { QuickReport } from "./progress.ts";
export type Trade = {
  id: string;
  ruleVersion: string;
  instrument: string;
  direction: "long" | "short";
  entryTime: string;
  exitTime: string;
  entry: number;
  exit: number;
  stop: number;
  target: number;
  size: number;
  fees: number;
  otherCosts: number;
  realizedPnl: number;
  initialRisk: number;
  setup: string;
  adherence: "adhered" | "breach" | "unknown";
  exitReason: string;
  source: string;
};
/** realizedPnl is gross platform-reported P&L; subtract separately entered fees/costs once. */
export const net = (t: Trade) => t.realizedPnl - t.fees - t.otherCosts;
export function validateTrade(value: unknown): Trade {
  const t = value as Trade;
  if (
    !t ||
    typeof t.id !== "string" ||
    !/^[\w-]{1,100}$/.test(t.id) ||
    !instruments.some((i) => i.id === t.instrument) ||
    !["long", "short"].includes(t.direction) ||
    !timestamp(t.entryTime) ||
    !timestamp(t.exitTime) ||
    Date.parse(t.exitTime) < Date.parse(t.entryTime) ||
    ![t.entry, t.exit, t.stop, t.target, t.size, t.initialRisk].every(
      positive,
    ) ||
    !finite(t.realizedPnl) ||
    ![t.fees, t.otherCosts].every((v) => finite(v) && v >= 0) ||
    ![t.ruleVersion, t.setup, t.exitReason, t.source].every(
      (v) => typeof v === "string" && v.trim().length > 0 && v.length <= 500,
    ) ||
    !["adhered", "breach", "unknown"].includes(t.adherence) ||
    (t.direction === "long"
      ? t.stop >= t.entry || t.target <= t.entry
      : t.stop <= t.entry || t.target >= t.entry)
  )
    throw Error(
      "Invalid journal trade: use UTC times, positive risk and explicit gross P&L/costs",
    );
  return t;
}
function aggregate(trades: Trade[]) {
  const values = trades.map(net),
    wins = values.filter((v) => v > 0),
    losses = values.filter((v) => v < 0),
    sum = (a: number[]) => a.reduce((s, v) => s + v, 0);
  const rs = trades.map((t) => net(t) / t.initialRisk);
  return {
    count: trades.length,
    net: sum(values),
    winRate: trades.length ? wins.length / trades.length : null,
    averageWin: wins.length ? sum(wins) / wins.length : null,
    averageLoss: losses.length ? sum(losses) / losses.length : null,
    profitFactor: losses.length ? sum(wins) / Math.abs(sum(losses)) : null,
    averageR: rs.length ? sum(rs) / rs.length : null,
    expectancyR: rs.length ? sum(rs) / rs.length : null,
  };
}
export function session(at: string) {
  const h = new Date(at).getUTCHours();
  return h < 7
    ? "Asia (00–07 UTC)"
    : h < 13
      ? "Europe (07–13 UTC)"
      : h < 21
        ? "US (13–21 UTC)"
        : "Late (21–24 UTC)";
}
export function performance(trades: Trade[]) {
  trades.forEach(validateTrade);
  const daily: Record<string, number> = {};
  for (const t of trades)
    daily[day(t.exitTime)] = (daily[day(t.exitTime)] ?? 0) + net(t);
  let cumulative = 0,
    peak = 0,
    maxDrawdown = 0;
  for (const t of [...trades].sort(
    (a, b) =>
      Date.parse(a.exitTime) - Date.parse(b.exitTime) ||
      a.id.localeCompare(b.id),
  )) {
    cumulative += net(t);
    peak = Math.max(peak, cumulative);
    maxDrawdown = Math.max(maxDrawdown, peak - cumulative);
  }
  const total = aggregate(trades),
    largestDay = Math.max(0, ...Object.values(daily));
  const group = (key: (t: Trade) => string) =>
    Object.fromEntries(
      [...new Set(trades.map(key))]
        .sort()
        .map((k) => [k, aggregate(trades.filter((t) => key(t) === k))]),
    );
  return {
    ...total,
    tradingDays: new Set(trades.map((t) => day(t.entryTime))).size,
    largestDay: trades.length ? largestDay : null,
    consistency: total.net > 0 ? largestDay / total.net : null,
    maxDrawdown: trades.length ? maxDrawdown : null,
    byInstrument: group((t) => t.instrument),
    bySetup: group((t) => t.setup),
    bySession: group((t) => session(t.entryTime)),
  };
}
export type Ledger = {
  schema: 1;
  rules: Rules[];
  snapshot: Snapshot | null;
  trades: Trade[];
  specs: ContractSpec[];
  quickReports?: QuickReport[];
};
export const storageKey = (profile: string) => {
  if (!/^[a-zA-Z0-9_-]{1,60}$/.test(profile))
    throw Error(
      "Use a challenge label of 1–60 letters, digits, underscores or hyphens",
    );
  return `alphaos:pivex:local:v1:${profile}`;
};
export function validateLedger(value: unknown): Ledger {
  const l = value as Ledger;
  if (
    !l ||
    l.schema !== 1 ||
    !Array.isArray(l.rules) ||
    !l.rules.length ||
    l.rules.length > 100 ||
    !Array.isArray(l.trades) ||
    l.trades.length > 10000 ||
    !Array.isArray(l.specs) ||
    l.specs.length > 100
  )
    throw Error("Unsupported Pivex ledger");
  l.rules.forEach(validateRules);
  l.trades.forEach(validateTrade);
  l.specs.forEach(validateSpec);
  if (l.quickReports !== undefined) {
    if (!Array.isArray(l.quickReports) || l.quickReports.length > 10000)
      throw Error("Invalid quick-report history");
    l.quickReports.forEach((q) => validateQuickReport(q));
    if (new Set(l.quickReports.map((q) => q.id)).size !== l.quickReports.length)
      throw Error("Duplicate quick update");
  }
  if (l.trades.some((t) => !l.rules.some((r) => r.version === t.ruleVersion)))
    throw Error("Journal references an unknown rule version");
  if (
    new Set(l.trades.map((t) => t.id)).size !== l.trades.length ||
    new Set(l.rules.map((r) => r.version)).size !== l.rules.length
  )
    throw Error("Duplicate trade or rule version");
  if (l.snapshot !== null) {
    const s = validateSnapshot(l.snapshot);
    if (
      l.quickReports?.some((q) => Date.parse(q.observedAt) > Date.parse(s.asOf))
    )
      throw Error("Advanced verification predates a newer quick report");
    const opened = l.trades.filter(
      (t) => day(t.entryTime) === day(s.asOf),
    ).length;
    const losses = l.trades.filter(
      (t) => day(t.exitTime) === day(s.asOf) && net(t) < 0,
    ).length;
    if (
      s.tradesToday < opened ||
      s.lossesToday < losses ||
      l.trades.some((t) => Date.parse(t.exitTime) > Date.parse(s.asOf))
    )
      throw Error(
        "Account observation predates journal activity or understates known daily counts",
      );
  }
  return l;
}
/** Idempotent local migration; incoming evidence never authorizes an account snapshot. */
export function mergeLocalBackup(current: Ledger, incoming: Ledger): Ledger {
  validateLedger(current);
  validateLedger(incoming);
  const canonical = (value: unknown): string =>
    JSON.stringify(value, (_key, v) =>
      v && typeof v === "object" && !Array.isArray(v)
        ? Object.fromEntries(
            Object.entries(v).sort(([a], [b]) => a.localeCompare(b)),
          )
        : v,
    );
  const merge = <T>(a: T[], b: T[], key: (v: T) => string): T[] => {
    const map = new Map(a.map((v) => [key(v), v]));
    for (const item of b) {
      const old = map.get(key(item));
      if (old && canonical(old) !== canonical(item))
        throw Error(`Conflicting backup record: ${key(item)}`);
      map.set(key(item), item);
    }
    return [...map.values()];
  };
  return validateLedger({
    ...current,
    snapshot: null,
    rules: merge(incoming.rules, current.rules, (r) => r.version),
    trades: merge(current.trades, incoming.trades, (t) => t.id),
    quickReports: merge(
      current.quickReports ?? [],
      incoming.quickReports ?? [],
      (q) => q.id,
    ),
    specs: current.specs,
  });
}
export interface LocalStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}
export function loadLedger(store: LocalStore, profile: string): Ledger | null {
  const raw = store.getItem(storageKey(profile));
  if (raw === null) return null;
  if (raw.length > 5000000) throw Error("Stored ledger exceeds import limit");
  return validateLedger(JSON.parse(raw));
}
export function saveLedger(store: LocalStore, profile: string, ledger: Ledger) {
  const raw = JSON.stringify(validateLedger(ledger));
  if (raw.length > 5000000)
    throw Error("Ledger exceeds 5 MB; export and open another local challenge");
  store.setItem(storageKey(profile), raw);
}
