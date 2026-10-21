
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { buyingPower, archiveExpirations, candidateViews } from "@/lib/market-candidates";
import { Header } from "@/components/shell/Header";
import { StatusPill } from "@/components/shell/StatusPill";

type MarketSymbol = "SPY" | "QQQ";
type ResearchMode = "current" | "historical";

type ResearchBundle = {
  archive: Record<string, unknown>;
  session: Record<string, unknown>;
  provenance: Record<string, unknown>;
  caveats: unknown;
  mode: ResearchMode;
};

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "result"; bundle: ResearchBundle };

const ERROR_MESSAGES: Record<string, string> = {
  backend_not_configured:
    "The website backend URL or server-side API token is not configured.",
  invalid_backend_configuration:
    "The website backend URL configuration is invalid.",
  backend_authentication_required:
    "The backend requires an API token; its configured token was not accepted as authenticated.",
  backend_authentication_rejected:
    "The backend rejected the configured API token. Check server-side credentials without exposing them.",
  archive_not_configured:
    "The backend options archive is not configured.",
  archive_missing:
    "No verified options archive is available for this symbol.",
  archive_stale:
    "The latest verified options archive is stale. No older snapshot or live data was substituted.",
  archive_unavailable:
    "Verified archive evidence is unavailable or could not be validated.",
  archive_research_unavailable:
    "The archived snapshot could not be processed as research evidence.",
  archive_expiration_unavailable:
    "The requested expiration is not present in the verified archive. No different expiration was substituted.",
  backend_rejected_request:
    "The backend rejected the research request.",
  backend_api_not_configured: "The research API is not configured on the backend.",
  backend_internal_error: "The backend could not complete research. Retry; no research evidence was accepted.",
  backend_endpoint_unavailable: "The configured backend does not provide this research endpoint. Check the backend deployment and URL.",
  backend_rate_limited: "The backend is rate limiting research requests. Wait briefly and retry.",
  backend_service_unavailable: "The backend service is temporarily unavailable or starting up. Wait briefly and retry.",
  backend_http_error:
    "The backend returned an unsuccessful research response.",
  response_schema_mismatch:
    "The backend response did not match the required alphaos-interface-v2 research schema.",
  backend_timeout:
    "The backend research request timed out.",
  backend_unreachable:
    "The website could not reach the research backend.",
};

function object(value: unknown): Record<string, unknown> | null {
  return value !== null &&
    typeof value === "object" &&
    !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function parseResearchBundle(
  value: unknown,
  symbol: MarketSymbol,
  mode: ResearchMode,
  expiration?: string
): ResearchBundle | null {
  const outer = object(value);
  const envelope = object(outer?.research);
  const request = object(envelope?.request);
  const research = object(envelope?.research);
  const archive = object(research?.archive);
  const session = object(research?.research_session);
  const provenance = object(envelope?.provenance);
  if (expiration !== undefined && (request?.expiration !== expiration || research?.expiration !== expiration || session?.expiration !== expiration)) return null;

  if (
    envelope?.schema_version !== "alphaos-interface-v2" ||
    envelope.read_only !== true ||
    request?.symbol !== symbol ||
    research?.symbol !== symbol ||
    typeof research.as_of !== "string" ||
    !archive ||
    !session ||
    session.symbol !== symbol ||
    !Array.isArray(session.candidates) ||
    (session.status !== "complete" &&
      session.status !== "no_candidate") ||
    !provenance ||
    outer?.verified_for_trading !== false
  ) {
    return null;
  }
  if (mode === "historical" && (request?.research_mode !== mode || research?.research_mode !== mode)) return null;
  if (mode === "current" && research?.research_mode === "historical") return null;

  return { archive, session, provenance, caveats: envelope.caveats, mode };
}

function displayDate(value: unknown): string {
  if (
    typeof value !== "string" ||
    !Number.isFinite(Date.parse(value))
  ) {
    return "Unavailable";
  }

  return value;
}

function formatValue(value: unknown): string {
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }

  if (typeof value === "string" && value.trim()) {
    return value;
  }

  return "Unavailable";
}

