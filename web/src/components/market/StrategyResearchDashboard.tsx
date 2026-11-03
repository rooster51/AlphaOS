"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import { Activity, ChevronDown, CircleAlert, ExternalLink, ShieldCheck } from "lucide-react";
import { Header } from "@/components/shell/Header";
import { StatusPill } from "@/components/shell/StatusPill";
import { archiveExpirations, buyingPower, record } from "@/lib/market-candidates";
import {
  archiveVerificationReason,
  assessStrategyCandidates,
  type OpportunityAssessment,
} from "@/lib/strategy-opportunities";

type MarketSymbol = "SPY" | "QQQ";
type ResearchMode = "current" | "historical";
type DashboardQuery = {
  symbol: MarketSymbol;
  available_capital: number;
  research_mode: ResearchMode;
  expiration?: string;
  width?: number;
};
type ResearchBundle = {
  archive: Record<string, unknown>;
  session: Record<string, unknown>;
  mode: ResearchMode;
  asOf: string;
  caveats: string[];
};
type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "result"; bundle: ResearchBundle; query: DashboardQuery };

const ERROR_MESSAGES: Record<string, string> = {
  backend_not_configured: "The authenticated research backend is not configured.",
  invalid_backend_configuration: "The research backend configuration is invalid.",
  backend_authentication_required: "The backend requires an API token that was not accepted.",
  backend_authentication_rejected: "The backend rejected its configured API token.",
  archive_not_configured: "The verified options archive is not configured.",
  archive_missing: "No verified options archive is available for this symbol.",
  archive_stale: "The latest verified archive is stale. No older snapshot or live data was substituted.",
  archive_unavailable: "Verified archive evidence is unavailable or could not be validated.",
  archive_research_unavailable: "The archive could not be processed as research evidence.",
  archive_expiration_unavailable: "The selected expiration is not in the verified archive. No other expiration was substituted.",
  backend_rejected_request: "The backend rejected the research request.",
  response_schema_mismatch: "The backend response did not match the verified research schema.",
  backend_timeout: "The research request timed out. No substitute data was displayed.",
  backend_unreachable: "The research backend could not be reached.",
};

function parseBundle(
  value: unknown,
  query: DashboardQuery,
): ResearchBundle | null {
  const outer = record(value);
  const envelope = record(outer.research);
  const request = record(envelope.request);
  const research = record(envelope.research);
  const archive = record(research.archive);
  const session = record(research.research_session);
  const mode = query.research_mode;

  if (
    outer.verified_for_trading !== false ||
    envelope.schema_version !== "alphaos-interface-v2" ||
    envelope.read_only !== true ||
    request.symbol !== query.symbol ||
    request.research_mode !== mode ||
    request.expiration !== (query.expiration ?? null) ||
    request.width !== (query.width ?? null) ||
    research.symbol !== query.symbol ||
    research.research_mode !== mode ||
    typeof research.as_of !== "string" ||
    !record(envelope.provenance) ||
    !Array.isArray(envelope.caveats) ||
    !archive.observation ||
    !archive.freshness ||
    !archive.storage ||
    session.symbol !== query.symbol ||
    session.available_capital !== query.available_capital ||
    session.expiration !== research.expiration ||
    !Array.isArray(session.candidates) ||
    !Array.isArray(session.excluded) ||
    !Array.isArray(session.unavailable_routes) ||
    (session.status !== "complete" && session.status !== "no_candidate")
  ) {
    return null;
  }

  return {
    archive,
    session,
    mode,
    asOf: research.as_of,
    caveats: envelope.caveats.filter(
      (item): item is string => typeof item === "string" && item.trim().length > 0,
    ),
  };
}

function formatMoney(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString("en-US", {
        style: "currency",
        currency: "USD",
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })
    : "Unavailable";
}

function formatMaximumProfit(value: unknown): string {
  return value === "unlimited" ? "Unlimited" : formatMoney(value);
}

function formatLabel(value: unknown): string {
  return typeof value === "string" && value.trim()
    ? value.replaceAll("_", " ")
    : "Unavailable";
}

function familyLabel(value: unknown): string {
  const labels: Record<string, string> = {
    long_call: "Long call",
    long_put: "Long put",
    call_debit_spread: "Call debit spread",
    put_debit_spread: "Put debit spread",
    put_credit_spread: "Put credit spread",
    call_credit_spread: "Call credit spread",
    iron_condor: "Iron condor",
    butterfly: "Butterfly",
    bullish_bwb: "Bullish broken-wing butterfly",
    bearish_bwb: "Bearish broken-wing butterfly",
  };
  const key = typeof value === "string" ? value : "";
  return labels[key] ?? formatLabel(key);
}

function candidateKey(assessment: OpportunityAssessment, index: number): string {
  const candidate = assessment.candidate as Record<string, unknown>;
  const inputIndex = candidate.input_index;
  return typeof inputIndex === "number" || typeof inputIndex === "string"
    ? String(inputIndex)
    : String(index);
}

function riskReward(research: Record<string, unknown>): string {
  const provided = research.risk_reward_ratio;
  if (typeof provided === "number" && Number.isFinite(provided) && provided >= 0) {
    return `1 : ${provided.toFixed(2)}`;
  }
  const loss = research.max_loss;
  const profit = research.max_profit;
  if (typeof loss !== "number" || !Number.isFinite(loss) || loss <= 0) return "Unavailable";
  if (profit === "unlimited") return "1 : Unlimited";
  if (typeof profit !== "number" || !Number.isFinite(profit) || profit < 0) return "Unavailable";
  return `1 : ${(profit / loss).toFixed(2)}`;
}

function Metric({
  label,
  value,
  accent = false,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="min-w-0 rounded border border-terminal-800 bg-terminal-950/70 px-3 py-3 sm:px-4">
      <p className="text-[10px] font-medium uppercase tracking-[0.12em] text-terminal-500">
        {label}
      </p>
      <p className={`mt-1 break-words font-mono text-lg font-semibold tabular-nums sm:text-xl ${accent ? "text-profit" : "text-terminal-100"}`}>
        {value}
      </p>
    </div>
  );
}

