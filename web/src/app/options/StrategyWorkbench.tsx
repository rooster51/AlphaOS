"use client";

import { useState } from "react";
import { defaultLimits, strategyNames, type ScenarioSelection, type ResearchResult } from "@/lib/options-research";

type Contract = { contract: string | null; type: string; strike: number | null; status: string };
const control = "rounded border border-terminal-700 bg-terminal-900 px-3 py-2 disabled:opacity-50";
const money = (value: number | null | undefined) => value == null ? "Unavailable" :
  value.toLocaleString("en-US", { style: "currency", currency: "USD" });
const words = (text: string) => text.replaceAll("_", " ");
const roles: Record<string, [string, string, number][]> = {
  long_call: [["Buy call", "Call", 1]], long_put: [["Buy put", "Put", 1]],
  call_debit_spread: [["Buy lower call", "Call", 1], ["Sell upper call", "Call", -1]],
  put_debit_spread: [["Buy upper put", "Put", 1], ["Sell lower put", "Put", -1]],
  put_credit_spread: [["Buy lower put", "Put", 1], ["Sell upper put", "Put", -1]],
  call_credit_spread: [["Buy upper call", "Call", 1], ["Sell lower call", "Call", -1]],
  iron_condor: [["Buy lower put", "Put", 1], ["Sell upper put", "Put", -1], ["Sell lower call", "Call", -1], ["Buy upper call", "Call", 1]],
  iron_butterfly: [["Buy lower put", "Put", 1], ["Sell center put", "Put", -1], ["Sell center call", "Call", -1], ["Buy upper call", "Call", 1]],
  long_call_butterfly: [["Buy lower call", "Call", 1], ["Sell two center calls", "Call", -2], ["Buy upper call", "Call", 1]],
  long_put_butterfly: [["Buy lower put", "Put", 1], ["Sell two center puts", "Put", -2], ["Buy upper put", "Put", 1]],
  long_straddle: [["Buy call at shared strike", "Call", 1], ["Buy put at shared strike", "Put", 1]],
  long_strangle: [["Buy upper call", "Call", 1], ["Buy lower put", "Put", 1]],
  custom: [["Signed leg 1", "Both", 1]],
};

