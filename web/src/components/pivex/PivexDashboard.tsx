"use client";
import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { Header } from "@/components/shell/Header";
import {
  instruments,
  validateEvidence,
  ManualHistoricalAdapter,
} from "@/lib/pivex/evidence";
import { analyze } from "@/lib/pivex/strategy";
import type { Setup } from "@/lib/pivex/strategy";
import {
  defaultRules,
  policy,
  riskState,
  validateRules,
  validateSnapshot,
  day,
  weekStart,
} from "@/lib/pivex/challenge";
import { plan, validateSpec } from "@/lib/pivex/planner";
import {
  loadLedger,
  saveLedger,
  validateLedger,
  validateTrade,
  performance,
  net,
  storageKey,
} from "@/lib/pivex/journal";
import type { Ledger } from "@/lib/pivex/journal";
import { fixture } from "@/lib/pivex/fixtures";

const box = "rounded border border-terminal-800 bg-terminal-900 p-5 space-y-4";
const input =
  "w-full rounded border border-terminal-700 bg-terminal-950 px-3 py-2 text-terminal-100 focus:outline-profit";
const button =
  "rounded border border-terminal-600 bg-terminal-850 px-3 py-2 text-terminal-100 hover:border-profit disabled:opacity-40";
const money = (n: number | null | undefined) =>
  n == null
    ? "Unable to verify"
    : new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
      }).format(n);
const number = (n: number | null | undefined) =>
  n == null ? "—" : n.toFixed(2);
const pct = (n: number | null | undefined) =>
  n == null ? "Unable to verify" : `${(n * 100).toFixed(1)}%`;