function formatMoney(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "Unavailable";
  }

  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatLabel(value: unknown): string {
  return typeof value === "string" && value.trim()
    ? value.replaceAll("_", " ")
    : "Unavailable";
}

function formatStringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter(
        (item): item is string =>
          typeof item === "string" && item.trim().length > 0
      )
    : [];
}

function formatBreakevens(value: unknown): string {
  const values = Array.isArray(value)
    ? value
    : value === null || value === undefined
      ? []
      : [value];

  const valid = values.filter(
    (item): item is number =>
      typeof item === "number" && Number.isFinite(item)
  );

  return valid.length > 0
    ? valid.map(formatMoney).join(", ")
    : "Unavailable";
}

function ResearchMetric({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded border border-terminal-800 p-3">
      <p className="font-mono text-xs text-terminal-400">
        {label}
      </p>
      <p className="mt-1 font-mono text-sm text-terminal-100">
        {value}
      </p>
    </div>
  );
}

export function MarketResearchPanel({
  symbol,
}: {
  symbol: MarketSymbol;
}) {
  const [attempt, setAttempt] = useState(0);
  const [capital, setCapital] = useState("150");
  const [mode, setMode] = useState<ResearchMode>("current");
  const [expiration, setExpiration] = useState("");
  const [expirations, setExpirations] = useState<string[]>([]);
  const [inputError, setInputError] = useState("");
  const [submitted, setSubmitted] = useState<{available_capital: number; expiration?: string; research_mode?: ResearchMode}>({available_capital: 150});
  const [state, setState] = useState<LoadState>({
    kind: "loading",
  });

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    setState({ kind: "loading" });

    void (async () => {
      try {
        const response = await fetch("/api/research/market", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ symbol, ...submitted }),
          cache: "no-store",
          signal: controller.signal,
        });

        let body: unknown;

        try {
          body = await response.json();
        } catch (error) {
          if (
            error instanceof SyntaxError ||
            error instanceof TypeError
          ) {
            if (active) {
              setState({
                kind: "error",
                message:
                  ERROR_MESSAGES.response_schema_mismatch,
              });
            }
            return;
          }

          throw error;
        }

        if (!response.ok) {
          const error = object(body);
          const code =
            typeof error?.code === "string" ? error.code : "";

          if (active) {
            setState({
              kind: "error",
              message:
                ERROR_MESSAGES[code] ??
                ERROR_MESSAGES.backend_http_error,
            });
          }

          return;
        }

        const bundle = parseResearchBundle(body, symbol, submitted.research_mode ?? "current", submitted.expiration);

        if (!bundle) {
          if (active) {
            setState({
              kind: "error",
              message:
                ERROR_MESSAGES.response_schema_mismatch,
            });
          }
          return;
        }

        if (active) {
          setExpirations(archiveExpirations(bundle.session, bundle.archive));
          setState({ kind: "result", bundle });
        }
      } catch (error) {
        if (!active) return;

        const message =
          error instanceof DOMException &&
          error.name === "AbortError"
            ? "The research request was cancelled."
            : ERROR_MESSAGES.backend_unreachable;

        setState({ kind: "error", message });
      }
    })();

    return () => {
      active = false;
      controller.abort();
    };
  }, [attempt, symbol, submitted]);

  return (
    <div>
      <Header
        title={`Market Research — ${symbol}`}
        subtitle="Authenticated, read-only research from the verified options archive."
        badge={{
          label: "ARCHIVE RESEARCH",
          variant: "archive",
        }}
      />

      <div className="p-8 space-y-6">
        <nav
          className="flex items-center gap-3"
          aria-label="Select market symbol"
        >
          {(["QQQ", "SPY"] as const).map((item) => (
            <Link
              key={item}
              href={`/market?symbol=${item}`}
              aria-current={
                item === symbol ? "page" : undefined
              }
              className={`rounded border px-3 py-1.5 font-mono text-xs ${
                item === symbol
                  ? "border-profit/40 bg-profit-bg text-profit"
                  : "border-terminal-800 bg-terminal-900 text-terminal-400 hover:text-terminal-200"
              }`}
            >
              {item}
            </Link>
          ))}
        </nav>

        <form className="flex flex-wrap items-end gap-4" onSubmit={(event) => {
          event.preventDefault();
          const amount = buyingPower(capital);
          if (amount === null) { setInputError("Enter a finite positive dollar amount."); return; }
          setInputError("");
          setSubmitted({ available_capital: amount, ...(expiration ? {expiration} : {}), ...(mode === "historical" ? {research_mode: mode} : {}) });
        }}>
          <label className="grid gap-2">Research mode
            <select className="rounded bg-terminal-900 border border-terminal-600 p-2" aria-label="Research mode"
              value={mode} onChange={e => setMode(e.target.value as ResearchMode)}>
              <option value="current">Current-market research (strict freshness)</option>
              <option value="historical">Historical archive research</option>
            </select>
          </label>
          <label className="grid gap-2">Available Buying Power ($)
            <input className="rounded bg-terminal-900 border border-terminal-600 p-2" aria-label="Available Buying Power ($)"
              inputMode="decimal" value={capital} onChange={e => setCapital(e.target.value)} />
          </label>
          <label className="grid gap-2">Expiration
            <select className="rounded bg-terminal-900 border border-terminal-600 p-2" aria-label="Expiration"
              value={expiration} onChange={e => setExpiration(e.target.value)}>
              <option value="">Backend archive selection</option>
              {expiration && !expirations.includes(expiration) && <option value={expiration}>{expiration} (explicit request)</option>}
              {expirations.map(date => <option key={date} value={date}>{date}</option>)}
            </select>
          </label>
          <label className="grid gap-2">Exact expiration date
            <input type="date" aria-label="Exact expiration date" value={expiration}
              className="rounded bg-terminal-900 border border-terminal-600 p-2"
              onChange={e => setExpiration(e.target.value)} />
          </label>
          <p className="w-full text-xs text-terminal-400">Listed choices come from archived observations. An exact date requires matching verified archive evidence; no other expiration is substituted. Monthly and long-dated coverage may be unavailable.</p>
          <button className="rounded border border-terminal-600 px-4 py-2" disabled={state.kind === "loading"}>Run Research</button>
          {inputError && <p role="alert">{inputError}</p>}
          <p className="text-xs text-terminal-400 w-full">Capital is an expiration maximum-loss ceiling, not account equity or broker margin. Expiration choices come from the last verified backend response; availability is rechecked on each run. Default spread width: 5 points, matching MCP.</p>
          <p className="text-xs text-terminal-400 w-full">Historical archive research must be requested explicitly. It uses the latest verified snapshot at its original observation time, including after close, weekends and holidays. Historical candidates are not current trading opportunities or executable quotes.</p>
        </form>

        <p className="border border-terminal-800 bg-terminal-900 p-4 font-mono text-xs text-terminal-300">
          This is point-in-time historical options research,
          not a current market quote, executable price, live
          trading signal, broker position, or recommendation.
          Market closure does not by itself invalidate a
          verified archive observation.
        </p>

        {state.kind === "loading" && (
          <section
            role="status"
            className="rounded border border-terminal-800 bg-terminal-900 p-5 font-mono text-sm text-terminal-300"
          >
            Loading authenticated {symbol} archive research...
          </section>
        )}

        {state.kind === "error" && (
          <section
            aria-live="polite"
            className="rounded border border-warning/30 bg-terminal-900 p-5 space-y-3"
          >
            <h2 className="font-mono font-bold text-terminal-100">
              Research unavailable
            </h2>

            <p className="font-mono text-sm text-terminal-300">
              {state.message}
            </p>

            <p className="font-mono text-xs text-terminal-400">
              No price, probability, expected value, or
              candidate has been substituted.
            </p>

            <button
              type="button"
              onClick={() =>
                setAttempt((current) => current + 1)
              }
              className="rounded border border-terminal-600 px-4 py-2 text-sm text-terminal-100 hover:bg-terminal-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-profit"
            >
              Retry research
            </button>
          </section>
        )}

        {state.kind === "result" && (
          <ResearchResult
            bundle={state.bundle}
            symbol={symbol}
          />
        )}
      </div>
    </div>
  );
}

