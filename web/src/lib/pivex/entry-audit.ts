import { finite, positive } from "./evidence.ts";
import type { Candle } from "./evidence.ts";
import type { ContractSpec } from "./planner.ts";
import type { Setup } from "./strategy.ts";

// Order is also the reporting priority. Count each applicable reason once per setup.
export const rejectionPriority = [
  "Missing contiguous next candle",
  "Invalid or nonfinite economics",
  "Invalid stop geometry",
  "Invalid target geometry",
  "Insufficient net reward/risk",
  "Planned risk above $25",
  "Planned risk above configured budget or available equity",
] as const;

type RejectionReason = (typeof rejectionPriority)[number];
type CostSpec = Pick<
  ContractSpec,
  | "tickSize"
  | "tickValue"
  | "quoteToAccount"
  | "spreadTicks"
  | "slippageTicks"
  | "commissionPerLot"
  | "fixedFees"
>;

export function auditEntry(
  setup: Setup,
  next: Candle | null,
  spec: CostSpec,
  quantity: number,
  budget: number,
  equity: number,
  observedSpreadTicks?: number,
) {
  const { direction, stop, target } = setup;
  const entry = next?.open;
  const spreadTicks = Math.max(spec.spreadTicks, observedSpreadTicks ?? 0);
  const spread = quantity * spreadTicks * spec.tickValue * spec.quoteToAccount;
  const slippage =
    quantity * spec.slippageTicks * spec.tickValue * spec.quoteToAccount;
  const fees = quantity * spec.commissionPerLot + spec.fixedFees;
  // Preserve the order of operations used by the historical entry model.
  const total =
    quantity *
      ((spreadTicks + spec.slippageTicks) *
        spec.tickValue *
        spec.quoteToAccount +
        spec.commissionPerLot) +
    spec.fixedFees;

  const reasons = new Set<RejectionReason>();
  let grossRisk: number | null = null,
    grossReward: number | null = null;
  let grossRewardRisk: number | null = null,
    netRewardRisk: number | null = null;
  let plannedRisk: number | null = null;
  let feasibleQuantity: { minimum: number; maximum: number } | null = null;
  const riskLimit = Math.min(budget, equity);
  if (!next) reasons.add("Missing contiguous next candle");
  else if (
    !finite(entry) ||
    !finite(stop) ||
    !finite(target) ||
    (direction !== "long" && direction !== "short")
  )
    reasons.add("Invalid or nonfinite economics");
  else {
    const sign = direction === "long" ? 1 : -1;
    const stopValid = sign * (entry - stop) > 0;
    const targetValid = sign * (target - entry) > 0;
    if (!stopValid) reasons.add("Invalid stop geometry");
    if (!targetValid) reasons.add("Invalid target geometry");
    const unitRisk =
      (Math.abs(entry - stop) / spec.tickSize) *
      spec.tickValue *
      spec.quoteToAccount;
    const unitReward =
      ((sign * (target - entry)) / spec.tickSize) *
      spec.tickValue *
      spec.quoteToAccount;
    const loss = unitRisk * quantity + total;
    const profit = unitReward * quantity - total;
    const net = profit / loss;
    const validEconomics =
      positive(loss) && finite(profit) && finite(net) && finite(total);
    if (!validEconomics) reasons.add("Invalid or nonfinite economics");
    if (stopValid && finite(loss)) {
      plannedRisk = loss;
      if (loss > 25) reasons.add("Planned risk above $25");
      if (riskLimit < 25 && loss > riskLimit)
        reasons.add("Planned risk above configured budget or available equity");
    }
    if (stopValid && targetValid) {
      grossRisk = numberOrNull(unitRisk * quantity);
      grossReward = numberOrNull(unitReward * quantity);
      grossRewardRisk = numberOrNull(unitReward / unitRisk);
      netRewardRisk = numberOrNull(net);
      if (validEconomics && net < 2)
        reasons.add("Insufficient net reward/risk");

      const perUnitCost =
        (spreadTicks + spec.slippageTicks) *
          spec.tickValue *
          spec.quoteToAccount +
        spec.commissionPerLot;
      const surplus = unitReward - 2 * unitRisk - 3 * perUnitCost;
      const maximum = (riskLimit - spec.fixedFees) / (unitRisk + perUnitCost);
      const minimum = spec.fixedFees === 0 ? 0 : (3 * spec.fixedFees) / surplus;
      if (
        validEconomics &&
        (surplus > 0 || (surplus === 0 && spec.fixedFees === 0)) &&
        finite(minimum) &&
        positive(maximum) &&
        minimum <= maximum
      )
        feasibleQuantity = { minimum, maximum };
    }
  }
  const rejectionReasons = rejectionPriority.filter((reason) =>
    reasons.has(reason),
  );
  return {
    confirmationTime: setup.confirmationTime ?? null,
    direction: direction ?? null,
    confirmationPrice: numberOrNull(setup.entryReference),
    nextOpenTime: next?.openTime ?? null,
    nextOpen: numberOrNull(entry),
    stop: numberOrNull(stop),
    target: numberOrNull(target),
    structuralTarget: numberOrNull(setup.evidence?.target.price),
    quantity,
    grossRisk,
    grossReward,
    grossRewardRisk,
    netRewardRisk,
    plannedRisk,
    riskLimit,
    costs: {
      spread: numberOrNull(spread),
      slippage: numberOrNull(slippage),
      fees: numberOrNull(fees),
      total: numberOrNull(total),
      basis: next
        ? "modeled entry costs"
        : "configured spread floor; entry unavailable",
    },
    feasibleQuantity,
    rejectionReasons,
    primaryRejectionReason: rejectionReasons[0] ?? null,
  };
}

function numberOrNull(value: unknown): number | null {
  return finite(value) ? value : null;
}