const empty = (): Ledger => ({
  schema: 1,
  rules: [{ ...defaultRules }],
  snapshot: null,
  trades: [],
  specs: [],
});
function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-label={title} className={box}>
      <h2 className="text-base font-bold text-terminal-100">{title}</h2>
      {children}
    </section>
  );
}
function Field({
  name,
  label,
  type = "number",
  value,
}: {
  name: string;
  label: string;
  type?: string;
  value?: string | number;
}) {
  return (
    <label className="block space-y-1 text-terminal-400">
      {label}
      <input
        className={input}
        name={name}
        type={type}
        step={type === "number" ? "any" : undefined}
        defaultValue={value}
        required
      />
    </label>
  );
}
function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-terminal-800 bg-terminal-950 p-3">
      <dt className="text-terminal-400">{label}</dt>
      <dd className="mt-2 text-sm text-terminal-100">{value}</dd>
    </div>
  );
}
const specTemplate = {
  instrument: "NAS100",
  brokerSymbol: "",
  source: "",
  verifiedAt: "",
  attested: false,
  tickSize: 0,
  tickValue: 0,
  quoteToAccount: 0,
  minLot: 0,
  maxLot: 0,
  lotStep: 0,
  spreadTicks: 0,
  slippageTicks: 0,
  commissionPerLot: 0,
  fixedFees: 0,
  costsSource: "",
  marketHours: "",
  permitted: false,
};
export function PivexDashboard() {
  const storedRaw = useRef<string | null>(null);
  const [ledger, setLedger] = useState<Ledger>(empty),
    [profile, setProfile] = useState("challenge-1"),
    [profileDraft, setProfileDraft] = useState("challenge-1");
  const [ready, setReady] = useState(false),
    [notice, setNotice] = useState(""),
    [now, setNow] = useState("");
  const [evidenceText, setEvidenceText] = useState(""),
    [setup, setSetup] = useState<Setup | null>(null);
  const [specText, setSpecText] = useState(
      JSON.stringify(specTemplate, null, 2),
    ),
    [rulesText, setRulesText] = useState(
      JSON.stringify({ ...defaultRules, version: "" }, null, 2),
    ),
    [backup, setBackup] = useState("");
  const [instrument, setInstrument] = useState("NAS100"),
    [prices, setPrices] = useState({
      entry: "",
      stop: "",
      target: "",
      budget: "25",
    });
  useEffect(() => {
    try {
      setLedger(loadLedger(localStorage, "challenge-1") ?? empty());
      storedRaw.current = localStorage.getItem(storageKey("challenge-1"));
      setReady(true);
    } catch {
      setNotice(
        "Local storage unavailable or invalid. Export/recover the existing record before writing; no records overwritten.",
      );
    }
    setNow(new Date().toISOString());
    const timer = setInterval(() => setNow(new Date().toISOString()), 30000);
    return () => clearInterval(timer);
  }, []);
  function attempt(action: () => void) {
    try {
      action();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Unable to save");
    }
  }
  function commit(next: Ledger) {
    if (!ready) throw Error("Local storage is not ready");
    if (localStorage.getItem(storageKey(profile)) !== storedRaw.current)
      throw Error(
        "This challenge changed in another tab. Reopen it before saving to prevent lost records.",
      );
    if (next.trades.some((t) => Date.parse(t.exitTime) > Date.now()))
      throw Error("Closed trades cannot have future exit times");
    saveLedger(localStorage, profile, next);
    storedRaw.current = localStorage.getItem(storageKey(profile));
    setLedger(next);
    setNotice("Saved in this browser only. Export a backup to retain a copy.");
  }
  const rules = ledger.rules.at(-1)!,
    snapshot = ledger.snapshot,
    stats = performance(ledger.trades),
    risk = riskState(snapshot, rules, now);
  const spec = ledger.specs.find((s) => s.instrument === instrument) ?? null;
  const modeled = plan({
    entry: Number(prices.entry),
    stop: Number(prices.stop),
    target: Number(prices.target),
    budget: Number(prices.budget),
    spec,
    snapshot,
    rules,
    now,
  });
  function snapshotSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    attempt(() => {
      const n = (k: string) => {
        const v = f.get(k);
        if (v === null || v === "") throw Error(`Missing ${k}`);
        return Number(v);
      };
      const s = validateSnapshot({
        asOf: f.get("asOf"),
        source: f.get("source"),
        attested: f.get("attested") === "on",
        equity: n("equity"),
        realizedPnl: n("realizedPnl"),
        floatingPnl: n("floatingPnl"),
        fees: n("fees"),
        exposure: n("exposure"),
        openRisk: n("openRisk"),
        dailyBaseline: { at: f.get("dailyAt"), equity: n("dailyEquity") },
        weeklyBaseline: { at: f.get("weeklyAt"), equity: n("weeklyEquity") },
        tradesToday: n("tradesToday"),
        lossesToday: n("lossesToday"),
      });
      commit({ ...ledger, snapshot: s });
    });
  }
  function tradeSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget,
      f = new FormData(form);
    attempt(() => {
      const t = validateTrade({
        ...Object.fromEntries(f.entries()),
        id: crypto.randomUUID(),
        ruleVersion: rules.version,
        ...Object.fromEntries(
          [
            "entry",
            "exit",
            "stop",
            "target",
            "size",
            "fees",
            "otherCosts",
            "realizedPnl",
            "initialRisk",
          ].map((k) => [k, Number(f.get(k))]),
        ),
      });
      // A newly recorded trade invalidates the pre-trade account snapshot until reconfirmed.
      commit({ ...ledger, trades: [...ledger.trades, t], snapshot: null });
      form.reset();
    });
  }
  function exportBackup() {
    const blob = new Blob([JSON.stringify(ledger, null, 2)], {
        type: "application/json",
      }),
      url = URL.createObjectURL(blob),
      a = document.createElement("a");
    a.href = url;
    a.download = `pivex-${profile}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }
  async function analyzeManual() {
    try {
      if (evidenceText.length > 5000000)
        throw Error("Market evidence exceeds 5 MB");
      const e = validateEvidence(JSON.parse(evidenceText));
      const adapter = new ManualHistoricalAdapter(e);
      setSetup(analyze(await adapter.load(e.instrument, e.asOf)));
    } catch (e) {
      setSetup(null);
      setNotice(e instanceof Error ? e.message : "Invalid manual evidence");
    }
  }
  return (
    <div>
      <Header
        title="Pivex Challenge"
        subtitle="Independent strategy research · Manual challenge tracking"
        badge={{
          label: "MANUAL / HISTORICAL — NO LIVE FEED",
          variant: "warning",
        }}
      />
      <div className="p-4 md:p-8 space-y-6 font-mono text-xs max-w-[1600px] mx-auto w-full">
        <div className="rounded border border-amber-700/50 bg-amber-950/20 p-4 text-amber-200 space-y-2">
          <p>
            Research and simulation only. No broker connection or trade
            execution. NAS100 and XAUUSD live research are disabled pending
            verified specifications and licensed data coverage.
          </p>
          <p>
            Local journal: saved on this browser and origin only, separate from
            options and Robinhood. Challenge labels separate records; they are
            not user identities or access controls. Anyone with this browser
            profile can access them. No cloud sync.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="space-y-1">
            Local challenge label
            <input
              aria-label="Local challenge label"
              className={input}
              value={profileDraft}
              onChange={(e) => setProfileDraft(e.target.value)}
            />
          </label>
          <button
            className={button}
            onClick={() =>
              attempt(() => {
                const next = loadLedger(localStorage, profileDraft) ?? empty();
                setLedger(next);
                storedRaw.current = localStorage.getItem(
                  storageKey(profileDraft),
                );
                setProfile(profileDraft);
                setReady(true);
                setNotice("Opened browser-local challenge");
              })
            }
          >
            Open challenge
          </button>
          <span className="text-terminal-400">Active: {profile}</span>
          <button className={button} disabled={!ready} onClick={exportBackup}>
            Export backup
          </button>
        </div>
        <p role="status" aria-live="polite" className="text-amber-200 min-h-4">
          {notice}
        </p>
        <Section title="Challenge Overview">
          <dl className="grid grid-cols-2 xl:grid-cols-4 gap-3">
            <Metric
              label="Configured starting balance"
              value={money(rules.startingBalance)}
            />
            <Metric
              label="Profit target"
              value={`${pct(rules.profitTarget)} / ${money(rules.startingBalance * rules.profitTarget)}`}
            />
            <Metric
              label="Target balance"
              value={money(rules.startingBalance * (1 + rules.profitTarget))}
            />
            <Metric
              label="Overall equity floor"
              value={money(risk.overallFloor)}
            />
          </dl>
          <p className="text-terminal-400">
            Daily drawdown: {pct(rules.dailyDrawdown)} of 00:00 UTC equity ·
            Overall: {pct(rules.overallDrawdown)} of original balance · Minimum{" "}
            {rules.minDays} trading days · Largest profitable day ≤{" "}
            {pct(rules.consistency)} of total net realized profit.
          </p>
          <p>
            No fixed completion deadline by default; active plan, inactivity
            rules and stage must be confirmed. Current stage: {rules.stage}.
            Rule version: {rules.version}.
          </p>
          <details>
            <summary className="cursor-pointer text-profit">
              Rule provenance and configuration ({ledger.rules.length} versions)
            </summary>
            <div className="space-y-3 mt-3">
              <p>
                {rules.source} Reviewed: {rules.reviewedAt}. Agreement:{" "}
                {rules.agreementStatus}.
              </p>
              <p className="text-amber-200">
                Official compliance: Unable to verify. Public terms differ from
                help-center wording on consistency and the daily baseline. An
                attestation records your review; it does not verify platform
                compliance or intraday equity history.
              </p>
              <ul className="list-disc pl-5 space-y-1">
                <li>
                  <a
                    className="underline"
                    href="https://help.pivex.com/en/support/solutions/articles/156000324695-what-are-the-drawdown-rules-at-pivex-"
                  >
                    Drawdown guidance
                  </a>
                </li>
                <li>
                  <a
                    className="underline"
                    href="https://help.pivex.com/en/support/solutions/articles/156000324708-what-is-a-consistency-rule-and-when-does-it-apply-"
                  >
                    Day-based consistency guidance
                  </a>
                </li>
                <li>
                  <a
                    className="underline"
                    href="https://help.pivex.com/en/support/solutions/articles/156000322627-what-are-the-restricted-and-prohibited-trading-strategies-at-pivex-"
                  >
                    News and prohibited strategies
                  </a>
                </li>
                <li>
                  <a
                    className="underline"
                    href="https://help.pivex.com/en/support/solutions/articles/156000390426-is-high-frequency-trading-or-copy-trading-allowed-at-pivex-"
                  >
                    HFT and copying guidance
                  </a>
                </li>
                <li>
                  <a
                    className="underline"
                    href="https://legal.pivexfunded.com/terms"
                  >
                    Legal terms, sections 7–8
                  </a>
                </li>
              </ul>
              <p>
                Public-source review: 10 November 2026. Stop loss required by
                guidance. Review prohibited latency/arbitrage, grid, stacking,
                copying and unauthorized automation. Help guidance allows
                challenge news trading and describes a ±5-minute high-impact
                news window in the funded stage. It flags sub-30-second trades
                as HFT, with profit-share conditions; this is not a universal
                30-second minimum-hold permission. Martingale, hedging
                permissions, stage differences and plan add-ons require the
                active agreement. No automated interpretation grants permission.
              </p>
              <label className="block">
                New rule version (JSON)
                <textarea
                  className={`${input} h-64 mt-2`}
                  value={rulesText}
                  onChange={(e) => setRulesText(e.target.value)}
                />
              </label>
              <button
                disabled={!ready}
                className={button}
                onClick={() =>
                  attempt(() => {
                    const r = validateRules(JSON.parse(rulesText));
                    if (ledger.rules.some((v) => v.version === r.version))
                      throw Error(
                        "Use a new rule version; prior provenance is immutable",
                      );
                    commit({
                      ...ledger,
                      rules: [...ledger.rules, r],
                      snapshot: null,
                    });
                  })
                }
              >
                Append rule version
              </button>
              <pre className="overflow-auto max-h-40 text-terminal-400">
                {JSON.stringify(ledger.rules, null, 2)}
              </pre>
            </div>
          </details>
        </Section>
        <Section title="Market Setup Scanner">
          <div className="grid md:grid-cols-2 gap-3">
            {instruments.map((i) => (
              <div
                key={i.id}
                className="border border-terminal-800 rounded p-4 space-y-2"
              >
                <h3 className="font-bold">
                  {i.id} · {i.name}
                </h3>
                <p className="text-amber-200">LIVE RESEARCH DISABLED</p>
                <p className="text-terminal-400">
                  Awaiting: {i.missing.join(", ")}. No QQQ proxy.
                </p>
              </div>
            ))}
          </div>
          <p>
            Import timestamped manual/historical candle evidence as JSON, or
            explicitly load a synthetic fixture. Fixtures never populate
            balances, journal or performance.
          </p>
          <div className="flex flex-wrap gap-2">
            {(["long", "short", "chop"] as const).map((d) => (
              <button
                className={button}
                key={d}
                onClick={() => {
                  setEvidenceText(JSON.stringify(fixture(d), null, 2));
                  setSetup(null);
                }}
              >
                Load synthetic {d}
              </button>
            ))}
          </div>
          <details>
            <summary className="cursor-pointer text-profit">
              Candle evidence editor
            </summary>
            <label className="block mt-3">
              Market evidence JSON
              <textarea
                className={`${input} h-64 mt-2`}
                value={evidenceText}
                onChange={(e) => {
                  setEvidenceText(e.target.value);
                  setSetup(null);
                }}
              />
            </label>
          </details>
          <button className={button} onClick={analyzeManual}>
            Analyze completed candles
          </button>
          <div
            aria-live="polite"
            className="border border-terminal-700 rounded p-4 space-y-2"
          >
            <h3 className="font-bold text-profit">
              {setup?.status ?? "UNAVAILABLE — no market evidence loaded"}
            </h3>
            <p>
              {setup?.reason ??
                "Provide completed 1-hour, 15-minute and 5-minute candles with UTC timestamps, source and a pre-existing target."}
            </p>
            {setup?.evidence && (
              <>
                <p className="text-amber-200">
                  {setup.evidence.mode.toUpperCase()} · {setup.evidence.source}{" "}
                  · As of {setup.evidence.asOf}
                </p>
                <p>
                  Direction: {setup.direction} · Entry reference:{" "}
                  {setup.entryReference} · Stop: {setup.stop} · Initial 2R
                  target: {setup.target}. No fill assumed.
                </p>
                <details>
                  <summary>Reproducible evidence</summary>
                  <pre className="overflow-auto max-h-64">
                    {JSON.stringify(setup, null, 2)}
                  </pre>
                </details>
              </>
            )}
          </div>
        </Section>
        <Section title="Trade Planner">
          <p>
            Instrument-specific costs and USD account sizing. A modeled size is
            not a qualified setup or permission to trade.
          </p>
          <div className="grid sm:grid-cols-2 xl:grid-cols-5 gap-3">
            <label>
              Instrument
              <select
                aria-label="Planner instrument"
                className={input}
                value={instrument}
                onChange={(e) => setInstrument(e.target.value)}
              >
                {instruments.map((i) => (
                  <option key={i.id}>{i.id}</option>
                ))}
              </select>
            </label>
            {Object.entries(prices).map(([k, v]) => (
              <label key={k}>
                {
                  (
                    {
                      entry: "Entry price",
                      stop: "Stop price",
                      target: "Target price",
                      budget: "Available risk budget",
                    } as Record<string, string>
                  )[k]
                }
                <input
                  className={input}
                  type="number"
                  step="any"
                  value={v}
                  onChange={(e) =>
                    setPrices({ ...prices, [k]: e.target.value })
                  }
                />
              </label>
            ))}
          </div>
          <details>
            <summary className="cursor-pointer text-profit">
              Contract specifications and costs:{" "}
              {spec ? "manual attestation on file" : "missing"}
            </summary>
            <div className="mt-3 space-y-3">
              <p>
                Enter actual broker symbol, tick value per lot in quote
                currency, quote-to-USD conversion, min/max lots and step. Spread
                and slippage are round-trip ticks; commissions per lot and fixed
                fees are round-trip USD. Zero costs require explicit evidence.
                Specifications expire for sizing after 24 hours. Manual
                attestation does not enable a live feed.
              </p>
              <label className="block">
                Contract specification JSON
                <textarea
                  className={`${input} h-64 mt-2`}
                  value={specText}
                  onChange={(e) => setSpecText(e.target.value)}
                />
              </label>
              <button
                disabled={!ready}
                className={button}
                onClick={() =>
                  attempt(() => {
                    const s = validateSpec(JSON.parse(specText));
                    commit({
                      ...ledger,
                      specs: [
                        ...ledger.specs.filter(
                          (v) => v.instrument !== s.instrument,
                        ),
                        s,
                      ],
                    });
                  })
                }
              >
                Save attested specifications
              </button>
              {spec && (
                <pre className="overflow-auto max-h-64">
                  {JSON.stringify(spec, null, 2)}
                </pre>
              )}
            </div>
          </details>
          <div
            className="border border-amber-800 rounded p-4 space-y-3"
            aria-live="polite"
          >
            <h3 className="font-bold text-amber-200">{modeled.status}</h3>
            <p>{modeled.reason}</p>
            <dl className="grid grid-cols-2 xl:grid-cols-4 gap-3">
              <Metric
                label="Proposed lots"
                value={modeled.size == null ? "—" : String(modeled.size)}
              />
              <Metric
                label="Maximum modeled loss"
                value={money(modeled.loss)}
              />
              <Metric
                label="Potential net target profit"
                value={money(modeled.profit)}
              />
              <Metric label="Net reward / risk" value={number(modeled.rr)} />
              <Metric label="Direction" value={modeled.direction ?? "—"} />
              <Metric
                label="Distance to stop"
                value={number(modeled.distance)}
              />
              <Metric
                label="Account equity for sizing"
                value={money(risk.verified ? snapshot?.equity : null)}
              />
              <Metric
                label="Setup qualification"
                value="Independent evidence required"
              />
            </dl>
          </div>
          <p className="text-terminal-400">
            No averaging down, no widening stops, no forced entries. A 2R gross
            strategy target may fail the net 2:1 requirement after costs.
          </p>
        </Section>
        <Section title="Risk Management">
          <p className="text-amber-200">
            Official rule compliance: Unable to verify. Current manual snapshot
            checks cannot establish continuous equity compliance. Platform
            marks, gaps and execution costs may differ.
          </p>
          <dl className="grid grid-cols-2 xl:grid-cols-4 gap-3">
            <Metric
              label="Current attested equity"
              value={money(risk.verified ? snapshot?.equity : null)}
            />
            <Metric
              label="Gross realized P&L (snapshot)"
              value={money(snapshot?.realizedPnl)}
            />
            <Metric
              label="Floating P&L (snapshot)"
              value={money(snapshot?.floatingPnl)}
            />
            <Metric
              label="Fees paid (snapshot)"
              value={money(snapshot?.fees)}
            />
            <Metric
              label="Open exposure (USD notional)"
              value={money(snapshot?.exposure)}
            />
            <Metric
              label="Remaining realized profit target"
              value={money(risk.remainingTarget)}
            />
            <Metric
              label="Daily drawdown headroom"
              value={money(risk.dailyHeadroom)}
            />
            <Metric
              label="Overall drawdown headroom"
              value={money(risk.overallHeadroom)}
            />
            <Metric
              label="Personal daily risk remaining"
              value={money(
                risk.dailyAllowance == null
                  ? null
                  : Math.max(
                      0,
                      risk.dailyAllowance - (snapshot?.openRisk ?? 0),
                    ),
              )}
            />
            <Metric
              label="Open-position planned risk"
              value={money(snapshot?.openRisk)}
            />
            <Metric
              label="Trading days (local journal)"
              value={`${stats.tradingDays} / ${rules.minDays}`}
            />
            <Metric
              label="Largest profitable day (journal)"
              value={money(stats.largestDay)}
            />
            <Metric
              label="Consistency (local net profit)"
              value={pct(stats.consistency)}
            />
          </dl>
          <p>
            Internal policy, separate from official rules: ${policy.tradeRisk}
            /trade and ${policy.aggregateRisk} aggregate planned risk; −$
            {policy.dailyLoss}/day; −${policy.weeklyLoss}/week;{" "}
            {policy.tradesPerDay} trades/day; stop after{" "}
            {policy.losingTradesPerDay} losing trades/day. Profits do not expand
            personal loss budgets.
          </p>
          {snapshot && (
            <p className="text-terminal-400">
              User-attested source: {snapshot.source} · As of {snapshot.asOf}.
              Reconfirm within 15 minutes and after each journal entry; UTC
              baselines must be entered explicitly.
            </p>
          )}
          <p className="text-amber-200">
            {risk.reasons.join("; ") ||
              "Current modeled snapshot within configured limits; historical compliance remains unverified."}
            {risk.verified &&
            ((risk.dailyHeadroom ?? 0) < 100 ||
              (risk.overallHeadroom ?? 0) < 100 ||
              (risk.dailyAllowance ?? 0) < 25)
              ? " WARNING — approaching risk limit."
              : ""}
            {stats.consistency != null && stats.consistency > rules.consistency
              ? " Consistency limit exceeded in local journal."
              : ""}
          </p>
          <details>
            <summary className="cursor-pointer text-profit">
              Record verified user account entry
            </summary>
            <form onSubmit={snapshotSubmit} className="space-y-4 mt-4">
              <p>
                Copy all values from your account statement. Equity is entered
                independently, not calculated from closed profits. Gross
                realized P&L and fees are cumulative; equity includes floating
                P&L and fees. Baselines are exact 00:00 UTC observations, not
                estimates from realized P&L. Weekly baseline is Monday 00:00
                UTC.
              </p>
              <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3">
                <Field
                  name="source"
                  label="Account evidence reference"
                  type="text"
                />
                <Field
                  name="asOf"
                  label="Account observation time (UTC ISO)"
                  type="text"
                  value={now}
                />
                {[
                  ["equity", "Verified equity USD"],
                  ["realizedPnl", "Gross realized P&L USD"],
                  ["floatingPnl", "Floating P&L USD"],
                  ["fees", "Cumulative fees USD"],
                  ["exposure", "Open exposure USD"],
                  ["openRisk", "Open planned risk USD"],
                  ["dailyEquity", "00:00 UTC equity USD"],
                  ["weeklyEquity", "Monday 00:00 UTC equity USD"],
                  ["tradesToday", "Trades opened today"],
                  ["lossesToday", "Losing trades today"],
                ].map(([name, label]) => (
                  <Field key={name} name={name} label={label} />
                ))}
                <Field
                  name="dailyAt"
                  label="Daily baseline timestamp"
                  type="text"
                  value={now ? `${day(now)}T00:00:00Z` : ""}
                />
                <Field
                  name="weeklyAt"
                  label="Weekly baseline timestamp"
                  type="text"
                  value={now ? weekStart(now) : ""}
                />
              </div>
              <label className="flex gap-2 items-start">
                <input name="attested" type="checkbox" required />I verified
                these entries, UTC baselines, costs, open risk and complete
                daily trade counts against my account.
              </label>
              <button className={button} disabled={!ready}>
                Save account observation
              </button>
            </form>
          </details>
        </Section>
        <Section title="Challenge Journal">
          <p>
            Manual closed trades only. Enter gross realized P&L; fees and other
            costs are subtracted once. Open positions belong in the account
            observation. No sample history.
          </p>
          <form onSubmit={tradeSubmit} className="space-y-4">
            <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-3">
              <label>
                Journal instrument
                <select className={input} name="instrument">
                  {instruments.map((i) => (
                    <option key={i.id}>{i.id}</option>
                  ))}
                </select>
              </label>
              <label>
                Direction
                <select className={input} name="direction">
                  <option value="long">Long</option>
                  <option value="short">Short</option>
                </select>
              </label>
              <Field name="entryTime" label="Entry time UTC ISO" type="text" />
              <Field name="exitTime" label="Exit time UTC ISO" type="text" />
              {[
                ["entry", "Journal entry price"],
                ["exit", "Exit price"],
                ["stop", "Initial stop price"],
                ["target", "Initial target price"],
                ["size", "Position size lots"],
                ["fees", "Trade fees USD"],
                ["otherCosts", "Other costs USD"],
                ["realizedPnl", "Trade gross realized P&L USD"],
                ["initialRisk", "Initial planned risk USD"],
              ].map(([name, label]) => (
                <Field key={name} name={name} label={label} />
              ))}
              <Field name="setup" label="Setup classification" type="text" />
              <label>
                Rule adherence
                <select className={input} name="adherence">
                  <option value="unknown">Unknown</option>
                  <option value="adhered">Adhered (user attested)</option>
                  <option value="breach">Breach</option>
                </select>
              </label>
              <Field name="exitReason" label="Exit reason" type="text" />
              <Field
                name="source"
                label="Trade evidence reference"
                type="text"
              />
            </div>
            <button className={button} disabled={!ready}>
              Record closed trade
            </button>
          </form>
          <div className="overflow-x-auto">
            <table className="w-full text-left whitespace-nowrap">
              <caption className="text-left py-3 text-terminal-400">
                {ledger.trades.length} manually recorded trades · Each record
                retains evidence, stops, targets and costs in the backup.
              </caption>
              <thead className="border-b border-terminal-700">
                <tr>
                  {[
                    "Instrument / direction",
                    "Entry / exit UTC",
                    "Prices / size",
                    "Stop / target",
                    "Net P&L",
                    "Realized R",
                    "Setup / adherence",
                    "Exit reason",
                  ].map((h) => (
                    <th className="p-2" key={h}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ledger.trades.map((t) => (
                  <tr key={t.id} className="border-b border-terminal-800">
                    <td className="p-2">
                      {t.instrument} / {t.direction}
                    </td>
                    <td className="p-2">
                      {t.entryTime}
                      <br />
                      {t.exitTime}
                    </td>
                    <td className="p-2">
                      {t.entry} / {t.exit} / {t.size}
                    </td>
                    <td className="p-2">
                      {t.stop} / {t.target}
                    </td>
                    <td className="p-2">{money(net(t))}</td>
                    <td className="p-2">{number(net(t) / t.initialRisk)}R</td>
                    <td className="p-2">
                      {t.setup} / {t.adherence}
                    </td>
                    <td className="p-2">{t.exitReason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <details>
            <summary className="cursor-pointer text-profit">
              Restore or import supported Pivex JSON backup
            </summary>
            <div className="mt-3 space-y-3">
              <p>
                Only schema 1 Pivex backups are supported (maximum 5 MB). Import
                replaces this local challenge, including rules and manual
                observations. Export the current record first.
              </p>
              <label className="block">
                Pivex backup JSON
                <textarea
                  className={`${input} h-40 mt-2`}
                  value={backup}
                  onChange={(e) => setBackup(e.target.value)}
                />
              </label>
              <button
                disabled={!ready}
                className={button}
                onClick={() =>
                  attempt(() => {
                    if (backup.length > 5000000)
                      throw Error("Backup exceeds 5 MB");
                    commit(validateLedger(JSON.parse(backup)));
                  })
                }
              >
                Import backup and replace local challenge
              </button>
            </div>
          </details>
        </Section>
        <Section title="Strategy Performance">
          <p>
            Local manual journal only; not a verified complete account record.
            Closed-trade drawdown excludes floating losses and cannot establish
            challenge compliance.
          </p>
          <dl className="grid grid-cols-2 xl:grid-cols-4 gap-3">
            <Metric label="Win rate" value={pct(stats.winRate)} />
            <Metric label="Average win" value={money(stats.averageWin)} />
            <Metric label="Average loss" value={money(stats.averageLoss)} />
            <Metric
              label="Profit factor"
              value={
                stats.profitFactor == null
                  ? "Unavailable (no losses)"
                  : number(stats.profitFactor)
              }
            />
            <Metric label="Average R" value={number(stats.averageR)} />
            <Metric label="Expectancy in R" value={number(stats.expectancyR)} />
            <Metric
              label="Observed closed-trade drawdown"
              value={money(stats.maxDrawdown)}
            />
            <Metric
              label="Net realized journal P&L"
              value={stats.count ? money(stats.net) : "No trades recorded"}
            />
          </dl>
          {[
            ["Instrument", stats.byInstrument],
            ["Setup", stats.bySetup],
            ["UTC session", stats.bySession],
          ].map(([label, groups]) => (
            <div key={String(label)} className="overflow-x-auto">
              <h3 className="font-bold mb-2">
                Results by {String(label).toLowerCase()}
              </h3>
              {!Object.keys(groups).length ? (
                <p className="text-terminal-400">No recorded history.</p>
              ) : (
                <table className="w-full text-left">
                  <thead>
                    <tr>
                      <th>{String(label)}</th>
                      <th>Trades</th>
                      <th>Net USD</th>
                      <th>Win rate</th>
                      <th>Average R</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(groups).map(([key, g]) => (
                      <tr key={key}>
                        <td className="py-2">{key}</td>
                        <td>{g.count}</td>
                        <td>{money(g.net)}</td>
                        <td>{pct(g.winRate)}</td>
                        <td>{number(g.averageR)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          ))}
        </Section>
      </div>
    </div>
  );
}
