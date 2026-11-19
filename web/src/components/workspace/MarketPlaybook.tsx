"use client";

import { useEffect, useState } from "react";
import type { CandleSymbol } from "../../lib/candles";
import { parsePlaybook, type Level, type Playbook, type Scenario } from "../../lib/market-playbook";

const pollMs = 60_000;
const when = (value: string) => new Date(value).toLocaleString("en-US", { timeZone: "America/New_York" });
const price = (value: number) => value.toFixed(2);

function zone(level: Level) {
  return level.low === level.high ? price(level.low) : `${price(level.low)}–${price(level.high)}`;
}

function Thesis({ record }: { record: Scenario }) {
  const { thesis, state, updated_at, events } = record;
  const last = events.at(-1);
  return (
    <article className="min-w-0 rounded-lg border border-terminal-800 bg-terminal-950/60 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold capitalize">{thesis.direction} {thesis.family}</h3>
        <span className={state === "WAITING" ? "font-mono text-warning" : "font-mono"}>
          {state === "WAITING" ? "WAIT" : state}
        </span>
      </div>
      <p className="mt-2">{thesis.thesis}</p>
      <p>{thesis.structure}</p>
      <dl className="mt-2 space-y-1">
        <div><dt className="font-semibold">Trigger</dt><dd>{thesis.confirmation}</dd></div>
        <div><dt className="font-semibold">Invalidation</dt><dd>{thesis.invalidation_condition}</dd></div>
        <div><dt className="font-semibold">Target</dt><dd>{thesis.target_condition}</dd></div>
      </dl>
      <p className="mt-2">Evidence quality at creation · {thesis.quality}. Bias · {thesis.bias}.</p>
      <p>Supporting zones · {thesis.supporting.map(zone).join(", ")}.</p>
      {thesis.conflicting.length > 0 && <p>Conflicting evidence · {thesis.conflicting.join(" ")}</p>}
      <p className="mt-2 text-terminal-400">
        Updated {when(updated_at)} ET · Observation window ends {when(thesis.expires_at)} ET
      </p>
      <p className="text-terminal-400">
        {thesis.provenance.provider} snapshot from {when(thesis.provenance.retrieved_at)} ET
      </p>
      {last?.reason && <p className="mt-2">{last.reason}</p>}
      {events.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer">Recorded observations</summary>
          <ul className="mt-1 space-y-1">
            {events.map((event, index) => (
              <li key={index}>{when(event.bar_at ?? event.recorded_at)} ET · {event.state}</li>
            ))}
          </ul>
        </details>
      )}
    </article>
  );
}

function PlaybookView({ value }: { value: Playbook }) {
  const current = value.history.filter((record) => record.thesis.session === value.session);
  const earlier = value.history.filter((record) => record.thesis.session !== value.session);
  return (
    <div className="mt-3 space-y-4 text-xs leading-relaxed text-terminal-300">
      <div role="status" className="rounded-lg border border-warning/30 bg-warning-bg/10 p-3">
        <p className="font-mono font-semibold text-warning">{value.status}</p>
        <p>{value.reason}</p>
      </div>
      <p>{value.structure}</p>
      <p>Session {value.session ?? "unavailable"} · Directional bias {value.bias} · Evidence quality {value.quality}</p>
      <p>
        {value.provider} · {value.as_of ? `${when(value.as_of)} ET` : "No current snapshot"}
        {value.provenance && ` · ${value.provenance.freshness.replaceAll("_", " ")}`}
      </p>
      {value.provisional_range && (
        <p>Provisional opening range · {price(value.provisional_range.low)}–{price(value.provisional_range.high)}</p>
      )}
      {value.vwap && <p>Session VWAP · {price(value.vwap.value)} · Dynamic reference · {value.vwap.status}</p>}
      <div>
        <h3 className="font-semibold text-terminal-100">Ranked key levels</h3>
        {value.levels.length === 0 && <p>Waiting for verified structural levels.</p>}
        <ol className="mt-1 space-y-1">
          {value.levels.map((level) => (
            <li key={level.rank}>
              <details>
                <summary className="cursor-pointer">
                  <span className="font-mono">{zone(level)}</span> · {level.types.join(", ")}
                  { ` · ${level.observations} distinct observations · ${level.reactions} swing reactions`}
                </summary>
                <ul className="mt-1 pl-4 text-terminal-400">
                  {level.evidence.map((proof) => (
                    <li key={`${proof.kind}/${proof.observed_at}`}>
                      {proof.kind} · {when(proof.observed_at)} ET · {level.provenance.provider} {proof.source}
                    </li>
                  ))}
                </ul>
              </details>
            </li>
          ))}
        </ol>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {(["bullish", "bearish"] as const).map((direction) => {
          const record = current.find((item) => item.thesis.direction === direction);
          return record ? <Thesis key={direction} record={record} /> : (
            <div key={direction} className="rounded-lg border border-terminal-800 p-3">
              <h3 className="font-semibold capitalize">{direction} scenario</h3>
              <p className="font-mono text-warning">{value.status}</p>
              <p>{value.reason}</p>
            </div>
          );
        })}
      </div>
      <p className="text-terminal-400">
        Strong requires repeated evidence at the trigger zone and aligned bias. Mixed indicates weaker confluence or conflicting bias.
        Insufficient indicates a gap in usable data. Outcomes track underlying five-minute closes.
      </p>
      <details>
        <summary className="cursor-pointer font-semibold text-terminal-100">Prior session history</summary>
        <div className="mt-2 space-y-2">
          {earlier.length === 0 && <p>No prior scenarios are recorded.</p>}
          {earlier.map((record) => <Thesis key={record.thesis.id} record={record} />)}
        </div>
      </details>
    </div>
  );
}

function Observation({ symbol }: { symbol: CandleSymbol }) {
  const [result, setResult] = useState<{ value?: Playbook; message?: string }>();

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      let retry = true;
      try {
        const response = await fetch(`/api/market-playbook/${symbol}`, {
          method: "POST", headers: { "X-AlphaOS-Playbook": "observe" },
          cache: "no-store", signal: controller.signal,
        });
        const payload = await response.json();
        if (controller.signal.aborted) return;
        const value = response.ok ? parsePlaybook(payload, symbol) : null;
        if (value) setResult({ value });
        else {
          retry = response.status !== 401 && response.status !== 403 && payload?.code !== "feature_disabled";
          setResult({ message: payload?.code === "feature_disabled"
            ? "Market Playbook is disabled on this site."
            : response.status === 401 || response.status === 403
              ? "An entitled owner session is required."
              : "Waiting for the Market Playbook service." });
        }
      } catch {
        if (!controller.signal.aborted) setResult({ message: "Waiting for the Market Playbook service." });
      } finally {
        if (retry && !controller.signal.aborted) timer = setTimeout(poll, pollMs);
      }
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [symbol]);

  if (result?.value) return <PlaybookView value={result.value} />;
  return (
    <p role="status" className="mt-3 text-xs text-warning">
      {result?.message ? `WAIT · ${result.message}` : `Loading ${symbol} playbook…`}
    </p>
  );
}

export function MarketPlaybook({ symbol }: { symbol: CandleSymbol }) {
  const [open, setOpen] = useState(false);
  return (
    <details onToggle={(event) => setOpen(event.currentTarget.open)}
      className="rounded-xl border border-terminal-800 bg-terminal-900/70 p-4">
      <summary className="cursor-pointer font-semibold text-terminal-100">Market Playbook · {symbol}</summary>
      {open && <Observation key={symbol} symbol={symbol} />}
    </details>
  );
}
