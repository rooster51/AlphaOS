"use client";

import { useState } from "react";
import { Header } from "@/components/shell/Header";
import { StatusPill } from "@/components/shell/StatusPill";
import {
  MAX_COMPARE_STRUCTURES,
  MAX_LEGS,
  MAX_LEG_QUANTITY,
  buildStructureRequest,
  structureLabel,
  type LegDraft,
  type StructureForm,
  type StructureRequestInput,
} from "@/lib/structure-contract";
import { requestComparison, requestObservation, requestStructure } from "@/lib/structure-client";
import {
  structureMessage,
  type CompareView,
  type ObservationSeed,
  type Scalar,
  type StructureView,
} from "@/lib/structure-view";

type SingleState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "result"; view: StructureView };

type CompareState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "result"; view: CompareView };

type SeedState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "loaded"; seed: ObservationSeed };

type SavedScenario = { id: string; payload: StructureRequestInput; label: string };

const money = (value: number) =>
  value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

const number = (value: number) =>
  value.toLocaleString("en-US", { maximumFractionDigits: 4 });

const price = (value: number) => money(value);

function scalarText(value: Scalar): string {
  if (value.kind === "value") return money(value.value);
  return value.kind === "unlimited" ? "Unlimited" : "Unavailable";
}

function scalarVariant(value: Scalar): "archive" | "neutral" | "warning" {
  if (value.kind === "value") return "archive";
  return value.kind === "unlimited" ? "neutral" : "warning";
}

function label(value: string | null | undefined): string {
  return value ? value.replaceAll("_", " ") : "Unavailable";
}

function displayDate(value: string | null): string {
  return value && Number.isFinite(Date.parse(`${value}T00:00:00Z`)) ? value : "Unavailable";
}

function timestamp(value: string | null): string {
  if (!value) return "Unavailable";
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? new Date(parsed).toISOString() : "Unavailable";
}

const INPUT =
  "w-full rounded border border-terminal-700 bg-terminal-950 px-3 py-2 font-mono text-sm text-terminal-100 " +
  "focus:border-profit focus:outline-none focus:ring-1 focus:ring-profit/40";

function Field({
  id,
  label: text,
  hint,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block font-mono text-[11px] uppercase tracking-wider text-terminal-400">
        {text}
      </label>
      {children}
      {hint && <p className="font-mono text-[10px] text-terminal-500">{hint}</p>}
    </div>
  );
}

function Metric({
  label: text,
  value,
  caption,
}: {
  label: string;
  value: Scalar;
  caption?: string;
}) {
  return (
    <div className="rounded border border-terminal-800 bg-terminal-900 p-3">
      <p className="font-mono text-[11px] uppercase tracking-wider text-terminal-400">{text}</p>
      <p className="mt-1 font-mono text-lg font-bold text-terminal-100">
        {scalarText(value)}
      </p>
      <div className="mt-1 flex items-center justify-between gap-2">
        <StatusPill
          label={value.kind === "value" ? "BACKEND" : value.kind === "unlimited" ? "UNLIMITED" : "UNAVAILABLE"}
          variant={scalarVariant(value)}
        />
        {caption && <span className="font-mono text-[10px] text-terminal-500">{caption}</span>}
      </div>
    </div>
  );
}

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded border border-terminal-800 bg-terminal-900/60 p-5 space-y-4">
      <div>
        <h2 className="font-mono text-sm font-bold uppercase tracking-wider text-terminal-100">{title}</h2>
        {subtitle && <p className="mt-1 font-mono text-[11px] text-terminal-400">{subtitle}</p>}
      </div>
      {children}
    </section>
  );
}

const EMPTY_LEG: LegDraft = { type: "Call", action: "Buy", strike: "", quantity: "1" };