export function StrategyWorkbench({ symbol, expiration, contracts }: {
  symbol: string; expiration: string; contracts: Contract[];
}) {
  const [strategy, setStrategy] = useState("long_call");
  const [selections, setSelections] = useState<string[]>([""]);
  const [quantities, setQuantities] = useState<number[]>([1]);
  const [units, setUnits] = useState(1);
  const [limits, setLimits] = useState({ ...defaultLimits });
  const [fee, setFee] = useState(0.65);
  const [queue, setQueue] = useState<ScenarioSelection[]>([]);
  const [results, setResults] = useState<ResearchResult[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [sort, setSort] = useState("input");
  const template = strategy === "custom" ? selections.map((_, index) => [`Signed leg ${index + 1}`, "Both", quantities[index]] as [string, string, number]) : roles[strategy];
  const selectable = contracts.filter(contract => contract.contract && contract.status === "fresh");
  const ordered = results.map((result, index) => ({ result, index })).sort((a, b) => {
    const metric = (result: ResearchResult) => {
      if (!result.eligible_for_analysis) return null;
      if (sort === "risk") return result.loss_unbounded ? Infinity : result.max_loss;
      if (sort === "profit") return result.profit_unbounded ? Infinity : result.max_profit;
      return result.return_on_max_risk;
    };
    if (sort === "input") return a.index - b.index;
    const left = metric(a.result), right = metric(b.result);
    if (left == null) return right == null ? a.index - b.index : 1;
    if (right == null) return -1;
    if (left === right) return a.index - b.index;
    return sort === "risk" ? (left < right ? -1 : 1) : (left > right ? -1 : 1);
  });

  function invalidate() { setResults([]); setMessage(""); }
  function chooseStrategy(value: string) {
    setStrategy(value);
    setSelections(roles[value].map(() => ""));
    setQuantities(roles[value].map(role => role[2]));
  }
  async function evaluate() {
    setBusy(true); invalidate();
    try {
      const response = await fetch(`/api/options?${new URLSearchParams({ symbol, expiration })}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, cache: "no-store",
        body: JSON.stringify({ scenarios: queue, limits, entry_fee_per_contract: fee }),
        signal: AbortSignal.timeout(10000),
      });
      const body = await response.json() as { code?: string; scenarios?: ResearchResult[] };
      if (!response.ok || !body.scenarios) setMessage(`NO TRADE · ${words(body.code ?? "research_unavailable")}`);
      else setResults(body.scenarios);
    } catch { setMessage("NO TRADE · Request unavailable. Refresh the chain and retry."); }
    finally { setBusy(false); }
  }

  return <section className="space-y-4 rounded border border-terminal-800 p-4" aria-label="Strategy Comparison Workbench">
    <h2 className="font-bold">Strategy Comparison Workbench</h2>
    <p>Compare up to eight scenarios for {symbol} · {expiration}. Quotes are checked again on evaluation. Sorting describes the selected metric and does not identify a preferred trade.</p>
    <fieldset disabled={busy} className="flex flex-wrap items-end gap-3">
      <label className="grid gap-1">Strategy
        <select aria-label="Strategy" className={control} value={strategy} onChange={event => chooseStrategy(event.target.value)}>
          {Object.entries(strategyNames).map(([value, name]) => <option key={value} value={value}>{name}</option>)}
        </select>
      </label>
      <label className="grid gap-1">Position units
        <input aria-label="Position units" className={`${control} w-24`} type="number" min={1} max={20} step={1} value={units} onChange={event => setUnits(Number(event.target.value))} />
      </label>
      {template.map(([role, side, quantity], index) => <div key={index} className="flex flex-wrap items-end gap-2">
        <label className="grid gap-1">{role} · signed quantity {quantity * units}
          <select aria-label={`Workbench ${role}`} className={`${control} max-w-full`} value={selections[index]} onChange={event => setSelections(selections.map((value, i) => i === index ? event.target.value : value))}>
            <option value="">Choose a contract</option>
            {selectable.filter(contract => side === "Both" || contract.type === side).map(contract =>
              <option key={contract.contract} value={contract.contract!}>{contract.type} {contract.strike} · {contract.contract}</option>)}
          </select>
        </label>
        {strategy === "custom" && <label className="grid gap-1">Signed quantity
          <input aria-label={`Quantity for leg ${index + 1}`} className={`${control} w-24`} type="number" min={-20} max={20} step={1} value={quantities[index]} onChange={event => setQuantities(quantities.map((value, i) => i === index ? Number(event.target.value) : value))} />
        </label>}
      </div>)}
      {strategy === "custom" && <>
        <button className={control} disabled={selections.length >= 8} onClick={() => { setSelections([...selections, ""]); setQuantities([...quantities, 1]); }}>Add leg</button>
        <button className={control} disabled={selections.length <= 1} onClick={() => { setSelections(selections.slice(0, -1)); setQuantities(quantities.slice(0, -1)); }}>Remove last leg</button>
      </>}
      <button className={control} disabled={queue.length >= 8 || selections.some(value => !value) || !Number.isInteger(units) || units < 1 || template.some(role => !Number.isInteger(role[2] * units) || !role[2] || Math.abs(role[2] * units) > 20)} onClick={() => {
        setQueue([...queue, { strategy, legs: selections.map((contract, index) => ({ contract, qty: template[index][2] * units })) }]); invalidate();
      }}>Add scenario to comparison</button>
    </fieldset>
    <fieldset disabled={busy} className="flex flex-wrap items-end gap-3 rounded border border-terminal-800 p-3">
      <legend>Hypothetical constraints</legend>
      {Object.entries(limits).map(([key, value]) => <label className="grid gap-1 capitalize" key={key}>{words(key)}{key.includes("debit") || key.includes("loss") || key.includes("credit") || key.includes("spread") ? " ($)" : ""}
        <input aria-label={words(key)} className={`${control} w-32`} type="number" min={key === "max_contracts" ? 1 : 0} step={["max_contracts", "dte_min", "dte_max"].includes(key) ? 1 : "any"} value={value ?? ""} placeholder="No limit" onChange={event => {
          setLimits({ ...limits, [key]: event.target.value === "" ? null : Number(event.target.value) }); invalidate();
        }} />
      </label>)}
      <label className="grid gap-1">Entry fee per contract ($)
        <input aria-label="Entry fee per contract" className={`${control} w-32`} type="number" min={0} max={100} step="any" value={fee} onChange={event => { setFee(Number(event.target.value)); invalidate(); }} />
      </label>
    </fieldset>
    <p>Maximum contracts counts all absolute leg quantities, including butterfly bodies. Minimum credit applies to credit structures after entry fees. Debit and loss limits include entry fees.</p>
    <ol className="list-decimal pl-6 space-y-2">{queue.map((item, index) => <li key={index}>
      {strategyNames[item.strategy as keyof typeof strategyNames]} · {item.legs.map(leg => `${leg.qty > 0 ? "+" : ""}${leg.qty} ${leg.contract}`).join(" / ")}
      <button className={`${control} ml-2`} disabled={busy} onClick={() => { setQueue(queue.filter((_, i) => i !== index)); invalidate(); }} aria-label={`Remove scenario ${index + 1}`}>Remove</button>
    </li>)}</ol>
    <button className={control} disabled={busy || !queue.length} onClick={() => void evaluate()}>Evaluate comparison</button>
    <div role="status">{busy ? "Evaluating selected contracts…" : message}</div>
    {!!results.length && <>
      <label className="grid gap-1 w-fit">Comparison sort
        <select aria-label="Comparison sort" className={control} value={sort} onChange={event => setSort(event.target.value)}>
          <option value="input">Input order</option><option value="risk">Maximum loss, ascending</option><option value="profit">Maximum theoretical profit, descending</option><option value="return">Defined-risk return, descending</option>
        </select>
      </label>
      <div className="overflow-x-auto" tabIndex={0}>
        <table className="w-full whitespace-nowrap text-left" aria-label="Strategy comparison">
          <thead><tr>{["Scenario", "Expiration / DTE", "Eligibility", "Net entry cash", "Max profit", "Max loss / capital at risk", "Return on max risk", "Breakevens", "Direction", "Oldest quote age"].map(name => <th key={name} className="px-3 py-2">{name}</th>)}</tr></thead>
          <tbody>{ordered.map(({ result, index }) => <tr key={index} className="border-t border-terminal-800">
            {[`${index + 1}. ${strategyNames[result.strategy as keyof typeof strategyNames]}`, `${result.expiration ?? expiration} / ${result.dte ?? "—"}`,
              result.eligible_for_analysis ? "Eligible for analysis" : `NO TRADE · ${words(result.reason ?? "unavailable")}`,
              money(result.net_cash), result.profit_unbounded ? "Unlimited" : money(result.max_profit), result.loss_unbounded ? "Unlimited" : money(result.max_loss),
              result.return_on_max_risk == null ? "Unavailable" : `${(result.return_on_max_risk * 100).toFixed(1)}%`, result.breakevens?.map(money).join(", ") || "Unavailable", words(result.direction ?? "unavailable"), result.oldest_quote_age_seconds == null ? "Unavailable" : `${result.oldest_quote_age_seconds.toFixed(1)}s at evaluation`]
              .map((value, column) => <td key={column} className="px-3 py-2">{value}</td>)}
          </tr>)}</tbody>
        </table>
      </div>
      {results.map((result, index) => <details key={index} className="rounded border border-terminal-800 p-3">
        <summary className="cursor-pointer">Scenario {index + 1} · evidence, assumptions and terminal payoff</summary>
        <div className="space-y-2 pt-3">
          <p>Evaluated {result.evaluated_at ?? "unavailable"} · Retrieved {result.retrieved_at ?? "unavailable"} · Standard multiplier 100</p>
          <p>Premium cashflow {money(result.entry_premium)} · Entry fees {money(result.entry_fees)} · {result.total_contracts ?? "—"} contracts</p>
          <p>{words(result.capital_treatment ?? "unavailable")}</p>
          {result.limit_breaches?.map(reason => <p key={reason}>NO TRADE · {words(reason)}</p>)}
          {result.legs?.map(leg => <p key={leg.contract}>{leg.qty > 0 ? "Buy at ask" : "Sell at bid"} {Math.abs(leg.qty)} × {leg.contract} · {money(leg.price)} per share · bid {leg.bid_timestamp} · ask {leg.ask_timestamp}</p>)}
          {result.liquidity_warnings?.map((warning, i) => <p key={i}>{warning}</p>)}
          <p>Signed Greek exposure (100-share multiplier) · {Object.entries(result.greek_exposure ?? {}).map(([key, value]) => `${key} ${value == null ? "unavailable" : value.toFixed(3)}`).join(" · ")}</p>
          {result.assumptions?.map(assumption => <p key={assumption}>{assumption}</p>)}
          {!!result.payoff?.length && <div className="max-h-64 overflow-auto"><table aria-label={`Scenario ${index + 1} terminal payoff`} className="w-full text-left">
            <thead><tr><th>Terminal underlying</th><th>Expiration P/L</th></tr></thead>
            <tbody>{result.payoff.map(point => <tr key={point.terminal_price}><td>{money(point.terminal_price)}</td><td>{money(point.pnl)}</td></tr>)}</tbody>
          </table></div>}
        </div>
      </details>)}
    </>}
  </section>;
}
