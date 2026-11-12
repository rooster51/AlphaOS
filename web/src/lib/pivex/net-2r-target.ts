import { positive } from "./evidence.ts";

/** Research target selection. Entry eligibility remains with the replay audit. */
export function netTwoRTarget(
  entry: number,
  direction: number,
  tickSize: number,
  dollarsPerTick: number,
  plannedRisk: number,
  costs: number,
  rewardPerUnitAt: (price: number) => number,
  quantity: number,
): number | null {
  const distance = ((2 * plannedRisk + costs) / dollarsPerTick) * tickSize;
  const grid = (direction * (entry + direction * distance)) / tickSize;
  if (
    !positive(dollarsPerTick) ||
    !positive(distance) ||
    !Number.isSafeInteger(Math.ceil(grid))
  )
    return null;

  // Use the same arithmetic as the entry gate at the adjacent price ticks.
  let ticks = Math.floor(grid);
  const price = () => direction * ticks * tickSize;
  if ((rewardPerUnitAt(price()) * quantity - costs) / plannedRisk < 2) ticks++;
  if ((rewardPerUnitAt(price()) * quantity - costs) / plannedRisk < 2) ticks++;
  return price();
}