export function StructureWorkbench() {
  const [symbol, setSymbol] = useState<"SPY" | "QQQ">("QQQ");
  const [expiration, setExpiration] = useState("");
  const [asOf, setAsOf] = useState("");
  const [spot, setSpot] = useState("");
  const [side, setSide] = useState<"debit" | "credit">("debit");
  const [packagePrice, setPackagePrice] = useState("");
  const [fees, setFees] = useState("0");
  const [legs, setLegs] = useState<LegDraft[]>([{ ...EMPTY_LEG }]);
  const [thesis, setThesis] = useState("");
  const [formErrors, setFormErrors] = useState<string[]>([]);
  const [saved, setSaved] = useState<SavedScenario[]>([]);
  const [single, setSingle] = useState<SingleState>({ kind: "idle" });
  const [comparison, setComparison] = useState<CompareState>({ kind: "idle" });
  const [seed, setSeed] = useState<SeedState>({ kind: "idle" });

  const form: StructureForm = {
    symbol,
    expiration,
    asOf,
    spot,
    side,
    packagePrice,
    fees,
    legs,
  };

  function updateLeg(index: number, patch: Partial<LegDraft>) {
    setLegs((current) => current.map((leg, position) =>
      position === index ? { ...leg, ...patch } : leg));
  }

  function addLeg() {
    setLegs((current) => current.length >= MAX_LEGS ? current : [...current, { ...EMPTY_LEG }]);
  }

  function removeLeg(index: number) {
    setLegs((current) => current.length <= 1 ? current : current.filter((_, position) => position !== index));
  }

  async function loadObservation() {
    setSeed({ kind: "loading" });
    const outcome = await requestObservation(symbol);
    if (!outcome.ok) {
      setSeed({ kind: "error", message: structureMessage(outcome.code) });
      return;
    }
    setSpot(String(outcome.seed.spot));
    setExpiration(outcome.seed.expiration);
    setAsOf(outcome.seed.asOf);
    setSeed({ kind: "loaded", seed: outcome.seed });
  }

  function built(): StructureRequestInput | null {
    const result = buildStructureRequest(form);
    if (!result.ok) {
      setFormErrors(result.errors);
      return null;
    }
    setFormErrors([]);
    return result.value;
  }

  async function research() {
    const payload = built();
    if (!payload) return;
    setSingle({ kind: "loading" });
    const outcome = await requestStructure(payload);
    if (!outcome.ok) {
      setSingle({ kind: "error", message: structureMessage(outcome.code) });
      return;
    }
    setSingle({ kind: "result", view: outcome.view });
  }

  function saveScenario() {
    const payload = built();
    if (!payload) return;
    if (saved.length >= MAX_COMPARE_STRUCTURES) {
      setFormErrors([`Comparison accepts up to ${MAX_COMPARE_STRUCTURES} structures.`]);
      return;
    }
    const id = typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `scenario-${saved.length + 1}`;
    setSaved((current) => [...current, { id, payload, label: structureLabel(payload) }]);
  }

  async function compare() {
    if (saved.length === 0) {
      setComparison({ kind: "error", message: "Save at least one structure before comparing." });
      return;
    }
    setComparison({ kind: "loading" });
    const trimmed = thesis.trim();
    const outcome = await requestComparison({
      structures: saved.map((item) => item.payload),
      ...(trimmed ? { thesis } : {}),
    });
    if (!outcome.ok) {
      setComparison({ kind: "error", message: structureMessage(outcome.code) });
      return;
    }
    setComparison({ kind: "result", view: outcome.view });
  }

  return (
    <div>
      <Header
        title="Structure Lab"
        subtitle="Explicit option structures priced by the canonical backend; supplied cashflow is not a quote."
        badge={{ label: "READ ONLY · NO EXECUTION", variant: "neutral" }}
      />

      <div className="space-y-5 p-8">
        <section className="rounded border border-terminal-800 bg-terminal-900 p-5">
          <h2 className="font-mono text-sm font-bold uppercase tracking-wider text-terminal-100">
            Research a structure you specify
          </h2>
          <p className="mt-2 max-w-4xl font-mono text-xs leading-relaxed text-terminal-400">
            Workbench posts to the existing structure research endpoints. The backend computes
            expiration payoff, maximum profit and loss, breakevens and capital requirement from the
            legs and package cashflow you supply. This interface does not price options, rank
            structures, size positions, or assess broker buying power.
          </p>
          <p className="mt-2 max-w-4xl font-mono text-xs leading-relaxed text-terminal-500">
            Entry prices are submitted as one signed package cashflow per share for the whole
            package, which is what the backend accepts; it does not accept per-leg fill prices.
          </p>
        </section>

        <Section
          title="Scenario inputs"
          subtitle="Symbol, expiration, research date and scenario spot are all required by the backend."
        >
          <div className="grid gap-4 md:grid-cols-4">
            <Field id="structure-symbol" label="Symbol">
              <select
                id="structure-symbol"
                className={INPUT}
                value={symbol}
                onChange={(event) => setSymbol(event.target.value === "SPY" ? "SPY" : "QQQ")}
              >
                <option value="QQQ">QQQ</option>
                <option value="SPY">SPY</option>
              </select>
            </Field>
            <Field id="structure-expiration" label="Expiration">
              <input
                id="structure-expiration"
                className={INPUT}
                placeholder="YYYY-MM-DD"
                value={expiration}
                onChange={(event) => setExpiration(event.target.value)}
              />
            </Field>
            <Field id="structure-as-of" label="Research date (as_of)">
              <input
                id="structure-as-of"
                className={INPUT}
                placeholder="YYYY-MM-DD"
                value={asOf}
                onChange={(event) => setAsOf(event.target.value)}
              />
            </Field>
            <Field id="structure-spot" label="Scenario spot" hint="Underlying price for the payoff.">
              <input
                id="structure-spot"
                className={INPUT}
                inputMode="decimal"
                placeholder="0.00"
                value={spot}
                onChange={(event) => setSpot(event.target.value)}
              />
            </Field>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={loadObservation}
              disabled={seed.kind === "loading"}
              className="rounded border border-terminal-700 bg-terminal-850 px-3 py-2 font-mono text-xs text-terminal-100 hover:border-profit disabled:opacity-50"
            >
              {seed.kind === "loading" ? "Reading archive…" : "Prefill from verified archive observation"}
            </button>
            <span className="font-mono text-[10px] text-terminal-500">
              Observation only; it performs no research and returns no quotes.
            </span>
          </div>
          {seed.kind === "error" && (
            <p role="alert" className="font-mono text-xs text-loss">{seed.message}</p>
          )}
          {seed.kind === "loaded" && (
            <div className="rounded border border-terminal-800 bg-terminal-950 p-3 font-mono text-[11px] text-terminal-400">
              <div className="flex flex-wrap items-center gap-2">
                <StatusPill label="VERIFIED ARCHIVE OBSERVATION" variant="archive" />
                <span>{seed.seed.provider} · session {seed.seed.asOf}</span>
              </div>
              <p className="mt-2">
                Spot {price(seed.seed.spot)} observed at {timestamp(seed.seed.observedAt)} ({number(seed.seed.ageSeconds)}s old).
                This is a stored archive observation, not a live quote. Historical analog evidence also
                requires that session to be complete.
              </p>
            </div>
          )}

          <div className="grid gap-4 md:grid-cols-3">
            <Field id="structure-side" label="Package side">
              <select
                id="structure-side"
                className={INPUT}
                value={side}
                onChange={(event) => setSide(event.target.value === "credit" ? "credit" : "debit")}
              >
                <option value="debit">Debit (pay)</option>
                <option value="credit">Credit (receive)</option>
              </select>
            </Field>
            <Field
              id="structure-price"
              label="Package price per share"
              hint="Total net cashflow per share for the entered quantities."
            >
              <input
                id="structure-price"
                className={INPUT}
                inputMode="decimal"
                placeholder="0.00"
                value={packagePrice}
                onChange={(event) => setPackagePrice(event.target.value)}
              />
            </Field>
            <Field id="structure-fees" label="Fees (total dollars)" hint="Commission and fees for the package.">
              <input
                id="structure-fees"
                className={INPUT}
                inputMode="decimal"
                value={fees}
                onChange={(event) => setFees(event.target.value)}
              />
            </Field>
          </div>
        </Section>

        <Section
          title="Option legs"
          subtitle={`Up to ${MAX_LEGS} legs; use Buy or Sell per leg. Quantities are contracts from 1 to ${MAX_LEG_QUANTITY}.`}
        >
          <div className="space-y-3">
            {legs.map((leg, index) => (
              <div key={index} className="grid gap-3 md:grid-cols-5">
                <Field id={`leg-type-${index}`} label={`Leg ${index + 1} type`}>
                  <select
                    id={`leg-type-${index}`}
                    className={INPUT}
                    value={leg.type}
                    onChange={(event) => updateLeg(index, { type: event.target.value })}
                  >
                    <option value="Call">Call</option>
                    <option value="Put">Put</option>
                  </select>
                </Field>
                <Field id={`leg-action-${index}`} label="Action">
                  <select
                    id={`leg-action-${index}`}
                    className={INPUT}
                    value={leg.action}
                    onChange={(event) => updateLeg(index, {
                      action: event.target.value === "Sell" ? "Sell" : "Buy",
                    })}
                  >
                    <option value="Buy">Buy</option>
                    <option value="Sell">Sell</option>
                  </select>
                </Field>
                <Field id={`leg-strike-${index}`} label="Strike">
                  <input
                    id={`leg-strike-${index}`}
                    className={INPUT}
                    inputMode="decimal"
                    placeholder="0.00"
                    value={leg.strike}
                    onChange={(event) => updateLeg(index, { strike: event.target.value })}
                  />
                </Field>
                <Field id={`leg-quantity-${index}`} label="Contracts">
                  <input
                    id={`leg-quantity-${index}`}
                    className={INPUT}
                    inputMode="numeric"
                    value={leg.quantity}
                    onChange={(event) => updateLeg(index, { quantity: event.target.value })}
                  />
                </Field>
                <div className="flex items-end">
                  <button
                    type="button"
                    onClick={() => removeLeg(index)}
                    disabled={legs.length <= 1}
                    className="w-full rounded border border-terminal-700 px-3 py-2 font-mono text-xs text-terminal-400 hover:border-loss hover:text-loss disabled:opacity-40"
                  >
                    Remove leg
                  </button>
                </div>
              </div>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={addLeg}
              disabled={legs.length >= MAX_LEGS}
              className="rounded border border-terminal-700 bg-terminal-850 px-3 py-2 font-mono text-xs text-terminal-100 hover:border-profit disabled:opacity-40"
            >
              Add leg
            </button>
            <span className="font-mono text-[10px] text-terminal-500">
              Supported families come from the backend: long call/put, debit or credit vertical,
              butterfly, broken-wing butterfly and iron condor.
            </span>
          </div>
          {formErrors.length > 0 && (
            <ul role="alert" className="space-y-1 font-mono text-xs text-loss">
              {formErrors.map((error) => <li key={error}>· {error}</li>)}
            </ul>
          )}
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={research}
              disabled={single.kind === "loading"}
              className="rounded border border-profit/40 bg-profit-bg px-4 py-2 font-mono text-xs font-semibold text-profit hover:border-profit disabled:opacity-50"
            >
              {single.kind === "loading" ? "Researching…" : "Research this structure"}
            </button>
            <button
              type="button"
              onClick={saveScenario}
              className="rounded border border-terminal-700 px-4 py-2 font-mono text-xs text-terminal-100 hover:border-profit"
            >
              Save for comparison
            </button>
          </div>
        </Section>

        {single.kind === "error" && (
          <section role="alert" className="rounded border border-loss/40 bg-loss-bg p-4 font-mono text-xs text-loss">
            {single.message}
          </section>
        )}

        {single.kind === "result" && (
          <>
            <Section
              title="Structure economics"
              subtitle="Every number below is returned by the backend for this exact scenario."
            >
              <div className="flex flex-wrap items-center gap-2">
                <StatusPill label={(single.view.family ?? "unknown").toUpperCase()} variant="neutral" />
                <StatusPill label={`DIRECTION ${(single.view.direction ?? "unknown").toUpperCase()}`} variant="neutral" />
                <StatusPill label="SUPPLIED CASHFLOW" variant="mock" />
                <span className="font-mono text-[11px] text-terminal-400">
                  {single.view.symbol} · expiration {displayDate(single.view.expiration)} · as of {displayDate(single.view.asOf)} · spot {price(single.view.spot)}
                </span>
              </div>

              <div className="grid gap-3 md:grid-cols-3">
                <Metric label="Max profit" value={single.view.maxProfit} />
                <Metric label="Max loss" value={single.view.maxLoss} />
                <Metric
                  label="Capital requirement"
                  value={single.view.capitalRequired}
                  caption="expiration max loss"
                />
                <div className="rounded border border-terminal-800 bg-terminal-900 p-3">
                  <p className="font-mono text-[11px] uppercase tracking-wider text-terminal-400">Breakevens</p>
                  <p className="mt-1 font-mono text-lg font-bold text-terminal-100">
                    {single.view.breakevens.length
                      ? single.view.breakevens.map((value) => price(value)).join(" · ")
                      : "Unavailable"}
                  </p>
                  <StatusPill
                    label={single.view.breakevens.length ? "BACKEND" : "UNAVAILABLE"}
                    variant={single.view.breakevens.length ? "archive" : "warning"}
                  />
                </div>
                <div className="rounded border border-terminal-800 bg-terminal-900 p-3">
                  <p className="font-mono text-[11px] uppercase tracking-wider text-terminal-400">Days to expiration</p>
                  <p className="mt-1 font-mono text-lg font-bold text-terminal-100">
                    {single.view.dte === null ? "Unavailable" : String(single.view.dte)}
                  </p>
                  <StatusPill
                    label={single.view.dte === null ? "UNAVAILABLE" : "BACKEND"}
                    variant={single.view.dte === null ? "warning" : "archive"}
                  />
                </div>
                <div className="rounded border border-terminal-800 bg-terminal-900 p-3">
                  <p className="font-mono text-[11px] uppercase tracking-wider text-terminal-400">Package cashflow</p>
                  <p className="mt-1 font-mono text-lg font-bold text-terminal-100">
                    {single.view.entryDebit
                      ? `${money(single.view.entryDebit)} debit`
                      : single.view.entryCredit
                        ? `${money(single.view.entryCredit)} credit`
                        : "Unavailable"}
                  </p>
                  <p className="font-mono text-[10px] text-terminal-500">
                    fees {single.view.fees === null ? "unavailable" : money(single.view.fees)}
                    {single.view.width !== null ? ` · width ${price(single.view.width)}` : ""}
                    {single.view.creditWidth !== null ? ` · credit/width ${number(single.view.creditWidth)}` : ""}
                  </p>
                </div>
              </div>

              {single.view.integrity.length > 0 && (
                <div role="alert" className="rounded border border-warning/40 bg-warning-bg p-3 font-mono text-[11px] text-warning">
                  <p className="font-semibold">Backend values disagree; the affected metrics are not reconciled here.</p>
                  <ul className="mt-1 space-y-0.5">
                    {single.view.integrity.map((item) => <li key={item}>· {label(item)}</li>)}
                  </ul>
                </div>
              )}

              <div className="overflow-x-auto">
                <table className="w-full border-collapse font-mono text-xs">
                  <caption className="pb-2 text-left font-mono text-[11px] text-terminal-500">
                    Positions as supplied; signed quantities are the backend&apos;s normalized legs.
                  </caption>
                  <thead>
                    <tr className="border-b border-terminal-800 text-left text-terminal-400">
                      <th className="py-2 pr-4">Action</th>
                      <th className="py-2 pr-4">Type</th>
                      <th className="py-2 pr-4">Strike</th>
                      <th className="py-2">Contracts</th>
                    </tr>
                  </thead>
                  <tbody>
                    {single.view.legs.map((leg, index) => (
                      <tr key={`${leg.type}-${leg.strike}-${index}`} className="border-b border-terminal-800/60 text-terminal-200">
                        <td className="py-2 pr-4">{leg.action}</td>
                        <td className="py-2 pr-4">{leg.type}</td>
                        <td className="py-2 pr-4">{price(leg.strike)}</td>
                        <td className="py-2">{leg.quantity}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {single.view.extremes.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse font-mono text-xs">
                    <caption className="pb-2 text-left font-mono text-[11px] text-terminal-500">
                      Backend expiration payoff at fixed terminal moves. Deterministic, not a forecast.
                    </caption>
                    <thead>
                      <tr className="border-b border-terminal-800 text-left text-terminal-400">
                        <th className="py-2 pr-4">Terminal underlying</th>
                        <th className="py-2 pr-4">Move from spot</th>
                        <th className="py-2">Expiration P&amp;L</th>
                      </tr>
                    </thead>
                    <tbody>
                      {single.view.extremes.map((row) => (
                        <tr key={row.price} className="border-b border-terminal-800/60 text-terminal-200">
                          <td className="py-2 pr-4">{price(row.price)}</td>
                          <td className="py-2 pr-4">
                            {row.movePct === null ? "Unavailable" : `${number(row.movePct)}%`}
                          </td>
                          <td className={`py-2 ${row.pnl >= 0 ? "text-profit" : "text-loss"}`}>{money(row.pnl)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <p className="font-mono text-[10px] text-terminal-500">
                Pricing assumption: {single.view.pricingAssumption ?? "Unavailable"}
              </p>
            </Section>

            <Section
              title="Historical evidence"
              subtitle="Only the backend's archive-backed evidence is shown; nothing is imputed."
            >
              <div className="flex flex-wrap items-center gap-2">
                <StatusPill
                  label={
                    single.view.historical.evidenceStatus === "descriptive_only"
                      ? "DESCRIPTIVE ONLY"
                      : single.view.historical.evidenceStatus === "unavailable"
                        ? "UNAVAILABLE"
                        : "NOT COMPUTED"
                  }
                  variant={single.view.historical.evidenceStatus === "descriptive_only" ? "archive" : "warning"}
                />
                {single.view.historical.provenance && (
                  <span className="font-mono text-[11px] text-terminal-400">
                    provenance: {label(single.view.historical.provenance)}
                  </span>
                )}
              </div>
              <dl className="grid gap-3 font-mono text-xs md:grid-cols-2">
                <div>
                  <dt className="text-terminal-400">Sample size</dt>
                  <dd className="text-terminal-200">
                    {single.view.historical.sampleSize === null
                      ? "Unavailable"
                      : String(single.view.historical.sampleSize)}
                  </dd>
                </div>
                <div>
                  <dt className="text-terminal-400">Capital eligibility</dt>
                  <dd className="text-terminal-200">
                    {label(single.view.historical.capitalStatus)}
                    {single.view.historical.capitalStatus === "not_assessed"
                      ? " (this endpoint does not accept an available-capital budget)"
                      : ""}
                  </dd>
                </div>
                <div className="md:col-span-2">
                  <dt className="text-terminal-400">Temporal basis</dt>
                  <dd className="text-terminal-200">{single.view.historical.temporalBasis ?? "Unavailable"}</dd>
                </div>
                {single.view.historical.missing.length > 0 && (
                  <div className="md:col-span-2">
                    <dt className="text-terminal-400">Missing evidence</dt>
                    <dd>
                      <ul className="mt-1 flex flex-wrap gap-1">
                        {single.view.historical.missing.map((reason) => (
                          <li key={reason} className="rounded border border-terminal-700 px-2 py-0.5 text-[10px] text-terminal-300">
                            {label(reason)}
                          </li>
                        ))}
                      </ul>
                    </dd>
                  </div>
                )}
              </dl>
              {single.view.caveats.length > 0 && (
                <div>
                  <p className="font-mono text-[11px] uppercase tracking-wider text-terminal-400">Backend caveats</p>
                  <ul className="mt-1 space-y-1 font-mono text-[11px] text-terminal-400">
                    {single.view.caveats.map((caveat) => <li key={caveat}>· {caveat}</li>)}
                  </ul>
                </div>
              )}
            </Section>
          </>
        )}

        <Section
          title="Comparison set"
          subtitle={`Saved scenarios are sent to the comparison endpoint in the order shown (up to ${MAX_COMPARE_STRUCTURES}).`}
        >
          {saved.length === 0 ? (
            <p className="font-mono text-xs text-terminal-500">
              No structures saved yet. Build a scenario, then save it for comparison.
            </p>
          ) : (
            <ol className="space-y-2">
              {saved.map((item, index) => (
                <li key={item.id} className="flex flex-wrap items-center justify-between gap-2 rounded border border-terminal-800 bg-terminal-950 p-2">
                  <span className="font-mono text-[11px] text-terminal-200">
                    {index + 1}. {item.label}
                  </span>
                  <button
                    type="button"
                    onClick={() => setSaved((current) => current.filter((row) => row.id !== item.id))}
                    className="rounded border border-terminal-700 px-2 py-1 font-mono text-[10px] text-terminal-400 hover:border-loss hover:text-loss"
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ol>
          )}
          <div className="grid gap-3 md:grid-cols-2">
            <Field id="structure-thesis" label="Optional thesis (recorded context only)">
              <input
                id="structure-thesis"
                className={INPUT}
                placeholder="Why these structures are being compared"
                value={thesis}
                onChange={(event) => setThesis(event.target.value)}
              />
            </Field>
            <div className="flex items-end">
              <button
                type="button"
                onClick={compare}
                disabled={comparison.kind === "loading" || saved.length === 0}
                className="w-full rounded border border-profit/40 bg-profit-bg px-4 py-2 font-mono text-xs font-semibold text-profit hover:border-profit disabled:opacity-40"
              >
                {comparison.kind === "loading" ? "Comparing…" : `Compare saved structures (${saved.length})`}
              </button>
            </div>
          </div>
          <p className="font-mono text-[10px] text-terminal-500">
            Thesis text is recorded by the backend as context; it does not filter or rank results.
          </p>
        </Section>

        {comparison.kind === "error" && (
          <section role="alert" className="rounded border border-loss/40 bg-loss-bg p-4 font-mono text-xs text-loss">
            {comparison.message}
          </section>
        )}

        {comparison.kind === "result" && (
          <Section
            title="Descriptive comparison"
            subtitle={`${comparison.view.order}. No winner, score or recommendation is produced.`}
          >
            {comparison.view.thesis && (
              <p className="font-mono text-[11px] text-terminal-400">Thesis: {comparison.view.thesis}</p>
            )}
            {comparison.view.noCandidate || comparison.view.candidates.length === 0 ? (
              <p className="font-mono text-xs text-terminal-500">
                The backend returned no comparable candidates. Invalid or insufficient inputs are listed below.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse font-mono text-xs">
                  <thead>
                    <tr className="border-b border-terminal-800 text-left text-terminal-400">
                      <th className="py-2 pr-3">#</th>
                      <th className="py-2 pr-3">Family</th>
                      <th className="py-2 pr-3">Capital at risk</th>
                      <th className="py-2 pr-3">Max profit</th>
                      <th className="py-2 pr-3">Max loss</th>
                      <th className="py-2 pr-3">Breakevens</th>
                      <th className="py-2 pr-3">DTE</th>
                      <th className="py-2 pr-3">Historical evidence</th>
                      <th className="py-2">Observed fields</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comparison.view.candidates.map((row) => (
                      <tr key={row.index} className="border-b border-terminal-800/60 align-top text-terminal-200">
                        <td className="py-2 pr-3">{row.index + 1}</td>
                        <td className="py-2 pr-3">{label(row.family)}</td>
                        <td className="py-2 pr-3">{scalarText(row.capital)}</td>
                        <td className="py-2 pr-3">{scalarText(row.maxProfit)}</td>
                        <td className="py-2 pr-3">{scalarText(row.maxLoss)}</td>
                        <td className="py-2 pr-3">
                          {row.breakevens.length ? row.breakevens.map((value) => price(value)).join(" · ") : "Unavailable"}
                        </td>
                        <td className="py-2 pr-3">{row.dte === null ? "Unavailable" : String(row.dte)}</td>
                        <td className="py-2 pr-3">{label(row.historicalStatus)}</td>
                        <td className="py-2">
                          {row.observedEvidence.length
                            ? row.observedEvidence.join(", ")
                            : "none (supplied scenario)"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {comparison.view.excluded.length > 0 && (
              <div>
                <p className="font-mono text-[11px] uppercase tracking-wider text-warning">Excluded by the backend</p>
                <ul className="mt-1 space-y-1 font-mono text-[11px] text-terminal-300">
                  {comparison.view.excluded.map((item) => (
                    <li key={item.index}>· #{item.index + 1}: {label(item.reason)}</li>
                  ))}
                </ul>
              </div>
            )}

            {comparison.view.groups.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse font-mono text-xs">
                  <caption className="pb-2 text-left font-mono text-[11px] text-terminal-500">
                    Candidates share historical evidence only within a group; same evidence is not a preference.
                  </caption>
                  <thead>
                    <tr className="border-b border-terminal-800 text-left text-terminal-400">
                      <th className="py-2 pr-3">Group</th>
                      <th className="py-2 pr-3">Candidates</th>
                      <th className="py-2 pr-3">Directly comparable</th>
                      <th className="py-2">Missing evidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comparison.view.groups.map((group) => (
                      <tr key={group.groupId} className="border-b border-terminal-800/60 text-terminal-200">
                        <td className="py-2 pr-3">{group.groupId}</td>
                        <td className="py-2 pr-3">{group.indices.map((index) => `#${index + 1}`).join(", ")}</td>
                        <td className="py-2 pr-3">{group.directlyComparable ? "Yes" : "No"}</td>
                        <td className="py-2">
                          {group.missing.length ? group.missing.map(label).join(", ") : "none"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {comparison.view.pairs.length > 0 && (
              <ul className="space-y-1 font-mono text-[11px] text-terminal-400">
                {comparison.view.pairs.map((pair) => (
                  <li key={pair.indices.join("-")}>
                    · #{pair.indices[0] + 1} vs #{pair.indices[1] + 1}:{" "}
                    {pair.comparable ? "directly comparable" : `not comparable (${label(pair.reason)})`}
                  </li>
                ))}
              </ul>
            )}

            {comparison.view.caveats.length > 0 && (
              <ul className="space-y-1 font-mono text-[11px] text-terminal-400">
                {comparison.view.caveats.map((caveat) => <li key={caveat}>· {caveat}</li>)}
              </ul>
            )}
          </Section>
        )}
      </div>
    </div>
  );
}
