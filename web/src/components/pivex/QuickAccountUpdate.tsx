"use client";
import type { FormEvent } from "react";
import { indicativeProgress, validateQuickReport } from "@/lib/pivex/progress";
import type { QuickReport } from "@/lib/pivex/progress";
import type { Rules } from "@/lib/pivex/challenge";
const input =
  "w-full rounded border border-terminal-700 bg-terminal-950 px-3 py-2 text-terminal-100";
const money = (n: number | null | undefined) =>
  n == null
    ? "Unknown"
    : new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
      }).format(n);
export function QuickAccountUpdate({
  reports,
  rules,
  now,
  days,
  dailyAllowance,
  ready,
  onSave,
}: {
  reports: QuickReport[];
  rules: Rules;
  now: string;
  days: number;
  dailyAllowance: number | null;
  ready: boolean;
  onSave: (q: QuickReport) => void;
}) {
  const latest =
    [...reports]
      .reverse()
      .filter((q) => Date.parse(q.observedAt) <= Date.parse(now))
      .sort((a, b) => Date.parse(b.observedAt) - Date.parse(a.observedAt))
      .at(0) ?? null;
  const p = indicativeProgress(latest, rules);
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const f = new FormData(event.currentTarget),
      optional = (key: string) =>
        f.get(key) === "" ? null : Number(f.get(key));
    // Parent handles validation/save errors without clearing the user's inputs.
    onSave({
      schema: 1,
      id: crypto.randomUUID(),
      kind: "user_reported",
      source: "Manual quick account update",
      observedAt: String(f.get("observedAt")),
      valueType: f.get("valueType") as "balance" | "equity",
      value: Number(f.get("reportedValue")),
      realizedToday: Number(f.get("realizedToday")),
      floatingPnl: optional("floatingPnl"),
      fees: optional("fees"),
      openRisk: optional("openRisk"),
    });
  }
  return (
    <div className="space-y-4" aria-label="Quick Account Update">
      <h3 className="font-bold text-sm text-profit">
        How is my challenge progressing?
      </h3>
      <p className="text-amber-200">
        UNVERIFIED · User-reported progress only. Quick updates never establish
        broker verification, drawdown headroom or permission to trade.
      </p>
      <dl className="grid grid-cols-2 xl:grid-cols-4 gap-3">
        {[
          [
            "Reported challenge equity",
            p?.equity == null ? "Not supplied" : money(p.equity),
          ],
          ["Profit remaining (indicative)", money(p?.remaining)],
          ["Reported daily result", money(p?.dailyResult)],
          [
            "Personal daily risk remaining (advanced evidence)",
            money(dailyAllowance),
          ],
          ["Trading days recorded", String(days)],
          ["Latest quick update", p?.observedAt ?? "No quick updates"],
        ].map(([label, value]) => (
          <div
            key={label}
            className="rounded border border-terminal-800 bg-terminal-950 p-3"
          >
            <dt className="text-terminal-400">{label}</dt>
            <dd className="mt-2 break-words">{value}</dd>
          </div>
        ))}
      </dl>
      {p && (
        <div className="space-y-2">
          <label className="block">
            Challenge progress (indicative): {(p.progress * 100).toFixed(1)}%
            <progress
              className="w-full accent-emerald-400 mt-2"
              aria-label="Indicative challenge progress"
              value={p.progress}
              max={1}
            />
          </label>
          <p className="text-terminal-400">
            Basis: {p.basis}
            {p.balance !== null
              ? ` · Reported balance: ${money(p.balance)}`
              : ""}
            . Daily P&L and fees are displayed as reported; their net/gross
            treatment is unverified. They do not set a personal loss allowance.
          </p>
        </div>
      )}
      <form
        onSubmit={submit}
        className="space-y-3"
        aria-label="Quick Account Update form"
      >
        <h3 className="font-bold">Quick Account Update</h3>
        <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-3">
          <label>
            Reported value type
            <select className={input} name="valueType">
              <option value="equity">Equity</option>
              <option value="balance">Balance</option>
            </select>
          </label>
          <label>
            Reported balance or equity USD
            <input
              className={input}
              name="reportedValue"
              type="number"
              step="any"
              required
            />
          </label>
          <label>
            Today’s reported realized P&L USD
            <input
              className={input}
              name="realizedToday"
              type="number"
              step="any"
              required
            />
          </label>
          <label>
            Current floating P&L USD (optional)
            <input
              className={input}
              name="floatingPnl"
              type="number"
              step="any"
            />
          </label>
        </div>
        <details>
          <summary className="cursor-pointer text-profit">
            Optional costs, risk and observation time
          </summary>
          <div className="grid sm:grid-cols-3 gap-3 mt-3">
            <label>
              Separately reported fees USD
              <input
                className={input}
                name="fees"
                type="number"
                step="any"
                min="0"
              />
            </label>
            <label>
              Reported open planned risk USD
              <input
                className={input}
                name="openRisk"
                type="number"
                step="any"
                min="0"
              />
            </label>
            <label>
              Quick observation time (UTC ISO)
              <input
                className={input}
                name="observedAt"
                type="text"
                defaultValue={now}
                required
              />
            </label>
          </div>
        </details>
        <button
          disabled={!ready}
          className="rounded border border-emerald-700 px-4 py-2 bg-terminal-850 disabled:opacity-40"
        >
          Save quick update
        </button>
      </form>
    </div>
  );
}
