"use client";

import { useState } from "react";
import { StrategyWorkbench } from "./StrategyWorkbench";

type Right = "Call" | "Put";
type Leg = {
  contract: string | null; type: Right; status: string;
  strike: number | null; bid: number | null; ask: number | null;
  bid_timestamp: string | null; ask_timestamp: string | null; last_timestamp: string | null;
} & Record<string, string | number | null>;
type Scenario = {
  status: string; reason?: string; net_cash: number; max_profit: number | null;
  max_loss: number; breakevens: number[]; width: number | null;
  legs: { contract: string; qty: number; price: number }[];
};
type Chain = {
  source: string; retrieved_at: string; max_quote_age_seconds: number;
  chain: { calls: Leg[]; puts: Leg[] };
  underlying?: { quote: { last: number; updated_at: string } };
  underlying_eligible?: boolean;
  scenario?: Scenario;
};

const control = "rounded border border-terminal-700 bg-terminal-900 px-3 py-2 disabled:opacity-50";
const fields = ["last", "bid", "ask", "bid_size", "ask_size", "iv", "delta", "gamma", "theta", "vega", "rho", "volume", "open_interest"] as const;
const label = (value: string) => value.replaceAll("_", " ");
const dollars = (value: number) => value.toLocaleString("en-US", { style: "currency", currency: "USD" });

