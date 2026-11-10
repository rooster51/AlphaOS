import { finite, positive, timestamp, instruments } from "./evidence.ts";
import { policy, riskState } from "./challenge.ts";
import type { Rules, Snapshot } from "./challenge.ts";
export type ContractSpec = {
  instrument: string;
  brokerSymbol: string;
  source: string;
  verifiedAt: string;
  attested: boolean;
  tickSize: number;
  tickValue: number;
  quoteToAccount: number;
  minLot: number;
  maxLot: number;
  lotStep: number;
  spreadTicks: number;
  slippageTicks: number;
  commissionPerLot: number;
  fixedFees: number;
  costsSource: string;
  marketHours: string;
  permitted: boolean;
};
export type PlanInput = {
  entry: number;
  stop: number;
  target: number;
  budget: number;
  spec: ContractSpec | null;
  snapshot: Snapshot | null;
  rules: Rules;
  now: string;
};
export function validateSpec(value: unknown): ContractSpec {
  const s = value as ContractSpec;
  if (
    !s ||
    !instruments.some((i) => i.id === s.instrument) ||
    !s.brokerSymbol?.trim() ||
    !s.source?.trim() ||
    !s.costsSource?.trim() ||
    !s.marketHours?.trim() ||
    s.permitted !== true ||
    s.attested !== true ||
    !timestamp(s.verifiedAt) ||
    ![
      s.tickSize,
      s.tickValue,
      s.quoteToAccount,
      s.minLot,
      s.maxLot,
      s.lotStep,
    ].every(positive) ||
    s.maxLot < s.minLot ||
    ![s.spreadTicks, s.slippageTicks, s.commissionPerLot, s.fixedFees].every(
      (v) => finite(v) && v >= 0,
    )
  )
    throw Error("Missing attested contract specifications or cost evidence");
  return s;
}
export function plan(p: PlanInput) {
  const reject = (reason: string) => ({
    status: "NO TRADE" as const,
    reason,
    size: null,
    loss: null,
    profit: null,
    rr: null,
    direction: null,
    distance: null,
  });
  try {
    const s = validateSpec(p.spec),
      risk = riskState(p.snapshot, p.rules, p.now);
    if (!risk.verified || !p.snapshot)
      return reject("Unable to verify account equity / UTC risk baseline");
    if (
      Date.parse(s.verifiedAt) > Date.parse(p.now) ||
      Date.parse(p.now) - Date.parse(s.verifiedAt) > 86400000
    )
      return reject("Contract/cost evidence older than 24 hours; reconfirm");
    if (
      ![p.entry, p.stop, p.target, p.budget].every(positive) ||
      p.entry === p.stop
    )
      return reject("Invalid prices or risk budget");
    const direction = p.stop < p.entry ? "long" : "short";
    if (direction === "long" ? p.target <= p.entry : p.target >= p.entry)
      return reject("Target is on the wrong side of entry");
    const aligned = (v: number) =>
      Math.abs(v / s.tickSize - Math.round(v / s.tickSize)) < 1e-6;
    if (![p.entry, p.stop, p.target].every(aligned))
      return reject("Prices must respect tick size");
    if (risk.reasons.length) return reject(risk.reasons.join("; "));
    const remaining = Math.min(
      p.budget,
      policy.tradeRisk,
      policy.aggregateRisk - p.snapshot.openRisk,
      risk.dailyAllowance! - p.snapshot.openRisk,
      risk.weeklyAllowance! - p.snapshot.openRisk,
      risk.dailyHeadroom! - p.snapshot.openRisk,
      risk.overallHeadroom! - p.snapshot.openRisk,
    );
    const distance = Math.abs(p.entry - p.stop),
      grossLoss = (distance / s.tickSize) * s.tickValue * s.quoteToAccount;
    // tickValue is per lot in quote currency; commission and fixed fees are round-trip in account USD.
    const costs =
      (s.spreadTicks + s.slippageTicks) * s.tickValue * s.quoteToAccount +
      s.commissionPerLot;
    const lossPerLot = grossLoss + costs;
    if (
      ![remaining, distance, grossLoss, costs, lossPerLot].every(finite) ||
      !positive(lossPerLot)
    )
      return reject("Invalid numeric precision in contract/cost model");
    const steps = Math.floor(
      ((remaining - s.fixedFees) / lossPerLot - s.minLot) / s.lotStep + 1e-10,
    );
    if (steps < 0)
      return reject("Minimum lot exceeds remaining risk allowance");
    const size = Number(
      Math.min(
        s.minLot + steps * s.lotStep,
        s.minLot + Math.floor((s.maxLot - s.minLot) / s.lotStep) * s.lotStep,
      ).toFixed(10),
    );
    const loss = size * lossPerLot + s.fixedFees;
    const profit =
      size *
        ((Math.abs(p.target - p.entry) / s.tickSize) *
          s.tickValue *
          s.quoteToAccount -
          costs) -
      s.fixedFees;
    const rr = profit / loss;
    if (
      ![size, loss, profit, rr].every(positive) ||
      size < s.minLot ||
      size > s.maxLot ||
      Math.abs(
        (size - s.minLot) / s.lotStep -
          Math.round((size - s.minLot) / s.lotStep),
      ) > 1e-6
    )
      return reject("Invalid numeric precision or lot increment in model");
    if (loss > remaining + 1e-8 || rr < 2)
      return reject(
        "Net modeled reward/risk is below 2:1 or risk allowance exceeded",
      );
    return {
      status: "MODELED" as const,
      reason:
        "Sizing check only. Setup, market hours, news and account agreement require independent review. No averaging down or widening stops. Gaps, slippage and platform marks can exceed estimates.",
      size,
      loss,
      profit,
      rr,
      direction,
      distance,
    };
  } catch (err) {
    return reject(
      err instanceof Error ? err.message : "Invalid planner inputs",
    );
  }
}
