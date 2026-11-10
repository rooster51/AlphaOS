import { finite, positive, timestamp } from "./evidence.ts";
export type Rules = {
  version: string;
  source: string;
  reviewedAt: string;
  agreementStatus: "unverified" | "user_attested";
  stage: "challenge" | "funded";
  startingBalance: number;
  profitTarget: number;
  overallDrawdown: number;
  dailyDrawdown: number;
  minDays: number;
  consistency: number;
  deadline: string | null;
};
export const defaultRules: Rules = {
  version: "research-2026-11-10-v1",
  source:
    "User research mandate; public Pivex help and legal terms conflict. Active account agreement required.",
  reviewedAt: "2026-11-10T00:00:00Z",
  agreementStatus: "unverified",
  stage: "challenge",
  startingBalance: 10000,
  profitTarget: 0.1,
  overallDrawdown: 0.06,
  dailyDrawdown: 0.04,
  minDays: 5,
  consistency: 0.5,
  deadline: null,
};
export const policy = {
  tradeRisk: 25,
  aggregateRisk: 25,
  dailyLoss: 60,
  weeklyLoss: 150,
  tradesPerDay: 3,
  losingTradesPerDay: 2,
} as const;
export type Snapshot = {
  asOf: string;
  source: string;
  attested: boolean;
  equity: number;
  realizedPnl: number;
  floatingPnl: number;
  fees: number;
  exposure: number;
  openRisk: number;
  dailyBaseline: { at: string; equity: number };
  weeklyBaseline: { at: string; equity: number };
  tradesToday: number;
  lossesToday: number;
};
export const day = (at: string) => at.slice(0, 10);
export function weekStart(at: string) {
  const d = new Date(at);
  d.setUTCHours(0, 0, 0, 0);
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
  return d.toISOString();
}
export function validateRules(value: unknown): Rules {
  const r = value as Rules;
  if (
    !r ||
    !r.version?.trim() ||
    !r.source?.trim() ||
    !timestamp(r.reviewedAt) ||
    !["unverified", "user_attested"].includes(r.agreementStatus) ||
    !["challenge", "funded"].includes(r.stage) ||
    !positive(r.startingBalance) ||
    ![r.profitTarget, r.overallDrawdown, r.dailyDrawdown, r.consistency].every(
      (v) => positive(v) && v < 1,
    ) ||
    !Number.isSafeInteger(r.minDays) ||
    r.minDays < 1 ||
    !(r.deadline === null || timestamp(r.deadline))
  )
    throw Error("Invalid versioned rule configuration");
  return r;
}
export function validateSnapshot(value: unknown): Snapshot {
  const s = value as Snapshot;
  if (
    !s ||
    !timestamp(s.asOf) ||
    s.attested !== true ||
    typeof s.source !== "string" ||
    !s.source.trim() ||
    !finite(s.equity) ||
    ![s.realizedPnl, s.floatingPnl].every(finite) ||
    ![s.fees, s.exposure, s.openRisk].every((v) => finite(v) && v >= 0) ||
    !s.dailyBaseline ||
    !s.weeklyBaseline ||
    !timestamp(s.dailyBaseline.at) ||
    !timestamp(s.weeklyBaseline.at) ||
    !positive(s.dailyBaseline.equity) ||
    !positive(s.weeklyBaseline.equity) ||
    Date.parse(s.dailyBaseline.at) !== Date.parse(day(s.asOf) + "T00:00:00Z") ||
    Date.parse(s.weeklyBaseline.at) !== Date.parse(weekStart(s.asOf)) ||
    ![s.tradesToday, s.lossesToday].every(
      (v) => Number.isSafeInteger(v) && v >= 0,
    )
  )
    throw Error(
      "Snapshot requires attested equity, exposure, P&L, costs, UTC baselines and trade counts",
    );
  return s;
}
export function riskState(
  snapshot: Snapshot | null,
  rules: Rules,
  now: string,
) {
  const overallFloor = rules.startingBalance * (1 - rules.overallDrawdown);
  const unavailable = {
    verified: false as const,
    overallFloor,
    dailyFloor: null,
    dailyHeadroom: null,
    overallHeadroom: null,
    dailyAllowance: null,
    weeklyAllowance: null,
    remainingTarget: null,
    reasons: ["Unable to verify current account equity and UTC baselines"],
  };
  try {
    validateRules(rules);
    const s = validateSnapshot(snapshot);
    if (
      !timestamp(now) ||
      Date.parse(now) < Date.parse(s.asOf) ||
      Date.parse(now) - Date.parse(s.asOf) > 15 * 60000 ||
      day(now) !== day(s.asOf)
    )
      return unavailable;
    // Equity is explicitly entered from the platform; never inferred from realized P&L.
    const dailyFloor = s.dailyBaseline.equity * (1 - rules.dailyDrawdown);
    const dailyPnl = s.equity - s.dailyBaseline.equity,
      weeklyPnl = s.equity - s.weeklyBaseline.equity;
    const reasons: string[] = [];
    if (s.equity <= overallFloor) reasons.push("Overall equity floor reached");
    if (s.equity <= dailyFloor) reasons.push("Daily equity floor reached");
    if (dailyPnl <= -policy.dailyLoss)
      reasons.push("Personal daily stop reached");
    if (weeklyPnl <= -policy.weeklyLoss)
      reasons.push("Personal weekly stop reached");
    if (s.tradesToday >= policy.tradesPerDay)
      reasons.push("Three-trade daily limit reached");
    if (s.lossesToday >= policy.losingTradesPerDay)
      reasons.push("Two losing trades today");
    if (rules.deadline && Date.parse(now) >= Date.parse(rules.deadline))
      reasons.push("Configured challenge deadline reached");
    return {
      verified: true as const,
      overallFloor,
      dailyFloor,
      dailyHeadroom: s.equity - dailyFloor,
      overallHeadroom: s.equity - overallFloor,
      dailyAllowance: Math.max(0, policy.dailyLoss + Math.min(0, dailyPnl)),
      weeklyAllowance: Math.max(0, policy.weeklyLoss + Math.min(0, weeklyPnl)),
      remainingTarget: Math.max(
        0,
        rules.startingBalance * rules.profitTarget - (s.realizedPnl - s.fees),
      ),
      reasons,
    };
  } catch {
    return unavailable;
  }
}
