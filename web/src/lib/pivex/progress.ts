import { finite, timestamp } from "./evidence.ts";
import type { Rules } from "./challenge.ts";

export type QuickReport = {
  schema: 1;
  id: string;
  kind: "user_reported";
  source: string;
  observedAt: string;
  valueType: "equity" | "balance";
  value: number;
  realizedToday: number;
  floatingPnl: number | null;
  fees: number | null;
  openRisk: number | null;
};
export function validateQuickReport(value: unknown, now?: string): QuickReport {
  const q = value as QuickReport;
  if (
    !q ||
    q.schema !== 1 ||
    typeof q.id !== "string" ||
    !/^[\w-]{1,100}$/.test(q.id) ||
    q.kind !== "user_reported" ||
    typeof q.source !== "string" ||
    !q.source.trim() ||
    q.source.length > 500 ||
    !timestamp(q.observedAt) ||
    !["equity", "balance"].includes(q.valueType) ||
    ![q.value, q.realizedToday].every(finite) ||
    !(q.floatingPnl === null || finite(q.floatingPnl)) ||
    (q.valueType === "balance" &&
      q.floatingPnl !== null &&
      !finite(q.value + q.floatingPnl)) ||
    ![q.fees, q.openRisk].every((v) => v === null || (finite(v) && v >= 0)) ||
    (now !== undefined &&
      (!timestamp(now) || Date.parse(q.observedAt) > Date.parse(now)))
  )
    throw Error(
      "Quick update requires a reported value, daily P&L and valid UTC observation; optional costs/risk must be nonnegative",
    );
  return q;
}
/** Indicative only. Neither reported balance nor P&L becomes a verified snapshot. */
export function indicativeProgress(report: QuickReport | null, rules: Rules) {
  if (!report) return null;
  const q = validateQuickReport(report);
  const equity =
    q.valueType === "equity"
      ? q.value
      : q.floatingPnl === null
        ? null
        : q.value + q.floatingPnl;
  const basis = equity ?? q.value,
    target = rules.startingBalance * (1 + rules.profitTarget);
  return {
    equity,
    balance: q.valueType === "balance" ? q.value : null,
    remaining: Math.max(0, target - basis),
    progress: Math.max(
      0,
      Math.min(
        1,
        (basis - rules.startingBalance) /
          (rules.startingBalance * rules.profitTarget),
      ),
    ),
    dailyResult: q.realizedToday,
    observedAt: q.observedAt,
    basis:
      equity === null ? "reported balance" : "user-reported equity estimate",
    compliance: "UNVERIFIED" as const,
    riskAllowance: null,
  };
}