export function OptionsChain() {
  const [symbol, setSymbol] = useState("SPY");
  const [date, setDate] = useState("");
  const [expirations, setExpirations] = useState<string[]>([]);
  const [side, setSide] = useState<"Both" | Right>("Both");
  const [data, setData] = useState<Chain>();
  const [buy, setBuy] = useState("");
  const [sell, setSell] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [scenario, setScenario] = useState<Scenario>();
  const legs = data ? [...data.chain.calls, ...data.chain.puts]
    .sort((a, b) => (a.strike ?? Infinity) - (b.strike ?? Infinity)) : [];
  const selectable = legs.filter(leg => leg.status === "fresh" && leg.contract);
  const spot = data?.underlying?.quote.last;

  function clearChain() {
    setData(undefined);
    setBuy("");
    setSell("");
    setScenario(undefined);
    setMessage("");
  }

  async function load(action: "discover" | "chain" | "scenario") {
    setBusy(true);
    setMessage("");
    setScenario(undefined);
    if (action === "discover") setExpirations([]);
    if (action === "chain") setData(undefined);
    const query = new URLSearchParams({ symbol });
    if (action !== "discover") query.set("expiration", date);
    if (action === "scenario") {
      query.set("buy", buy);
      if (sell) query.set("sell", sell);
    }
    try {
      const response = await fetch(`/api/options?${query}`, { cache: "no-store", signal: AbortSignal.timeout(10000) });
      const result: unknown = await response.json();
      if (!response.ok) {
        const code = (result as { code?: string } | null)?.code ?? "request_failed";
        setMessage(action === "discover"
          ? `Expiration discovery unavailable (${label(code)}). Enter a known expiration below.`
          : `Research unavailable · ${label(code)}.`);
        return;
      }
      if (action === "discover") {
        const { expirations: dates } = result as { expirations: string[] };
        setExpirations(dates);
        if (!dates.length) setMessage("Public returned no expirations. Enter a known expiration to check it directly.");
      } else {
        const chain = result as Chain;
        setData(chain);
        setScenario(chain.scenario);
      }
    } catch {
      setMessage("The request could not be completed. Retry when ready.");
    } finally {
      setBusy(false);
    }
  }

  return <main className="space-y-5 p-4 md:p-8 font-mono text-sm">
    <p>Choose a symbol and discover expirations, or enter a known expiration to request its chain directly.</p>
    <fieldset disabled={busy} className="flex flex-wrap items-end gap-3">
      <label className="grid gap-1">Symbol
        <select aria-label="Symbol" className={control} value={symbol} onChange={event => {
          setSymbol(event.target.value); setDate(""); setExpirations([]); clearChain();
        }}><option>SPY</option><option>QQQ</option></select>
      </label>
      <button className={control} onClick={() => void load("discover")}>Discover expirations</button>
      {!!expirations.length && <label className="grid gap-1">Public expirations
        <select aria-label="Public expirations" className={control} value={expirations.includes(date) ? date : ""} onChange={event => {
          setDate(event.target.value); clearChain();
        }}><option value="">Choose a date</option>
          {expirations.map(value => <option key={value}>{value}</option>)}
        </select>
      </label>}
      <label className="grid gap-1">Expiration
        <input type="date" className={control} value={date} onChange={event => {
          setDate(event.target.value); clearChain();
        }} />
      </label>
      <button className={control} disabled={!date} onClick={() => void load("chain")}>Refresh chain</button>
      <label className="grid gap-1">Display
        <select aria-label="Display" className={control} value={side} onChange={event => setSide(event.target.value as typeof side)}>
          <option value="Both">Both</option><option value="Call">Calls</option><option value="Put">Puts</option>
        </select>
      </label>
    </fieldset>
    <div role="status">{busy ? "Requesting Public data…" : message}</div>
    {data && <>
      <section className="space-y-1 text-terminal-300" aria-label="Quote provenance">
        <p>{symbol} · {date} · {data.source} · Retrieved {data.retrieved_at}</p>
        <p>Underlying {spot === undefined ? "unavailable" : `${dollars(spot)} · ${data.underlying_eligible ? "fresh at retrieval" : "context only"} · ${data.underlying!.quote.updated_at ?? "timestamp unavailable"}`}</p>
        <p>Freshness labels reflect retrieval or evaluation time. Both provider bid and ask must be within {data.max_quote_age_seconds}s at evaluation.</p>
        {(!data.chain.calls.length || !data.chain.puts.length) && <p>Partial chain · Public returned no {data.chain.calls.length ? "puts" : "calls"}.</p>}
      </section>
      <section className="space-y-3 rounded border border-terminal-800 p-4" aria-label="Strategy scenario">
        <h2 className="font-bold">Strategy scenario</h2>
        <p>Buy at ask. Sell at bid. One standard 100-share lot per leg. Expiration payoff excludes fees and assumes theoretical fills. Assignment and leg execution can affect actual outcomes.</p>
        <fieldset disabled={busy} className="flex flex-wrap items-end gap-3">
          {([{ title: "Buy contract", value: buy, set: setBuy }, { title: "Sell contract (optional)", value: sell, set: setSell }]).map(({ title, value, set }) =>
            <label key={title} className="grid gap-1">{title}
              <select aria-label={title} className={control} value={value} onChange={event => { set(event.target.value); setScenario(undefined); }}>
                <option value="">Select contract</option>
                {selectable.map(leg => <option key={leg.contract} value={leg.contract!}>{leg.type} {leg.strike} · {leg.contract}</option>)}
              </select>
            </label>)}
          <button className={control} disabled={!buy} onClick={() => void load("scenario")}>Evaluate scenario</button>
        </fieldset>
        {!selectable.length && <p>Insufficient evidence · No contract has verified fresh pricing evidence.</p>}
        {scenario && (scenario.status === "available" ? <div className="space-y-1">
          <p>Net {scenario.net_cash < 0 ? "debit" : "credit"} {dollars(Math.abs(scenario.net_cash))} per position</p>
          <p>Maximum theoretical gain {scenario.max_profit === null ? "unlimited" : dollars(scenario.max_profit)}</p>
          <p>Maximum theoretical loss and total risk {dollars(scenario.max_loss)} per position</p>
          <p>Expiration breakeven {scenario.breakevens.map(dollars).join(", ") || "unavailable"}</p>
          {scenario.width !== null && <p>Spread width {dollars(scenario.width)}</p>}
          {scenario.legs.map(leg => <p key={leg.contract}>{leg.qty > 0 ? "Buy at ask" : "Sell at bid"} · {leg.contract} · {dollars(leg.price)} per share</p>)}
        </div> : <p>{scenario.reason === "Fresh underlying quote unavailable." || scenario.reason === "Selected contract has insufficient pricing evidence."
          ? "Insufficient evidence" : "Scenario unavailable"} · {scenario.reason}</p>)}
      </section>
      <StrategyWorkbench key={`${symbol}-${date}-${data.retrieved_at}`} symbol={symbol} expiration={date} contracts={legs} />
      <div className="overflow-x-auto rounded border border-terminal-800" tabIndex={0} aria-label="Scrollable options table">
        <table className="w-full whitespace-nowrap text-left">
          <thead><tr>{["Strike", "Side", "Moneyness", "Contract", "Status", "Age (s)", "Spread", ...fields.map(label), "Provider bid time", "Provider ask time", "Provider last time"].map(name =>
            <th className="px-3 py-2 capitalize" key={name}>{name}</th>)}</tr></thead>
          <tbody>{legs.filter(leg => side === "Both" || side === leg.type).map((leg, index) => {
            const moneyness = spot === undefined || leg.strike === null ? "—" : spot === leg.strike ? "ATM" :
              (leg.type === "Call" ? spot > leg.strike : spot < leg.strike) ? "ITM" : "OTM";
            const spread = leg.bid !== null && leg.ask !== null && leg.bid >= 0 && leg.ask > 0 && leg.ask >= leg.bid
              ? (leg.ask - leg.bid).toFixed(2) : null;
            return <tr key={index} className="border-t border-terminal-800">
              {[leg.strike, leg.type, moneyness, leg.contract, label(leg.status),
                typeof leg.quote_age_seconds === "number" ? leg.quote_age_seconds.toFixed(1) : null,
                spread, ...fields.map(field => leg[field]), leg.bid_timestamp, leg.ask_timestamp, leg.last_timestamp]
                .map((value, column) => <td className="px-3 py-2" key={column}>{value ?? "—"}</td>)}
            </tr>;
          })}</tbody>
        </table>
      </div>
    </>}
  </main>;
}