function EvidenceList({
  reasons,
}: {
  reasons: string[];
}) {
  if (!reasons.length) return null;
  return (
    <ul className="space-y-1 text-xs text-warning">
      {reasons.map((reason) => <li key={reason}>{reason}</li>)}
    </ul>
  );
}

function QuoteLeg({ leg }: { leg: Record<string, unknown> }) {
  const action = typeof leg.action === "string" ? leg.action : "Unavailable";
  const isBuy = action.toLowerCase() === "buy";
  return (
    <div className="grid gap-x-4 gap-y-2 rounded border border-terminal-800 bg-terminal-950/60 p-3 sm:grid-cols-2 lg:grid-cols-4">
      <div className="min-w-0 sm:col-span-2">
        <p className="font-mono text-sm text-terminal-100">
          {action} {String(leg.quantity ?? "Unavailable")} {String(leg.type ?? "Option")} {String(leg.strike ?? "Unavailable")}
        </p>
        <p className="mt-1 break-all font-mono text-[11px] text-terminal-400">
          {typeof leg.contract === "string" ? leg.contract : "Exact contract identifier unavailable"}
        </p>
      </div>
      <p className="text-xs text-terminal-300">
        {isBuy ? "Ask" : "Bid"} entry · {formatMoney(isBuy ? leg.ask : leg.bid)}
        <span className="block text-terminal-500">
          Bid {formatMoney(leg.bid)} / Ask {formatMoney(leg.ask)}
        </span>
      </p>
      <p className="break-all text-xs text-terminal-400">
        {String(leg.expiration ?? "Expiration unavailable")}
        <span className="block">Archive quote · {formatLabel(leg.archive_quality)}</span>
      </p>
      <p className="break-all text-[10px] text-terminal-500 sm:col-span-2 lg:col-span-4">
        Bid observed {String(leg.bid_timestamp ?? "timestamp unavailable")}
        {" · "}
        Ask observed {String(leg.ask_timestamp ?? "timestamp unavailable")}
        {Array.isArray(leg.quality_warnings) && leg.quality_warnings.length > 0
          ? ` · Warnings: ${leg.quality_warnings.map(String).join(", ")}`
          : ""}
      </p>
    </div>
  );
}

function PayoffDetails({ research }: { research: Record<string, unknown> }) {
  const payoff = record(research.payoff);
  const grid = Array.isArray(payoff.grid) ? payoff.grid.map(record) : [];
  const rows = grid.length > 9
    ? Array.from({ length: 9 }, (_, i) => grid[Math.round(i * (grid.length - 1) / 8)])
    : grid;
  const breakevens = Array.isArray(research.breakevens)
    ? research.breakevens.filter(
        (value): value is number => typeof value === "number" && Number.isFinite(value),
      )
    : [];
  const evidence = record(research.evidence);
  const economics = record(research.historical_economics);
  const missing = Array.isArray(economics.missing_evidence)
    ? economics.missing_evidence.filter((value): value is string => typeof value === "string")
    : [];

  return (
    <div className="mt-4 space-y-4 border-t border-terminal-800 pt-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <p className="text-xs text-terminal-400">
          Breakeven{breakevens.length === 1 ? "" : "s"}
          <span className="mt-1 block font-mono text-terminal-100">
            {breakevens.length ? breakevens.map(formatMoney).join(" · ") : "Unavailable"}
          </span>
        </p>
        <p className="text-xs text-terminal-400">
          Pricing assumption
          <span className="mt-1 block text-terminal-200">
            {typeof evidence.pricing_assumption === "string"
              ? evidence.pricing_assumption
              : "Unavailable"}
          </span>
        </p>
        <p className="text-xs text-terminal-400">
          Historical economics
          <span className="mt-1 block text-terminal-200">
            {formatLabel(economics.eligibility)}
          </span>
        </p>
      </div>
      {rows.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[380px] text-left text-xs">
            <thead className="text-terminal-500">
              <tr>
                <th className="pb-2 pr-3 font-medium">Underlying at expiration</th>
                <th className="pb-2 pr-3 font-medium">Modeled expiration P&amp;L</th>
                <th className="pb-2 font-medium">Scenario</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={`${String(row["Terminal underlying ($)"])}-${index}`} className="border-t border-terminal-800/70 text-terminal-300">
                  <td className="py-2 pr-3 font-mono">{formatMoney(row["Terminal underlying ($)"])}</td>
                  <td className="py-2 pr-3 font-mono">{formatMoney(row["Expiration P&L ($)"])}</td>
                  <td className="py-2">{typeof row.Landmark === "string" ? row.Landmark : "Backend payoff grid"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {grid.length > rows.length && (
            <p className="mt-2 text-[10px] text-terminal-500">Showing 9 evenly spaced samples from the backend payoff grid.</p>
          )}
        </div>
      ) : (
        <p className="text-xs text-terminal-500">Payoff scenarios are unavailable in this API response.</p>
      )}
      {missing.length > 0 && (
        <div className="rounded border border-warning/20 bg-warning-bg/20 p-3">
          <p className="text-xs font-medium text-warning">Historical research evidence remains unavailable</p>
          <EvidenceList reasons={missing.map(formatLabel)} />
        </div>
      )}
      <p className="text-[11px] text-terminal-500">
        Deterministic expiration payoff from backend research; not a forecast, fill guarantee, probability, expected return, or recommendation.
      </p>
    </div>
  );
}