function ResearchResult({
  bundle,
  symbol,
}: {
  bundle: ResearchBundle;
  symbol: MarketSymbol;
}) {
  const session = bundle.session;
  const coverage = object(object(bundle.archive.expiration_coverage)?.horizons);
  const archiveObservation = object(
    bundle.archive.observation
  );

  const candidates = candidateViews(session);

  const observationAt = displayDate(
    archiveObservation?.observed_at
  );

  const ageSeconds = object(
    bundle.archive.freshness
  )?.age_seconds;

  const archiveAge =
    typeof ageSeconds === "number" &&
    Number.isFinite(ageSeconds) &&
    ageSeconds >= 0
      ? `${Math.round(ageSeconds)} seconds at request time`
      : "Not supplied";

  const eligibleCandidateCount = candidates.filter((candidate) => {
    const entry = object(candidate);
    const research = object(entry?.research);
    const economics = object(research?.historical_economics);
    return economics?.eligible_for_consideration === true;
  }).length;

  const researchStatus =
    candidates.length === 0
      ? object(session.diagnostics)?.generated_count === 0 ? "NO CANDIDATES GENERATED" : "NO EVALUABLE CANDIDATES"
      : "RESEARCH ONLY — SEE CAPITAL AND EVIDENCE STATUS";

  return (
    <section
      className="space-y-5"
      aria-live="polite"
    >
      <div className="flex items-center gap-3">
        <h2 className="font-mono text-sm font-bold text-terminal-100">
          {symbol} archived research
        </h2>

        <StatusPill
          label={researchStatus}
          variant={
            eligibleCandidateCount > 0 ? "archive" : "warning"
          }
        />
      </div>
      {coverage && <section aria-label="Expiration coverage" className="overflow-x-auto">
        <h3>Archived expiration coverage</h3>
        <table className="w-full text-left text-sm"><thead><tr><th>Horizon</th><th>Archived dates</th></tr></thead>
          <tbody>{Object.entries({"0dte":"0DTE", "1dte":"1DTE", weekly:"Weekly", monthly:"Monthly", long_dated:"Long-dated / LEAPS-style"}).map(([key,label]) => {
            const entry = object(coverage[key]);
            const dates = Array.isArray(entry?.expirations) ? entry.expirations.filter((d): d is string => typeof d === "string") : [];
            return <tr key={key}><th>{label}</th><td>{dates.length ? dates.join(", ") : "Missing verified archive evidence"}</td></tr>;
          })}</tbody>
        </table>
        <p className="text-xs text-terminal-400">Calendar-day labels; monthly dates follow the exchange calendar. Long-dated means at least 365 days, not verified LEAPS series status. Archived observations do not establish fresh quotes or eligible candidates.</p>
      </section>}
      <p className="rounded border border-warning/30 p-4 font-mono text-sm">
        {bundle.mode === "historical"
          ? "HISTORICAL ARCHIVE RESEARCH — candidates describe the archived observation, not current trading opportunities or executable quotes."
          : "CURRENT-MARKET RESEARCH — strict archive freshness; archived observations are not executable quotes."}
      </p>

      <div className="grid gap-3 sm:grid-cols-2">
        <ResearchMetric label="Archive source" value={formatValue(bundle.archive.provider)} />
        <ResearchMetric label="Archive expiration" value={formatValue(session.expiration)} />
        <ResearchMetric
          label="Archive observation"
          value={observationAt}
        />

        <ResearchMetric
          label="Archive freshness at request"
          value={archiveAge}
        />
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <ResearchMetric label="Generated structures" value={formatValue(object(session.diagnostics)?.generated_count)} />
        <ResearchMetric label="Accepted by backend" value={formatValue(object(session.diagnostics)?.accepted_count)} />
        <ResearchMetric label="Capital-rejected structures" value={formatValue(object(session.diagnostics)?.capital_rejection_count)} />
      </div>
      <ResearchMetric label="Available buying power used" value={formatMoney(session.available_capital)} />
      <section className="rounded border border-terminal-800 p-4 space-y-3">
        <h3>Candidate generation diagnostics</h3>
        <p className="text-xs">Unavailable classifications are not invalid structures. Matched market routes and quote-supported structure research are reported separately. Counts apply to this snapshot and selected expiration; they are not rankings or a count of all possible trades.</p>
        {object(session.diagnostics)?.generation_basis === "unclassified_quote_research" && (
          <p className="font-mono text-sm text-warning">No evidence-supported market route matched. Both existing debit hypotheses were tested with observed quotes and deltas; resulting structures are unclassified research, not evidence-supported opportunities.</p>
        )}
        {typeof object(session.diagnostics)?.zero_candidate_reason === "string" && (
          <p className="text-sm">Zero-candidate reason: {formatLabel(object(session.diagnostics)?.zero_candidate_reason)}</p>
        )}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs" aria-label="Candidate generation pipeline">
            <thead><tr><th className="p-2">Stage</th><th className="p-2">Status</th><th className="p-2">Input</th><th className="p-2">Output</th><th className="p-2">Reasons</th></tr></thead>
            <tbody>{(Array.isArray(object(session.diagnostics)?.pipeline) ? object(session.diagnostics)!.pipeline as unknown[] : []).map((value, index) => {
              const stage = object(value);
              return <tr key={index} className="border-t border-terminal-800">
                <th className="p-2">{formatLabel(stage?.stage)}</th>
                <td className="p-2">{formatLabel(stage?.status)}</td>
                <td className="p-2">{formatValue(stage?.input_count)} {formatLabel(stage?.input_unit)}</td>
                <td className="p-2">{formatValue(stage?.output_count)} {formatLabel(stage?.output_unit)}</td>
                <td className="p-2">{Object.entries(object(stage?.reason_counts) ?? {}).filter(([, count]) => typeof count === "number" && count > 0).map(([reason, count]) => `${formatLabel(reason)}: ${count}`).join("; ") || "None reported"}</td>
              </tr>;
            })}</tbody>
          </table>
        </div>
        <details><summary>Constructor counts and exclusion reasons</summary>
          <pre className="whitespace-pre-wrap break-words text-xs">{JSON.stringify(object(session.diagnostics)?.construction ?? "Unavailable", null, 2)}</pre>
        </details>
      </section>
      <section className="rounded border border-terminal-800 p-4 space-y-3">
        <h3>Backend exclusions and unavailable routes</h3>
        <ul className="text-sm list-disc pl-5 space-y-2">
          {(Array.isArray(session.excluded) ? session.excluded : []).map((item, i) => {
            const row = object(item); return <li key={`excluded-${i}`}>{formatLabel(row?.stage)}: {formatLabel(row?.reason)}
              {row?.required_capital !== undefined ? `; required capital ${formatMoney(row.required_capital)}` : ""}</li>;
          })}
          {(Array.isArray(session.unavailable_routes) ? session.unavailable_routes : []).map((item, i) => {
            const row = object(item); return <li key={`route-${i}`}>{formatLabel(row?.route)}: {formatLabel(row?.reason)}</li>;
          })}
          {formatStringList(object(session.diagnostics)?.blocking_reasons).map(reason => <li key={reason}>{formatLabel(reason)}</li>)}
        </ul>
        <p className="text-xs">Evidence-supported backend routes retain their existing constructors. When no route matches, both existing debit hypotheses may be evaluated as unclassified quote-supported research. Automatic discovery supports long calls/puts, debit/credit verticals, iron condors, iron butterflies and broken-wing butterflies. Standard long butterflies require explicit structure research; they are not automatically discovered. No additional families are implied by this screen.</p>
        <ul className="text-xs list-disc pl-5">{[...formatStringList(bundle.caveats), ...formatStringList(bundle.archive.caveats), ...formatStringList(session.caveats)].map((warning,i)=><li key={i}>{warning}</li>)}</ul>
      </section>
      <details className="rounded border border-terminal-800 p-4">
        <summary>Research outcomes, strategy routes and exclusions</summary>
        <p className="text-xs">Counts are backend-reported for this snapshot and routed constructors, not all possible structures. No candidates generated differs from all generated candidates being excluded.</p>
        <pre className="whitespace-pre-wrap break-words text-xs mt-3">{JSON.stringify({
          diagnostics: session.diagnostics ?? "Unavailable",
          strategy_routes: session.strategy_routes ?? "Unavailable",
          unavailable_routes: session.unavailable_routes ?? "Unavailable",
          excluded: session.excluded ?? "Unavailable",
          archive_exclusions: bundle.archive.excluded ?? "Unavailable",
          warnings: [bundle.caveats, bundle.archive.caveats, session.caveats],
          provenance: bundle.provenance,
        }, null, 2)}</pre>
      </details>
      <p className="font-mono text-xs text-terminal-400">
        This observation is historical archive evidence.
        Its freshness window is not a live-quote or
        execution guarantee.
      </p>

      {candidates.length === 0 ? (
        <div className="rounded border border-warning/30 bg-terminal-900 p-4 space-y-2">
          <p className="font-mono text-sm text-terminal-200">
            Research completed, but this archive snapshot
            returned no evaluable candidate structures. See backend generated/rejected counts and evidence reasons above.
          </p>

          <p className="font-mono text-xs text-terminal-400">
            This does not establish that no market
            opportunities exist.
          </p>
        </div>
      ) : (
        <div className="space-y-5">
          {candidates.map((candidate, index) => {
            const entry = object(candidate);
            const research = object(entry?.research);
            const economics = object(
              research?.historical_economics
            );

            const legs = Array.isArray(research?.legs)
              ? research.legs
              : [];

            const eligible =
              economics?.eligible_for_consideration === true;

            const missingEvidence = formatStringList(
              economics?.missing_evidence
            );

            const researchOnlyReasons = formatStringList(
              economics?.research_only_reasons
            );

            return (
              <article
                key={index}
                className="rounded border border-terminal-700 bg-terminal-900 p-5 space-y-5"
              >
                <div className="space-y-2">
                  <h3 className="font-mono text-base font-bold text-terminal-100 capitalize">
                    {formatLabel(
                      research?.strategy_family ??
                        entry?.strategy_family
                    )}
                  </h3>

                  <p className="font-mono text-sm">{formatValue(entry?.capital_status)}</p>
                  {entry?.classification_supported === false && <p className="font-mono text-xs text-warning">Unclassified quote-supported structure — market thesis unavailable; not an evidence-supported opportunity.</p>}
                  <p className="font-mono text-xs text-terminal-300">
                    Underlying: {symbol}{" · "}Direction:{" "}
                    {formatLabel(research?.direction)}
                    {" · "}
                    Expiration:{" "}
                    {formatValue(research?.expiration)}
                    {" · "}
                    DTE: {formatValue(research?.dte)}
                  </p>

                  <p
                    className={`font-mono text-xs font-bold ${
                      eligible
                        ? "text-terminal-200"
                        : "text-warning"
                    }`}
                  >
                    {eligible
                      ? "Backend eligibility reported: true. Not a trade recommendation."
                      : "Evidence incomplete — NOT ELIGIBLE FOR CONSIDERATION"}
                  </p>

                  <p className="font-mono text-xs text-terminal-400">
                    Eligibility status:{" "}
                    {formatValue(economics?.eligibility)}
                  </p>
                </div>

                <div className="space-y-2">
                  <h4 className="font-mono text-sm font-bold text-terminal-200">
                    Option legs
                  </h4>

                  {legs.length > 0 ? (
                    <div className="space-y-2">
                      {legs.map((leg, legIndex) => {
                        const item = object(leg);

                        return (
                          <div
                            key={legIndex}
                            className="rounded border border-terminal-800 p-3 font-mono text-sm text-terminal-200"
                          >
                            {formatValue(item?.action)}
                            {" "}
                            {formatValue(
                              item?.quantity ?? item?.qty
                            )}
                            {" × "}
                            {formatValue(item?.type)}
                            {" "}
                            {formatValue(item?.strike)}
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="font-mono text-xs text-terminal-400">
                      Leg details unavailable.
                    </p>
                  )}
                </div>

                <div className="space-y-3">
                  <h4 className="font-mono text-sm font-bold text-terminal-200">
                    Modeled expiration economics
                  </h4>

                  <div className="grid grid-cols-2 gap-3">
                    <ResearchMetric
                      label="Entry debit per share"
                      value={formatMoney(
                        research?.entry_debit
                      )}
                    />

                    <ResearchMetric
                      label="Entry credit per share"
                      value={formatMoney(
                        research?.entry_credit
                      )}
                    />

                    <ResearchMetric
                      label="Capital at risk"
                      value={formatMoney(
                        research?.capital_at_risk
                      )}
                    />

                    <ResearchMetric
                      label="Maximum loss"
                      value={formatMoney(
                        research?.max_loss
                      )}
                    />

                    <ResearchMetric
                      label="Maximum profit"
                      value={research?.max_profit === "unlimited" ? "Unlimited" : formatMoney(research?.max_profit)}
                    />
                  </div>

                  <ResearchMetric
                    label="Expiration breakeven(s)"
                    value={formatBreakevens(
                      research?.breakevens ??
                        research?.breakeven
                    )}
                  />

                  <p className="font-mono text-xs text-terminal-400">
                    These are modeled expiration payoffs,
                    not guaranteed returns, executable
                    prices, probabilities, or expected values.
                  </p>
                </div>

                <details className="text-xs whitespace-pre-wrap break-words"><summary>Backend evidence, quote timestamps and quality limitations</summary><pre className="whitespace-pre-wrap break-words">{JSON.stringify(research, null, 2)}</pre></details>
                <ResearchMetric label="Broker buying-power requirement" value="Unavailable — not supplied by backend" />
                <ResearchMetric label="Risk/reward ratio" value={formatValue(research?.risk_reward_ratio)} />
                <div className="rounded border border-warning/30 p-4 space-y-3">
                  <h4 className="font-mono text-sm font-bold text-terminal-100">
                    Historical evidence and eligibility
                  </h4>

                  <p className="font-mono text-xs text-terminal-300">
                    Historical evidence status:{" "}
                    {formatValue(
                      economics?.historical_evidence_status
                    )}
                  </p>

                  <p className="font-mono text-xs text-terminal-300">
                    Economics coverage:{" "}
                    {formatValue(
                      economics?.economics_coverage
                    )}
                  </p>

                  {missingEvidence.length > 0 && (
                    <div className="space-y-2">
                      <p className="font-mono text-xs font-bold text-warning">
                        Missing evidence
                      </p>

                      <ul className="list-disc pl-5 space-y-1">
                        {missingEvidence.map(
                          (reason, reasonIndex) => (
                            <li
                              key={reasonIndex}
                              className="font-mono text-xs text-terminal-300"
                            >
                              {formatLabel(reason)}
                            </li>
                          )
                        )}
                      </ul>
                    </div>
                  )}

                  {researchOnlyReasons.length > 0 && (
                    <div className="space-y-2">
                      <p className="font-mono text-xs font-bold text-terminal-200">
                        Research limitations
                      </p>

                      <ul className="list-disc pl-5 space-y-1">
                        {researchOnlyReasons.map(
                          (reason, reasonIndex) => (
                            <li
                              key={reasonIndex}
                              className="font-mono text-xs text-terminal-300"
                            >
                              {reason}
                            </li>
                          )
                        )}
                      </ul>
                    </div>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}

      <p className="font-mono text-xs text-terminal-500">
        Candidate order is not a ranking. No candidate
        is a live quote, recommendation, or verified
        probability or expected-value claim.
      </p>
    </section>
  );
}
