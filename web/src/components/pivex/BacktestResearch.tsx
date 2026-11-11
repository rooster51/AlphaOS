"use client";
import { useState } from "react";
import { runBacktest } from "@/lib/pivex/backtest";
import type { ReplayResult } from "@/lib/pivex/backtest";
import { backtestFixture } from "@/lib/pivex/backtest-fixture";
const input =
  "w-full rounded border border-terminal-700 bg-terminal-950 px-3 py-2 text-terminal-100";
const button =
  "rounded border border-terminal-600 px-3 py-2 hover:border-profit";
const money = (n: number | null) =>
  n == null
    ? "Unavailable"
    : new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
      }).format(n);
function EquityCurve({ result }: { result: ReplayResult }) {
  const values = result.curve.map((p) => p.equity),
    low = Math.min(...values) - 1,
    high = Math.max(...values) + 1;
  const first = Date.parse(result.from),
    last = Date.parse(result.to),
    points = result.curve
      .map(
        (p) =>
          `${20 + (560 * (Date.parse(p.at) - first)) / (last - first)},${145 - (120 * (p.equity - low)) / (high - low)}`,
      )
      .join(" ");
  return (
    <figure className="border border-terminal-800 rounded p-3">
      <figcaption>
        {result.label}: resolved simulated-trade equity (USD)
      </figcaption>
      <svg
        className="w-full h-44"
        viewBox="0 0 600 170"
        role="img"
        aria-label={`${result.label} hypothetical equity curve`}
      >
        <line x1="20" y1="145" x2="580" y2="145" stroke="#334155" />
        <polyline
          points={points}
          fill="none"
          stroke="#34d399"
          strokeWidth="2"
        />
        {result.curve.map((p, i) => (
          <circle
            key={i}
            cx={20 + (560 * (Date.parse(p.at) - first)) / (last - first)}
            cy={145 - (120 * (p.equity - low)) / (high - low)}
            r="3"
            fill="#34d399"
          >
            <title>
              {p.at}: {money(p.equity)}
            </title>
          </circle>
        ))}
      </svg>
      <p className="text-terminal-400">
        {money(values[0])} → {money(values.at(-1)!)} · excludes unresolved
        positions and continuous floating equity.
      </p>
    </figure>
  );
}
function Results({ result }: { result: ReplayResult }) {
  const m = result.metrics;
  return (
    <section
      aria-label={result.label}
      className="border border-terminal-700 rounded p-4 space-y-4"
    >
      <h3 className="font-bold text-sm">{result.label}</h3>
      <p>
        {result.from} → {result.to} · {result.bars} observed 5-minute bars.
      </p>
      <p className="text-amber-200">
        {result.incomplete
          ? "INCOMPLETE — inspect missing coverage, unfilled signals and unresolved positions."
          : "Resolved imported sample only — not proof of market-wide coverage."}
      </p>
      <dl className="grid grid-cols-2 xl:grid-cols-4 gap-3">
        {[
          ["Setups", String(result.setups)],
          ["Completed simulated trades", String(m.completed)],
          [
            "Win rate",
            m.winRate == null
              ? "Unavailable"
              : `${(m.winRate * 100).toFixed(1)}%`,
          ],
          ["Average winner", money(m.averageWinner)],
          ["Average loser", money(m.averageLoser)],
          [
            "Profit factor",
            m.profitFactor?.toFixed(2) ?? "Unavailable (no losses)",
          ],
          ["Average R", m.averageR?.toFixed(2) ?? "Unavailable"],
          ["Expectancy in R", m.expectancyR?.toFixed(2) ?? "Unavailable"],
          ["Maximum simulated closed-trade drawdown", money(m.maxDrawdown)],
          ["Consecutive losses", String(m.consecutiveLosses ?? "Unavailable")],
        ].map(([k, v]) => (
          <div key={k} className="bg-terminal-950 rounded p-3">
            <dt className="text-terminal-400">{k}</dt>
            <dd className="mt-2">{v}</dd>
          </div>
        ))}
      </dl>
      <EquityCurve result={result} />
      <div className="overflow-x-auto">
        <table className="w-full text-left whitespace-nowrap">
          <caption className="text-left py-2">
            Hypothetical trade-by-trade results · exit times identify bars, not
            exact fills.
          </caption>
          <thead>
            <tr>
              {[
                "Direction",
                "Confirmation / entry UTC",
                "Exit bar UTC",
                "Entry / stop / target / exit",
                "Lots / costs",
                "Net USD / R",
                "Resolution",
              ].map((h) => (
                <th className="p-2" key={h}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.trades.map((t, i) => (
              <tr key={i} className="border-t border-terminal-800">
                <td className="p-2">
                  {t.instrument} {t.direction}
                </td>
                <td className="p-2">
                  {t.confirmationTime}
                  <br />
                  {t.entryTime}
                </td>
                <td className="p-2">{t.exitTime ?? "Unresolved"}</td>
                <td className="p-2">
                  {t.entry} / {t.stop} / {t.target} / {t.exit ?? "?"}
                </td>
                <td className="p-2">
                  {t.lots} / {money(t.costs)}
                </td>
                <td className="p-2">
                  {money(t.netPnl)} / {t.r?.toFixed(2) ?? "?"}
                </td>
                <td className="p-2">
                  <details>
                    <summary>{t.outcome}</summary>
                    <p className="max-w-xs whitespace-normal">{t.note}</p>
                  </details>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details>
        <summary className="cursor-pointer text-profit">
          Performance breakdowns and coverage diagnostics
        </summary>
        <div className="space-y-3 mt-3">
          {[
            ["Instrument", result.byInstrument],
            ["UTC session", result.bySession],
            ["Long versus short", result.byDirection],
            [
              "Market condition (existing trend classification only)",
              result.byCondition,
            ],
          ].map(([label, group]) => (
            <div key={String(label)}>
              <h4 className="font-bold">{String(label)}</h4>
              <ul>
                {Object.entries(group).map(([key, value]) => (
                  <li key={key}>
                    {key}: {value.completed} completed · net{" "}
                    {money(value.netPnl)} · average R{" "}
                    {value.averageR?.toFixed(2) ?? "unavailable"}
                  </li>
                ))}
              </ul>
            </div>
          ))}
          <ul className="text-amber-200">
            {Object.entries(result.diagnostics).map(([message, count]) => (
              <li key={message}>
                {message}: {count}
              </li>
            ))}
          </ul>
        </div>
      </details>
    </section>
  );
}
export function BacktestResearch() {
  const [dataset, setDataset] = useState(""),
    [config, setConfig] = useState(""),
    [result, setResult] = useState<ReturnType<typeof runBacktest> | null>(null),
    [error, setError] = useState("");
  return (
    <section
      id="historical-backtesting"
      aria-label="Historical Strategy Backtesting"
      className="rounded border border-terminal-800 bg-terminal-900 p-5 space-y-4"
    >
      <h2 className="text-base font-bold">Historical Strategy Backtesting</h2>
      <h3 className="text-profit font-bold">
        Has the strategy performed well historically?
      </h3>
      <p>
        Replay the existing strategy on completed historical candles. No live
        recommendation, broker execution or journal writes. No provider is
        connected. Import only data you are authorized to use, with instrument
        mapping and contract provenance.
      </p>
      <div className="flex flex-wrap gap-2">
        {(["long", "short"] as const).map((d) => (
          <button
            key={d}
            className={button}
            onClick={() => {
              const f = backtestFixture(d);
              setDataset(JSON.stringify(f.dataset, null, 2));
              setConfig(JSON.stringify(f.config, null, 2));
              setResult(null);
              setError("");
            }}
          >
            Load synthetic {d} replay
          </button>
        ))}
      </div>
      <details>
        <summary className="cursor-pointer text-profit">
          Historical import and execution assumptions
        </summary>
        <div className="space-y-3 mt-3">
          <p>
            Schema 1 JSON: 1H/15M/5M completed UTC bars, sourced pre-existing
            targets, explicit symbol/contract/rights mapping, optional sourced
            closed periods. Each partition is limited to 2,000 entry bars;
            imports to 5 MB. Missing periods reset strategy warm-up; no prices
            are interpolated. In-sample and validation windows are independent
            and nonoverlapping; prior observed candles may warm up validation.
            You choose the split before running; the app cannot prove you did
            not tune on validation.
          </p>
          <label className="block">
            Historical dataset JSON
            <textarea
              aria-label="Historical dataset JSON"
              className={`${input} h-64 mt-2`}
              value={dataset}
              onChange={(e) => {
                setDataset(e.target.value);
                setResult(null);
              }}
            />
          </label>
          <label className="block">
            Backtest configuration JSON
            <textarea
              aria-label="Backtest configuration JSON"
              className={`${input} h-64 mt-2`}
              value={config}
              onChange={(e) => {
                setConfig(e.target.value);
                setResult(null);
              }}
            />
          </label>
        </div>
      </details>
      <button
        className={button}
        onClick={() => {
          try {
            if (dataset.length + config.length > 5000000)
              throw Error("Backtest import exceeds 5 MB");
            setResult(runBacktest(JSON.parse(dataset), JSON.parse(config)));
            setError("");
          } catch (e) {
            setResult(null);
            setError(
              e instanceof Error ? e.message : "Invalid historical input",
            );
          }
        }}
      >
        Run deterministic backtest
      </button>
      <p role="status" className="text-amber-200">
        {error}
      </p>
      {result && (
        <div className="space-y-5">
          <p className="text-amber-200 font-bold">
            HYPOTHETICAL BACKTEST · {result.dataMode.toUpperCase()} ·{" "}
            {result.source}
          </p>
          <p>{result.executionModel}</p>
          <p className="text-terminal-400">
            Declared round-trip costs: {result.config.spec.spreadTicks} spread
            ticks + {result.config.spec.slippageTicks} slippage ticks;
            commission {money(result.config.spec.commissionPerLot)}/lot; fixed{" "}
            {money(result.config.spec.fixedFees)}. Historical financing, spread
            variation and liquidity are not established by these assumptions.
          </p>
          <Results result={result.development} />
          <Results result={result.validation} />
          <details>
            <summary>Reproducible result JSON</summary>
            <pre className="overflow-auto max-h-64">
              {JSON.stringify(result, null, 2)}
            </pre>
          </details>
        </div>
      )}
    </section>
  );
}