function OpportunityCard({
  assessment,
  symbol,
  compact = false,
}: {
  assessment: OpportunityAssessment;
  symbol: MarketSymbol;
  compact?: boolean;
}) {
  const candidate = assessment.candidate as Record<string, unknown>;
  const research = record(candidate.research);
  const legs = Array.isArray(research.legs) ? research.legs.map(record) : [];
  const debit = research.entry_debit;
  const credit = research.entry_credit;
  const hasDebit = typeof debit === "number" && Number.isFinite(debit) && debit >= 0;
  const hasCredit = typeof credit === "number" && Number.isFinite(credit) && credit >= 0;
  const entryPricing =
    hasDebit && debit > 0 && hasCredit && credit > 0
      ? `${formatMoney(debit)} debit · ${formatMoney(credit)} credit / share`
      : hasDebit && debit > 0
        ? `${formatMoney(debit)} debit / share`
        : hasCredit && credit > 0
          ? `${formatMoney(credit)} credit / share`
          : hasDebit
            ? `${formatMoney(debit)} debit / share`
            : hasCredit
              ? `${formatMoney(credit)} credit / share`
              : "Unavailable";
  const family = familyLabel(research.strategy_family);
  const headerId = `opportunity-${symbol}-${String(candidate.input_index ?? family).replaceAll(/[^a-zA-Z0-9_-]/g, "-")}`;

  return (
    <article aria-labelledby={headerId} className="rounded-xl border border-profit/25 bg-terminal-900/80 p-4 shadow-lg shadow-black/10 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 id={headerId} className="text-lg font-semibold text-terminal-50 sm:text-xl">{family}</h3>
            <StatusPill label="WITHIN MAX-LOSS BUDGET" variant="archive" />
          </div>
          <p className="mt-1 text-xs text-terminal-400">
            {symbol} <span aria-hidden="true">·</span> {String(research.expiration ?? "Expiration unavailable")}
            {typeof research.dte === "number" ? ` · ${research.dte} DTE` : ""}
          </p>
        </div>
        <span className="inline-flex items-center gap-1 text-xs text-profit">
          <ShieldCheck className="h-4 w-4" aria-hidden="true" />
          Backend-filtered · verified quotes
        </span>
      </div>

      <div className="mt-4 flex flex-wrap gap-2" aria-label="Exact strategy legs">
        {legs.map((leg, index) => (
          <span key={`${String(leg.contract ?? index)}-${index}`} className="rounded-md border border-terminal-700 bg-terminal-950 px-3 py-2 font-mono text-xs text-terminal-100">
            {leg.action === "Sell" ? "SELL" : leg.action === "Buy" ? "BUY" : formatLabel(leg.action)}
            {" "}{String(leg.quantity ?? "—")} {String(leg.type ?? "Option")} {String(leg.strike ?? "—")}
          </span>
        ))}
      </div>

      <div className={`mt-4 grid grid-cols-2 gap-2 ${compact ? "" : "xl:grid-cols-4"}`}>
        <Metric label="Entry pricing · per share" value={entryPricing} />
        <Metric label="Maximum profit" value={formatMaximumProfit(research.max_profit)} accent />
        <Metric label="Maximum modeled loss" value={formatMoney(research.max_loss)} />
        <Metric label="Risk / reward" value={riskReward(research)} />
      </div>
      <p className="mt-3 text-[11px] leading-relaxed text-terminal-500">
        Capital required is the backend expiration max loss ({formatMoney(research.capital_at_risk)}), not broker buying power or margin.
        No recommendation or execution is implied.
      </p>

      <details className="group mt-4 border-t border-terminal-800 pt-3">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded px-1 py-2 text-sm font-medium text-terminal-200 outline-none hover:text-profit focus-visible:ring-2 focus-visible:ring-profit [&::-webkit-details-marker]:hidden">
          <span>Exact contracts, payoff &amp; supporting evidence</span>
          <ChevronDown className="h-4 w-4 shrink-0 transition-transform group-open:rotate-180" aria-hidden="true" />
        </summary>
        <div className="mt-2 space-y-2">
          {legs.map((leg, index) => (
            <QuoteLeg key={`${String(leg.contract ?? index)}-${index}`} leg={leg} />
          ))}
          <PayoffDetails research={research} />
        </div>
      </details>
    </article>
  );
}

