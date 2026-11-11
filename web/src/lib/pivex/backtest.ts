import { analyze } from "./strategy.ts";
import type { Setup } from "./strategy.ts";
import { positive, finite, timestamp } from "./evidence.ts";
import {
  HistoricalExportAdapter,
  validateDataset,
  gapKind,
} from "./history.ts";
import type { HistoricalDataset } from "./history.ts";
import { validateSpec } from "./planner.ts";
import type { ContractSpec } from "./planner.ts";
import { session } from "./journal.ts";

export type BacktestConfig = {
  from: string;
  splitAt: string;
  to: string;
  startingEquity: number;
  lots: number;
  riskBudget: number;
  spec: ContractSpec;
};
export type SimulatedTrade = {
  confirmationTime: string;
  entryTime: string;
  exitTime: string | null;
  direction: "long" | "short";
  instrument: string;
  entry: number;
  exit: number | null;
  stop: number;
  target: number;
  lots: number;
  costs: number;
  initialRisk: number;
  netPnl: number | null;
  r: number | null;
  outcome:
    | "target"
    | "stop"
    | "ambiguous_stop_first"
    | "gap_stop"
    | "unresolved";
  condition: "bullish trend" | "bearish trend";
  note: string;
};
export function backtestMetrics(
  trades: SimulatedTrade[],
  startingEquity: number,
) {
  const completed = trades.filter((t) => t.netPnl !== null),
    values = completed.map((t) => t.netPnl!),
    wins = values.filter((v) => v > 0),
    losses = values.filter((v) => v < 0);
  const sum = (a: number[]) => a.reduce((s, v) => s + v, 0),
    average = (a: number[]) => (a.length ? sum(a) / a.length : null);
  let equity = startingEquity,
    peak = equity,
    maxDrawdown = 0,
    streak = 0,
    consecutiveLosses = 0;
  const curve: { at: string; equity: number }[] = [];
  for (const t of completed) {
    equity += t.netPnl!;
    peak = Math.max(peak, equity);
    maxDrawdown = Math.max(maxDrawdown, peak - equity);
    streak = t.netPnl! < 0 ? streak + 1 : 0;
    consecutiveLosses = Math.max(consecutiveLosses, streak);
    curve.push({ at: t.exitTime!, equity });
  }
  return {
    completed: completed.length,
    winRate: completed.length ? wins.length / completed.length : null,
    averageWinner: average(wins),
    averageLoser: average(losses),
    profitFactor: losses.length ? sum(wins) / Math.abs(sum(losses)) : null,
    averageR: average(completed.map((t) => t.r!)),
    expectancyR: average(completed.map((t) => t.r!)),
    maxDrawdown: completed.length ? maxDrawdown : null,
    consecutiveLosses: completed.length ? consecutiveLosses : null,
    netPnl: sum(values),
    curve,
  };
}
export type ReplayResult = ReturnType<typeof replayWindow>;
export function replayWindow(
  d: Pick<HistoricalDataset, "instrument" | "candles" | "closedPeriods">,
  c: Pick<BacktestConfig, "startingEquity" | "lots" | "riskBudget"> & {
    spec: Pick<
      ContractSpec,
      | "tickSize"
      | "tickValue"
      | "quoteToAccount"
      | "spreadTicks"
      | "slippageTicks"
      | "commissionPerLot"
      | "fixedFees"
    >;
  },
  from: string,
  to: string,
  label: string,
  evaluate: (bar: HistoricalDataset["candles"]["m5"][number]) => Setup,
  proxy?: {
    entrySpreadTicks: (openTime: string) => number;
    classifyGap?: (from: string, to: string) => ReturnType<typeof gapKind>;
  },
) {
  const bars = d.candles.m5.filter(
    (b) =>
      Date.parse(b.openTime) >= Date.parse(from) &&
      Date.parse(b.closeTime) <= Date.parse(to),
  );
  const classifyGap =
    proxy?.classifyGap ?? ((from, to) => gapKind(d, from, to));
  if (!proxy && bars.length > 2000)
    throw Error(
      "Replay is limited to 2,000 entry bars per partition; import a smaller research window",
    );
  const trades: SimulatedTrade[] = [],
    diagnostics: Record<string, number> = {};
  const count = (message: string) => {
    diagnostics[message] = (diagnostics[message] ?? 0) + 1;
  };
  let coverageIncomplete = false;
  if (!bars.length) {
    count("No entry bars in requested window");
    coverageIncomplete = true;
  } else {
    if (Date.parse(bars[0].openTime) > Date.parse(from)) {
      const kind = classifyGap(from, bars[0].openTime);
      count(`Leading ${kind}`);
      if (!proxy || kind === "missing bars") coverageIncomplete = true;
    }
    if (Date.parse(bars.at(-1)!.closeTime) < Date.parse(to)) {
      const kind = classifyGap(bars.at(-1)!.closeTime, to);
      count(`Trailing ${kind}`);
      if (!proxy || kind === "missing bars") coverageIncomplete = true;
    }
  }
  let pending: Setup | null = null,
    open: SimulatedTrade | null = null,
    setups = 0,
    equity = c.startingEquity,
    previousClose: string | null = null,
    terminated = false,
    evaluated = 0;
  const s = c.spec,
    sign = (t: SimulatedTrade) => (t.direction === "long" ? 1 : -1);
  const roundTripCosts = (spreadTicks: number) =>
    c.lots *
      ((spreadTicks + s.slippageTicks) * s.tickValue * s.quoteToAccount +
        s.commissionPerLot) +
    s.fixedFees;
  const pnl = (t: SimulatedTrade, price: number) =>
    ((sign(t) * (price - t.entry)) / s.tickSize) *
      s.tickValue *
      s.quoteToAccount *
      c.lots -
    t.costs;
  for (const bar of bars) {
    if (
      previousClose &&
      Date.parse(bar.openTime) !== Date.parse(previousClose)
    ) {
      const kind = classifyGap(previousClose, bar.openTime);
      count(kind);
      const knownProxyClosure = proxy && kind === "declared non-trading period";
      if (!knownProxyClosure) coverageIncomplete = true;
      if (open && !knownProxyClosure) {
        open.outcome = "unresolved";
        open.note = `Replay stopped: ${kind} while a position was open. No invented exit or subsequent portfolio results.`;
        trades.push(open);
        open = null;
        terminated = true;
        break;
      }
      if (pending) count("Confirmation has no contiguous next bar; no entry");
      pending = null;
    }
    if (pending && !open) {
      if (Date.parse(bar.openTime) !== Date.parse(pending.confirmationTime!))
        count("Missing exact next-bar open; no fill");
      else {
        const direction = pending.direction!,
          entry = bar.open,
          stop = pending.stop!,
          target = pending.target!,
          costs = roundTripCosts(
            Math.max(s.spreadTicks, proxy?.entrySpreadTicks(bar.openTime) ?? 0),
          ),
          loss =
            (Math.abs(entry - stop) / s.tickSize) *
              s.tickValue *
              s.quoteToAccount *
              c.lots +
            costs,
          profit =
            ((direction === "long" ? target - entry : entry - target) /
              s.tickSize) *
              s.tickValue *
              s.quoteToAccount *
              c.lots -
            costs;
        if (
          (direction === "long"
            ? entry <= stop || entry >= target
            : entry >= stop || entry <= target) ||
          !positive(loss) ||
          !finite(profit) ||
          profit / loss < 2 ||
          loss > Math.min(c.riskBudget, equity)
        )
          count("Next-open geometry, costs or risk budget rejects entry");
        else
          open = {
            confirmationTime: pending.confirmationTime!,
            entryTime: bar.openTime,
            exitTime: null,
            direction,
            instrument: d.instrument,
            entry,
            exit: null,
            stop,
            target,
            lots: c.lots,
            costs,
            initialRisk: loss,
            netPnl: null,
            r: null,
            outcome: "unresolved",
            condition: direction === "long" ? "bullish trend" : "bearish trend",
            note: "Hypothetical observed next-bar open; no liquidity guarantee. Exit timestamp is bar close, not an exact intrabar fill time.",
          };
      }
      pending = null;
    }
    if (open) {
      const long = open.direction === "long",
        stopGap = long ? bar.open < open.stop : bar.open > open.stop,
        stopHit = long ? bar.low <= open.stop : bar.high >= open.stop,
        targetHit = long ? bar.high >= open.target : bar.low <= open.target;
      let exit: number | null = null;
      if (stopGap) {
        exit = bar.open;
        open.outcome = "gap_stop";
        open.note +=
          " Stop gapped: adverse observed open used plus declared costs.";
      } else if (stopHit) {
        exit = open.stop;
        open.outcome = targetHit ? "ambiguous_stop_first" : "stop";
        if (targetHit)
          open.note +=
            " Stop and target touched in one bar: uncertain sequence, conservatively charged stop loss.";
      } else if (targetHit) {
        exit = open.target;
        open.outcome = "target";
        open.note +=
          " Target limit modeled at target, without favorable gap improvement.";
      }
      if (exit !== null) {
        open.exit = exit;
        open.exitTime = bar.closeTime;
        open.netPnl = pnl(open, exit);
        open.r = open.netPnl / open.initialRisk;
        equity += open.netPnl;
        trades.push(open);
        open = null;
      }
    }
    // Evidence is cut at this completed bar; analyze() independently freezes 1H/15M at its open.
    if (!open) {
      try {
        evaluated++;
        const result = evaluate(bar);
        if (result.status === "CONFIRMED") {
          setups++;
          pending = result;
        } else count(`${result.status}: ${result.reason}`);
      } catch (e) {
        count(
          e instanceof Error ? e.message : "Insufficient historical evidence",
        );
      }
    }
    previousClose = bar.closeTime;
  }
  if (open) {
    open.note +=
      " Window ended before a resolvable exit. No forced liquidation.";
    trades.push(open);
  }
  if (pending) count("Window ended before next candle; no fill");
  const metrics = backtestMetrics(trades, c.startingEquity);
  const group = (key: (t: SimulatedTrade) => string) =>
    Object.fromEntries(
      [...new Set(trades.map(key))].sort().map((k) => [
        k,
        backtestMetrics(
          trades.filter((t) => key(t) === k),
          c.startingEquity,
        ),
      ]),
    );
  return {
    label,
    from,
    to,
    bars: bars.length,
    evaluated,
    setups,
    trades,
    metrics,
    diagnostics,
    terminated,
    incomplete:
      coverageIncomplete ||
      terminated ||
      trades.some((t) => t.outcome === "unresolved") ||
      Boolean(pending),
    curve: [{ at: from, equity: c.startingEquity }, ...metrics.curve],
    byInstrument: group((t) => t.instrument),
    bySession: group((t) => session(t.entryTime)),
    byDirection: group((t) => t.direction),
    byCondition: group((t) => t.condition),
  };
}
export function runBacktest(value: unknown, config: BacktestConfig) {
  const d = validateDataset(value),
    c = config,
    s = validateSpec(c.spec);
  if (
    ![c.from, c.splitAt, c.to].every(timestamp) ||
    Date.parse(c.from) >= Date.parse(c.splitAt) ||
    Date.parse(c.splitAt) >= Date.parse(c.to) ||
    ![c.startingEquity, c.lots, c.riskBudget].every(positive) ||
    c.riskBudget > 25 ||
    s.instrument !== d.instrument ||
    s.brokerSymbol !== d.mapping.brokerSymbol ||
    s.tickSize !== d.tickSize ||
    c.lots < s.minLot ||
    c.lots > s.maxLot ||
    Math.abs(
      (c.lots - s.minLot) / s.lotStep -
        Math.round((c.lots - s.minLot) / s.lotStep),
    ) > 1e-6
  )
    throw Error(
      "Backtest needs ordered nonoverlapping windows, matching contract mapping, valid lots and risk budget up to $25",
    );
  if (
    d.candles.m5.some(
      (b) =>
        Date.parse(b.openTime) < Date.parse(c.splitAt) &&
        Date.parse(b.closeTime) > Date.parse(c.splitAt),
    )
  )
    throw Error("Split must lie on an entry-bar boundary");
  const adapter = new HistoricalExportAdapter(d);
  const evaluate = (bar: HistoricalDataset["candles"]["m5"][number]) =>
    analyze(adapter.evidenceAt(d.instrument, bar.closeTime));
  return {
    model: "pivex-replay-v1",
    kind: "hypothetical_backtest" as const,
    source: d.source,
    dataMode: d.mode,
    config: structuredClone(c),
    executionModel:
      "Single position, fixed declared lots; completed-bar signals; contiguous next-bar observed open; round-trip spread/slippage/commission/fees charged once; net >=2R and risk <=$25 at entry; stop first on ambiguous bars; missing bars during a position terminate the partition; no forced window-end exits. Equity curve is resolved-trade net equity, not continuous mark-to-market compliance.",
    development: replayWindow(
      d,
      c,
      c.from,
      c.splitAt,
      "In-sample development",
      evaluate,
    ),
    validation: replayWindow(
      d,
      c,
      c.splitAt,
      c.to,
      "Out-of-sample validation",
      evaluate,
    ),
  };
}