function TechnicalResearch({ bundle }: { bundle: ResearchBundle }) {
  const session = bundle.session;
  const market = record(session.market);
  const state = record(session.opportunity_state);
  const classification = record(market.classification_evidence);
  const latest = record(classification.latest);
  const previous = record(classification.previous);
  const expectedEvidence = record(market.expected_move_evidence);
  const structure = record(market.support_resistance ?? market.price_structure);
  const indicators = [
    ["Completed close", latest.close],
    ["EMA 9", latest.ema_9],
    ["EMA 21", latest.ema_21],
    ["EMA 50", latest.ema_50],
    ["20-session high", latest.high_20],
    ["20-session low", latest.low_20],
    ["20-day realized volatility", latest.realized_vol_20d],
    ["60-day realized volatility", latest.realized_vol_60d],
  ] as const;
  const hasIndicators = indicators.some(([, value]) => typeof value === "number" && Number.isFinite(value));

  return (
    <details className="rounded-xl border border-terminal-800 bg-terminal-900/40">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-4 py-4 text-sm font-semibold text-terminal-100 outline-none hover:text-profit focus-visible:ring-2 focus-visible:ring-profit sm:px-5 [&::-webkit-details-marker]:hidden">
        <span className="flex items-center gap-2"><Activity className="h-4 w-4 text-profit" aria-hidden="true" />Technical analysis &amp; market structure</span>
        <ChevronDown className="h-4 w-4 shrink-0 text-terminal-400" aria-hidden="true" />
      </summary>
      <div className="space-y-5 border-t border-terminal-800 px-4 py-4 sm:px-5">
        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-terminal-400">Backend market classification</h3>
          <dl className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-5">
            {([
              ["Direction", state.direction],
              ["Premium", state.premium_state],
              ["Movement", state.movement_state],
              ["Session", state.time_state],
              ["Volatility", state.volatility_state],
            ] as Array<[string, unknown]>).map(([label, value]) => (
              <div key={label} className="rounded border border-terminal-800 bg-terminal-950/70 p-3">
                <dt className="text-[10px] uppercase tracking-wider text-terminal-500">{label}</dt>
                <dd className="mt-1 text-xs font-medium capitalize text-terminal-200">{formatLabel(value)}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-terminal-400">Completed-session technical indicators</h3>
          {hasIndicators ? (
            <dl className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
              {indicators.filter(([, value]) => typeof value === "number" && Number.isFinite(value)).map(([label, value]) => (
                <div key={label} className="rounded border border-terminal-800 bg-terminal-950/70 p-3">
                  <dt className="text-[10px] text-terminal-500">{label}</dt>
                  <dd className="mt-1 font-mono text-sm tabular-nums text-terminal-100">{typeof value === "number" ? value.toLocaleString("en-US", { maximumFractionDigits: 4 }) : "Unavailable"}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="mt-2 text-xs text-terminal-500">Technical indicator observations are unavailable.</p>
          )}
          {typeof latest.date === "string" && <p className="mt-2 text-[11px] text-terminal-500">Latest completed bar: {latest.date}{typeof previous.date === "string" ? ` · Previous: ${previous.date}` : ""}. These are lagged research observations, not live technical signals.</p>}
        </section>

        <section className="grid gap-4 md:grid-cols-2">
          <div className="rounded border border-terminal-800 p-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-terminal-400">Market structure</h3>
            {Object.keys(structure).length > 0 ? (
              <dl className="mt-2 space-y-1">
                {Object.entries(structure).slice(0, 8).map(([key, value]) => (
                  <div key={key} className="flex justify-between gap-3 text-xs">
                    <dt className="text-terminal-500">{formatLabel(key)}</dt>
                    <dd className="break-words text-right text-terminal-200">{typeof value === "number" ? formatMoney(value) : formatLabel(value)}</dd>
                  </div>
                ))}
              </dl>
            ) : <p className="mt-2 text-xs text-terminal-500">Support/resistance levels and price-structure fields are not supplied by this research response.</p>}
          </div>
          <div className="rounded border border-terminal-800 p-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-terminal-400">Expected move</h3>
            <p className="mt-2 font-mono text-sm text-terminal-100">{formatMoney(market.expected_move)}</p>
            <p className="mt-1 text-xs text-terminal-500">
              {typeof expectedEvidence.reason === "string"
                ? formatLabel(expectedEvidence.reason)
                : expectedEvidence.comparison_available === true
                  ? "Backend-supplied expected-move context."
                  : "No comparable, verified expected-move estimate is available."}
            </p>
          </div>
        </section>
        <p className="text-[11px] text-terminal-500">
          Classifier evidence and historical context are descriptive; unknown fields remain unknown. No indicators or structure levels are inferred in the browser.
        </p>
      </div>
    </details>
  );
}

function UnavailableResearch({
  assessments,
  bundle,
}: {
  assessments: OpportunityAssessment[];
  bundle: ResearchBundle;
}) {
  const unavailable = assessments.filter((item) => item.status === "unavailable");
  const unaffordable = assessments.filter((item) => item.status === "unaffordable");
  const session = bundle.session;
  const routes = Array.isArray(session.unavailable_routes)
    ? session.unavailable_routes.map(record)
    : [];
  const exclusions = Array.isArray(session.excluded)
    ? session.excluded.map(record)
    : [];

  return (
    <details className="rounded-xl border border-terminal-800 bg-terminal-900/40">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-4 py-4 text-sm font-semibold text-terminal-100 outline-none hover:text-profit focus-visible:ring-2 focus-visible:ring-profit sm:px-5 [&::-webkit-details-marker]:hidden">
        <span>Unavailable, unaffordable &amp; rejected research <span className="ml-1 font-mono text-terminal-400">{unavailable.length + unaffordable.length + exclusions.length + routes.length}</span></span>
        <ChevronDown className="h-4 w-4 shrink-0 text-terminal-400" aria-hidden="true" />
      </summary>
      <div className="space-y-4 border-t border-terminal-800 px-4 py-4 sm:px-5">
        {assessments.length === 0 && routes.length === 0 && exclusions.length === 0 && (
          <p className="text-xs text-terminal-500">The backend returned no additional candidates, exclusions, or unavailable routes.</p>
        )}
        {unaffordable.length > 0 && (
          <section aria-label="Unaffordable opportunities">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-warning">Above the selected max-loss budget · {unaffordable.length}</h3>
            <div className="mt-2 space-y-2">
              {unaffordable.slice(0, 5).map((assessment, index) => (
                <OpportunitySummary key={`unaffordable-${candidateKey(assessment, index)}`} assessment={assessment} />
              ))}
            </div>
            {unaffordable.length > 5 && <p className="mt-2 text-[11px] text-terminal-500">Showing 5 of {unaffordable.length} backend-rejected candidates.</p>}
          </section>
        )}
        {unavailable.length > 0 && (
          <section aria-label="Incomplete or unsupported research">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-warning">Incomplete or unsupported evidence · {unavailable.length}</h3>
            <div className="mt-2 space-y-2">
              {unavailable.slice(0, 5).map((assessment, index) => (
                <OpportunitySummary key={`unavailable-${candidateKey(assessment, index)}`} assessment={assessment} />
              ))}
            </div>
            {unavailable.length > 5 && <p className="mt-2 text-[11px] text-terminal-500">Showing 5 of {unavailable.length} research records.</p>}
          </section>
        )}
        {routes.length > 0 && (
          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-terminal-400">Unavailable strategy routes</h3>
            <ul className="mt-2 space-y-1 text-xs text-terminal-300">
              {routes.slice(0, 8).map((route, index) => (
                <li key={`route-${index}`}>{familyLabel(route.route)} · {formatLabel(route.reason)}</li>
              ))}
            </ul>
          </section>
        )}
        {exclusions.some((entry) => entry.reason !== "exceeds_available_capital") && (
          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-terminal-400">Backend exclusions</h3>
            <ul className="mt-2 space-y-1 text-xs text-terminal-300">
              {exclusions.filter((entry) => entry.reason !== "exceeds_available_capital").slice(0, 8).map((entry, index) => (
                <li key={`exclusion-${index}`}>{formatLabel(entry.stage)} · {formatLabel(entry.reason)}</li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </details>
  );
}

function OpportunitySummary({ assessment }: { assessment: OpportunityAssessment }) {
  const candidate = assessment.candidate as Record<string, unknown>;
  const research = record(candidate.research);
  const legs = Array.isArray(research.legs) ? research.legs.map(record) : [];
  const requiredCapital = candidate.required_capital;

  return (
    <div className="rounded border border-terminal-800 bg-terminal-950/50 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium text-terminal-200">
          {familyLabel(research.strategy_family)}
          {typeof research.expiration === "string" ? ` · ${research.expiration}` : ""}
        </p>
        {typeof requiredCapital === "number" && (
          <span className="font-mono text-xs text-warning">Required {formatMoney(requiredCapital)}</span>
        )}
      </div>
      {legs.length > 0 && (
        <p className="mt-1 break-words font-mono text-[11px] text-terminal-400">
          {legs.map((leg) => `${leg.action ?? "?"} ${leg.quantity ?? "?"} ${leg.type ?? "option"} ${leg.strike ?? "?"}`).join(" · ")}
        </p>
      )}
      <EvidenceList reasons={assessment.reasons} />
    </div>
  );
}

function ResearchDiagnostics({ bundle }: { bundle: ResearchBundle }) {
  const session = bundle.session;
  const diagnostics = record(session.diagnostics);
  const archive = bundle.archive;
  const archiveDiagnostics = record(archive.diagnostics);
  const observation = record(archive.observation);
  const freshness = record(archive.freshness);
  const pipeline = Array.isArray(diagnostics.pipeline) ? diagnostics.pipeline.map(record) : [];
  const construction = record(diagnostics.construction);
  const caveats = [
    ...bundle.caveats,
    ...(Array.isArray(archive.caveats) ? archive.caveats.filter((item): item is string => typeof item === "string") : []),
    ...(Array.isArray(session.caveats) ? session.caveats.filter((item): item is string => typeof item === "string") : []),
  ];

  return (
    <details className="rounded-xl border border-terminal-800 bg-terminal-900/40">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-4 py-4 text-sm font-semibold text-terminal-100 outline-none hover:text-profit focus-visible:ring-2 focus-visible:ring-profit sm:px-5 [&::-webkit-details-marker]:hidden">
        <span>Archive freshness &amp; research diagnostics</span>
        <ChevronDown className="h-4 w-4 shrink-0 text-terminal-400" aria-hidden="true" />
      </summary>
      <div className="space-y-4 border-t border-terminal-800 px-4 py-4 sm:px-5">
        <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {([
            ["Archive status", observation.options_status],
            ["Archive observed", observation.observed_at],
            ["Snapshot age", typeof freshness.age_seconds === "number" ? `${Math.round(freshness.age_seconds)}s` : null],
            ["Freshness limit", typeof freshness.max_age_seconds === "number" ? `${Math.round(freshness.max_age_seconds)}s` : null],
            ["Generated structures", diagnostics.generated_count],
            ["Accepted by backend", diagnostics.accepted_count],
            ["Capital exclusions", diagnostics.capital_rejection_count],
            ["Width mode", record(diagnostics.width_selection).mode],
          ] as Array<[string, unknown]>).map(([label, value]) => (
            <div key={label} className="min-w-0 rounded border border-terminal-800 bg-terminal-950/70 p-3">
              <dt className="text-[10px] uppercase tracking-wide text-terminal-500">{label}</dt>
              <dd className="mt-1 break-words text-xs text-terminal-200">{formatLabel(value)}</dd>
            </div>
          ))}
        </dl>
        {pipeline.length > 0 && (
          <section className="overflow-x-auto">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-terminal-400">Research pipeline</h3>
            <table className="mt-2 w-full min-w-[500px] text-left text-xs">
              <thead className="text-terminal-500"><tr><th className="py-2 pr-3">Stage</th><th className="py-2 pr-3">Status</th><th className="py-2 pr-3">Input → output</th><th className="py-2">Reasons</th></tr></thead>
              <tbody>{pipeline.slice(0, 10).map((row, index) => (
                <tr key={`pipeline-${index}`} className="border-t border-terminal-800">
                  <td className="py-2 pr-3">{formatLabel(row.stage)}</td>
                  <td className="py-2 pr-3">{formatLabel(row.status)}</td>
                  <td className="py-2 pr-3 font-mono">{String(row.input_count ?? "—")} → {String(row.output_count ?? "—")}</td>
                  <td className="py-2">{Object.entries(record(row.reason_counts)).filter(([, count]) => typeof count === "number" && count > 0).slice(0, 4).map(([reason, count]) => `${formatLabel(reason)} (${count})`).join(", ") || "None reported"}</td>
                </tr>
              ))}</tbody>
            </table>
          </section>
        )}
        {Object.keys(construction).length > 0 && (
          <details className="text-xs">
            <summary className="cursor-pointer text-terminal-400 hover:text-terminal-200">Constructor availability</summary>
            <ul className="mt-2 space-y-1">
              {Object.entries(construction).slice(0, 10).map(([key, value]) => (
                <li key={key}>{formatLabel(key)}: {formatLabel(value)}</li>
              ))}
            </ul>
          </details>
        )}
        {caveats.length > 0 && (
          <ul className="list-disc space-y-1 pl-5 text-[11px] text-terminal-500">
            {caveats.slice(0, 8).map((caveat, index) => <li key={`caveat-${index}`}>{caveat}</li>)}
          </ul>
        )}
        <p className="text-[11px] text-terminal-500">
          The backend API does not provide a broker margin or account-level buying-power requirement. Capital screening uses verified expiration max loss only.
        </p>
      </div>
    </details>
  );
}

export function StrategyResearchDashboard({
  initialSymbol,
}: {
  initialSymbol: MarketSymbol;
}) {
  const [symbol, setSymbol] = useState<MarketSymbol>(initialSymbol);
  const [capital, setCapital] = useState("150");
  const [researchMode, setResearchMode] = useState<ResearchMode>("current");
  const [expiration, setExpiration] = useState("");
  const [expirationDate, setExpirationDate] = useState("");
  const [widthMode, setWidthMode] = useState<"auto" | "manual">("auto");
  const [manualWidth, setManualWidth] = useState("5");
  const [inputError, setInputError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [submitted, setSubmitted] = useState<DashboardQuery>({
    symbol: initialSymbol,
    available_capital: 150,
    research_mode: "current",
  });
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setState({ kind: "loading" });

    void (async () => {
      try {
        const response = await fetch("/api/research/market", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(submitted),
          cache: "no-store",
          signal: controller.signal,
        });
        let body: unknown;
        try {
          body = await response.json();
        } catch (error) {
          if (error instanceof SyntaxError || error instanceof TypeError) {
            if (active) setState({ kind: "error", message: ERROR_MESSAGES.response_schema_mismatch });
            return;
          }
          throw error;
        }
        if (!response.ok) {
          const code = record(body).code;
          if (active) {
            setState({
              kind: "error",
              message: typeof code === "string" ? ERROR_MESSAGES[code] ?? "The research API returned an unsuccessful response." : "The research API returned an unsuccessful response.",
            });
          }
          return;
        }

        const bundle = parseBundle(body, submitted);
        if (!bundle) {
          if (active) setState({ kind: "error", message: ERROR_MESSAGES.response_schema_mismatch });
          return;
        }
        if (active) setState({ kind: "result", bundle, query: submitted });
      } catch (error) {
        if (!active) return;
        setState({
          kind: "error",
          message: error instanceof DOMException && error.name === "AbortError"
            ? "The research request was cancelled."
            : ERROR_MESSAGES.backend_unreachable,
        });
      }
    })();

    return () => {
      active = false;
      controller.abort();
    };
  }, [attempt, submitted]);

  const expirations = useMemo(
    () => state.kind === "result"
      ? archiveExpirations(state.bundle.session, state.bundle.archive)
      : [],
    [state],
  );

  function runResearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const budget = buyingPower(capital);
    if (budget === null) {
      setInputError("Enter a finite, positive dollar amount.");
      return;
    }
    const selectedExpiration = expirationDate || expiration;
    if (selectedExpiration && !/^\d{4}-\d{2}-\d{2}$/.test(selectedExpiration)) {
      setInputError("Choose a valid exact expiration date.");
      return;
    }
    let width: number | undefined;
    if (widthMode === "manual") {
      width = Number(manualWidth);
      if (!Number.isFinite(width) || width <= 0 || width > 100) {
        setInputError("Manual width must be greater than 0 and at most 100 points.");
        return;
      }
    }
    setInputError("");
    setExpiration(selectedExpiration);
    setExpirationDate(selectedExpiration);
    setSubmitted({
      symbol,
      available_capital: budget,
      research_mode: researchMode,
      ...(selectedExpiration ? { expiration: selectedExpiration } : {}),
      ...(width !== undefined ? { width } : {}),
    });
    setAttempt((value) => value + 1);
  }

  return (
    <>
      <Header
        title="Strategy Research"
        subtitle="Verified SPY and QQQ option research · no order execution"
        badge={{ label: "READ-ONLY RESEARCH", variant: "archive" }}
      />
      <div className="mx-auto w-full max-w-[1440px] space-y-5 px-4 py-5 sm:px-6 sm:py-7 lg:px-8">
        <section className="relative overflow-hidden rounded-2xl border border-terminal-800 bg-gradient-to-br from-terminal-900 via-terminal-950 to-terminal-900 p-5 sm:p-7">
          <div className="pointer-events-none absolute -right-10 -top-20 h-56 w-56 rounded-full bg-profit/5 blur-3xl" />
          <div className="relative flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.24em] text-profit">ALPHAOS · OPTIONS RESEARCH</p>
              <h1 className="mt-2 text-2xl font-semibold tracking-tight text-terminal-50 sm:text-3xl">Find the contracts. Understand the risk.</h1>
              <p className="mt-2 max-w-2xl text-sm leading-relaxed text-terminal-400">
                Review backend-researched SPY and QQQ strategies against a verified archive and your expiration max-loss limit.
              </p>
            </div>
            <Link prefetch={false} href={`/market?symbol=${symbol}`} className="inline-flex items-center gap-2 rounded-lg border border-terminal-700 px-3 py-2 text-xs text-terminal-300 transition hover:border-profit/50 hover:text-terminal-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-profit">
              Full market research <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
            </Link>
          </div>
        </section>

        <form onSubmit={runResearch} className="rounded-2xl border border-terminal-800 bg-terminal-900/70 p-4 sm:p-5">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <label className="grid gap-1.5 text-xs text-terminal-400">
              Underlying
              <select aria-label="Underlying" value={symbol} onChange={(event) => setSymbol(event.target.value as MarketSymbol)} className="h-11 w-full rounded-lg border border-terminal-700 bg-terminal-950 px-3 text-sm text-terminal-100 outline-none focus:border-profit focus:ring-1 focus:ring-profit">
                <option value="SPY">SPY · S&amp;P 500 ETF</option>
                <option value="QQQ">QQQ · Nasdaq 100 ETF</option>
              </select>
            </label>
            <label className="grid gap-1.5 text-xs text-terminal-400">
              Available buying power · max-loss budget
              <span className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 font-mono text-sm text-terminal-500">$</span>
                <input aria-label="Available Buying Power ($)" inputMode="decimal" value={capital} onChange={(event) => setCapital(event.target.value)} className="h-11 w-full rounded-lg border border-terminal-700 bg-terminal-950 pl-7 pr-3 font-mono text-sm tabular-nums text-terminal-100 outline-none focus:border-profit focus:ring-1 focus:ring-profit" />
              </span>
            </label>
            <label className="grid gap-1.5 text-xs text-terminal-400">
              Expiration filter
              <select aria-label="Expiration" value={expiration} onChange={(event) => { setExpiration(event.target.value); setExpirationDate(event.target.value); }} className="h-11 w-full rounded-lg border border-terminal-700 bg-terminal-950 px-3 text-sm text-terminal-100 outline-none focus:border-profit focus:ring-1 focus:ring-profit">
                <option value="">Backend archive selection</option>
                {expiration && !expirations.includes(expiration) && <option value={expiration}>{expiration} · explicitly requested</option>}
                {expirations.map((date) => <option key={date} value={date}>{date}</option>)}
              </select>
            </label>
            <label className="grid gap-1.5 text-xs text-terminal-400">
              Research evidence
              <select aria-label="Research mode" value={researchMode} onChange={(event) => setResearchMode(event.target.value as ResearchMode)} className="h-11 w-full rounded-lg border border-terminal-700 bg-terminal-950 px-3 text-sm text-terminal-100 outline-none focus:border-profit focus:ring-1 focus:ring-profit">
                <option value="current">Current · strict freshness</option>
                <option value="historical">Historical archive</option>
              </select>
            </label>
            <div className="grid grid-cols-2 gap-2">
              <label className="grid gap-1.5 text-xs text-terminal-400">
                Spread width
                <select aria-label="Width mode" value={widthMode} onChange={(event) => setWidthMode(event.target.value as "auto" | "manual")} className="h-11 w-full rounded-lg border border-terminal-700 bg-terminal-950 px-2 text-sm text-terminal-100 outline-none focus:border-profit focus:ring-1 focus:ring-profit">
                  <option value="auto">Auto</option>
                  <option value="manual">Manual</option>
                </select>
              </label>
              {widthMode === "manual" ? (
                <label className="grid gap-1.5 text-xs text-terminal-400">
                  Width · points
                  <input aria-label="Manual width (points)" inputMode="decimal" value={manualWidth} onChange={(event) => setManualWidth(event.target.value)} className="h-11 w-full rounded-lg border border-terminal-700 bg-terminal-950 px-2 font-mono text-sm text-terminal-100 outline-none focus:border-profit focus:ring-1 focus:ring-profit" />
                </label>
              ) : (
                <label className="grid gap-1.5 text-xs text-terminal-400">
                  Exact date
                  <input aria-label="Exact expiration date" type="date" value={expirationDate} onChange={(event) => { setExpirationDate(event.target.value); setExpiration(event.target.value); }} className="h-11 w-full min-w-0 rounded-lg border border-terminal-700 bg-terminal-950 px-2 text-xs text-terminal-100 outline-none focus:border-profit focus:ring-1 focus:ring-profit" />
                </label>
              )}
            </div>
          </div>
          <div className="mt-4 flex flex-col gap-3 border-t border-terminal-800 pt-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="max-w-3xl text-[11px] leading-relaxed text-terminal-500">
              Eligibility uses the backend max-loss filter and verified, timestamped option quotes—not broker margin. Missing or stale evidence is never promoted. Historical research is not a current opportunity.
            </p>
            <button type="submit" disabled={state.kind === "loading"} className="inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-lg border border-profit/50 bg-profit-bg px-5 text-sm font-semibold text-profit transition hover:border-profit disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-profit">
              <Activity className="h-4 w-4" aria-hidden="true" />
              {state.kind === "loading" ? "Researching…" : "Run research"}
            </button>
          </div>
          {inputError && <p role="alert" className="mt-3 text-xs text-warning">{inputError}</p>}
          {state.kind === "result" && (
            <p className="mt-2 text-[10px] text-terminal-600">
              Showing the last completed request: {state.query.symbol} · {formatMoney(state.query.available_capital)} max-loss budget. Submit to apply changed filters.
            </p>
          )}
        </form>

        {state.kind === "loading" && (
          <section role="status" className="rounded-xl border border-terminal-800 bg-terminal-900 p-5">
            <p className="font-medium text-terminal-100">Verifying the latest {submitted.symbol} option archive…</p>
            <p className="mt-1 text-xs text-terminal-500">No candidates are displayed until the research response and contract evidence are validated.</p>
          </section>
        )}

        {state.kind === "error" && (
          <section role="alert" className="rounded-xl border border-warning/30 bg-terminal-900 p-5">
            <div className="flex items-start gap-3">
              <CircleAlert className="mt-0.5 h-5 w-5 shrink-0 text-warning" aria-hidden="true" />
              <div>
                <h2 className="font-semibold text-terminal-100">Research unavailable</h2>
                <p className="mt-1 text-sm text-terminal-300">{state.message}</p>
                <p className="mt-2 text-xs text-terminal-500">No contract, quote, probability, eligibility result, or substitute data was displayed.</p>
                <button type="button" onClick={() => setAttempt((value) => value + 1)} className="mt-4 rounded-lg border border-terminal-700 px-4 py-2 text-xs text-terminal-200 hover:border-profit focus-visible:outline focus-visible:outline-2 focus-visible:outline-profit">Retry research</button>
              </div>
            </div>
          </section>
        )}

        {state.kind === "result" && (
          <ResearchResults bundle={state.bundle} query={state.query} />
        )}
      </div>
    </>
  );
}

function ResearchResults({
  bundle,
  query,
}: {
  bundle: ResearchBundle;
  query: DashboardQuery;
}) {
  const archiveReason = archiveVerificationReason(bundle.archive, query.symbol, bundle.asOf, bundle.mode);
  const freshness = record(bundle.archive.freshness);
  const observation = record(bundle.archive.observation);
  const age = typeof freshness.age_seconds === "number" && Number.isFinite(freshness.age_seconds)
    ? `${Math.round(freshness.age_seconds)} sec`
    : "Unavailable";
  const assessments = assessStrategyCandidates(
    bundle.session,
    bundle.archive,
    query.symbol,
    query.available_capital,
    bundle.mode,
    bundle.asOf,
  );
  const eligible = assessments.filter((item) => item.status === "eligible");
  const unaffordable = assessments.filter((item) => item.status === "unaffordable");
  const unavailable = assessments.filter((item) => item.status === "unavailable");
  const spot = record(bundle.session.market).spot;

  return (
    <section className="space-y-4" aria-live="polite">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-terminal-800 bg-terminal-900/60 px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-sm font-semibold text-terminal-100">{query.symbol}</span>
          <span className="text-terminal-700" aria-hidden="true">/</span>
          <span className="text-xs text-terminal-400">{String(bundle.session.expiration ?? "Expiration unavailable")}</span>
          {typeof spot === "number" && Number.isFinite(spot) && (
            <span className="text-xs text-terminal-400">Spot {formatMoney(spot)}</span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusPill
            label={bundle.mode === "historical" ? "HISTORICAL · NOT CURRENT" : archiveReason ? "EVIDENCE INCOMPLETE" : "VERIFIED ARCHIVE"}
            variant={bundle.mode === "current" && !archiveReason ? "archive" : "warning"}
          />
          <span className="text-[11px] text-terminal-500">
            {String(observation.options_status ?? "Archive quality unavailable")} · {age} at request
          </span>
        </div>
      </div>

      {bundle.mode === "historical" && (
        <div role="status" className="rounded-lg border border-warning/30 bg-warning-bg/10 px-4 py-3 text-sm text-warning">
          Historical archive research describes its original observation only; it is not a current trading opportunity and cannot be marked eligible here.
        </div>
      )}
      {archiveReason && bundle.mode === "current" && (
        <div role="status" className="rounded-lg border border-warning/30 bg-warning-bg/10 px-4 py-3 text-sm text-warning">
          Current opportunity eligibility is unavailable: {archiveReason}
        </div>
      )}

      <div className="grid grid-cols-3 gap-2 sm:gap-3">
        <Metric label="Eligible by backend" value={String(eligible.length)} accent={eligible.length > 0} />
        <Metric label="Above max-loss budget" value={String(unaffordable.length)} />
        <Metric label="Unavailable evidence" value={String(unavailable.length)} />
      </div>

      {eligible.length > 0 ? (
        <section aria-label="Eligible opportunities" className="space-y-3">
          <div className="flex flex-wrap items-end justify-between gap-2">
            <div>
              <h2 className="text-lg font-semibold text-terminal-50">Eligible strategies</h2>
              <p className="mt-1 text-xs text-terminal-500">Passed the backend expiration max-loss filter with complete, fresh contract evidence. Not a trading recommendation.</p>
            </div>
            <span className="font-mono text-xs text-profit">{eligible.length} verified</span>
          </div>
          <div className={`grid gap-3 ${eligible.length > 1 ? "xl:grid-cols-2" : ""}`}>
            {eligible.slice(0, 4).map((assessment, index) => (
              <OpportunityCard key={`${query.symbol}-${candidateKey(assessment, index)}`} assessment={assessment} symbol={query.symbol} compact={eligible.length > 1} />
            ))}
          </div>
          {eligible.length > 4 && (
            <details className="rounded-lg border border-terminal-800 bg-terminal-900/50 px-4 py-3">
              <summary className="cursor-pointer text-xs font-medium text-terminal-300">Additional eligible strategies · {eligible.length - 4}</summary>
              <div className="mt-3 grid gap-3 xl:grid-cols-2">
                {eligible.slice(4).map((assessment, index) => (
                  <OpportunityCard key={`${query.symbol}-additional-${candidateKey(assessment, index)}`} assessment={assessment} symbol={query.symbol} compact />
                ))}
              </div>
            </details>
          )}
        </section>
      ) : bundle.mode === "current" ? (
        <section role="status" className="rounded-xl border border-warning/30 bg-terminal-900 p-5 sm:p-6">
          <div className="flex items-start gap-3">
            <CircleAlert className="mt-0.5 h-5 w-5 shrink-0 text-warning" aria-hidden="true" />
            <div>
              <h2 className="font-mono text-lg font-bold tracking-wide text-warning">NO TRADE</h2>
              <p className="mt-1 text-sm text-terminal-200">No opportunity satisfies the backend max-loss limit and all current archive, contract-quote, and research-evidence checks.</p>
              {(unaffordable.length > 0 || unavailable.length > 0) && (
                <p className="mt-2 text-xs text-terminal-500">
                  {unaffordable.length} above budget · {unavailable.length} unavailable or unsupported. Expand the research details below for backend-provided reasons.
                </p>
              )}
            </div>
          </div>
        </section>
      ) : (
        <section role="status" className="rounded-xl border border-terminal-800 bg-terminal-900 p-5">
          <h2 className="font-semibold text-terminal-100">Current opportunities unavailable</h2>
          <p className="mt-1 text-sm text-terminal-400">Historical research cannot establish a current trade opportunity.</p>
        </section>
      )}

      <TechnicalResearch bundle={bundle} />
      <UnavailableResearch assessments={assessments} bundle={bundle} />
      <ResearchDiagnostics bundle={bundle} />

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-terminal-800 pt-4">
        <p className="max-w-3xl text-[11px] leading-relaxed text-terminal-500">
          Archive observations are not guaranteed executable quotes. Max-loss eligibility is not broker buying power or margin. AlphaOS does not place or execute orders.
        </p>
        <div className="flex flex-wrap gap-3">
          <Link prefetch={false} href={`/market?symbol=${query.symbol}`} className="text-xs text-terminal-400 underline decoration-terminal-700 underline-offset-4 hover:text-terminal-100">Full market research</Link>
          <Link prefetch={false} href="/structures" className="text-xs text-terminal-400 underline decoration-terminal-700 underline-offset-4 hover:text-terminal-100">Structure Lab</Link>
          <Link prefetch={false} href="/dashboard" className="text-xs text-terminal-400 underline decoration-terminal-700 underline-offset-4 hover:text-terminal-100">Research dashboard</Link>
        </div>
      </div>
    </section>
  );
}
