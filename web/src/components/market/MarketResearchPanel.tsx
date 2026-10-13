"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Header } from "@/components/shell/Header";
import { StatusPill } from "@/components/shell/StatusPill";

type ResearchBundle = {
  archive: Record<string, unknown>;
  session: Record<string, unknown>;
  provenance: Record<string, unknown>;
};

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "result"; bundle: ResearchBundle };

const ERROR_MESSAGES: Record<string, string> = {
  backend_not_configured: "The website backend URL or server-side API token is not configured.",
  invalid_backend_configuration: "The website backend URL configuration is invalid.",
  backend_authentication_required: "The backend requires an API token; its configured token was not accepted as authenticated.",
  backend_authentication_rejected: "The backend rejected the configured API token. Check server-side credentials without exposing them.",
  archive_not_configured: "The backend options archive is not configured.",
  archive_missing: "No verified options archive is available for this symbol.",
  archive_stale: "The latest verified options archive is stale. No older snapshot or live data was substituted.",
  archive_unavailable: "Verified archive evidence is unavailable or could not be validated.",
  archive_research_unavailable: "The archived snapshot could not be processed as research evidence.",
  archive_expiration_unavailable: "The requested expiration is not present in the verified archive. No different expiration was substituted.",
  backend_rejected_request: "The backend rejected the research request.",
  backend_http_error: "The backend returned an unsuccessful research response.",
  response_schema_mismatch: "The backend response did not match the required alphaos-interface-v2 research schema.",
  backend_timeout: "The backend research request timed out.",
  backend_unreachable: "The website could not reach the research backend.",
};

function object(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function parseResearchBundle(value: unknown, symbol: string): ResearchBundle | null {
  const outer = object(value);
  const envelope = object(outer?.research);
  const request = object(envelope?.request);
  const research = object(envelope?.research);
  const archive = object(research?.archive);
  const session = object(research?.research_session);
  const provenance = object(envelope?.provenance);
  if (envelope?.schema_version !== "alphaos-interface-v2" ||
      envelope.read_only !== true ||
      request?.symbol !== symbol ||
      research?.symbol !== symbol ||
      typeof research.as_of !== "string" ||
      !archive || !session || session.symbol !== symbol ||
      !Array.isArray(session.candidates) ||
      (session.status !== "complete" && session.status !== "no_candidate") ||
      !provenance || outer?.verified_for_trading !== false) {
    return null;
  }
  return { archive, session, provenance };
}

function displayDate(value: unknown): string {
  if (typeof value !== "string" || !Number.isFinite(Date.parse(value))) return "Unavailable";
  return value;
}

export function MarketResearchPanel({ symbol }: { symbol: "SPY" | "QQQ" }) {
  const [attempt, setAttempt] = useState(0);
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
          body: JSON.stringify({ symbol }),
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
          const error = object(body);
          const code = typeof error?.code === "string" ? error.code : "";
          if (active) {
            setState({
              kind: "error",
              message: ERROR_MESSAGES[code] ?? ERROR_MESSAGES.backend_http_error,
            });
          }
          return;
        }
        const bundle = parseResearchBundle(body, symbol);
        if (!bundle) {
          if (active) setState({ kind: "error", message: ERROR_MESSAGES.response_schema_mismatch });
          return;
        }
        if (active) setState({ kind: "result", bundle });
      } catch (error) {
        if (!active) return;
        const message = error instanceof DOMException && error.name === "AbortError"
          ? "The research request was cancelled."
          : ERROR_MESSAGES.backend_unreachable;
        setState({ kind: "error", message });
      }
    })();

    return () => {
      active = false;
      controller.abort();
    };
  }, [attempt, symbol]);

  return (
    <div>
      <Header
        title={`Market Research — ${symbol}`}
        subtitle="Authenticated, read-only research from the verified options archive."
        badge={{ label: "ARCHIVE RESEARCH", variant: "archive" }}
      />
      <div className="p-8 space-y-6">
        <nav className="flex items-center gap-3" aria-label="Select market symbol">
          {(["QQQ", "SPY"] as const).map((item) => (
            <Link
              key={item}
              href={`/market?symbol=${item}`}
              aria-current={item === symbol ? "page" : undefined}
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

        <p className="border border-terminal-800 bg-terminal-900 p-4 font-mono text-xs text-terminal-300">
          This is point-in-time historical options research, not a current market quote, executable price,
          live trading signal, broker position, or recommendation. Market closure does not by itself invalidate
          a verified archive observation.
        </p>

        {state.kind === "loading" && (
          <section role="status" className="rounded border border-terminal-800 bg-terminal-900 p-5 font-mono text-sm text-terminal-300">
            Loading authenticated {symbol} archive research…
          </section>
        )}

        {state.kind === "error" && (
          <section aria-live="polite" className="rounded border border-warning/30 bg-terminal-900 p-5 space-y-3">
            <h2 className="font-mono font-bold text-terminal-100">Research unavailable</h2>
            <p className="font-mono text-sm text-terminal-300">{state.message}</p>
            <p className="font-mono text-xs text-terminal-400">
              No price, probability, expected value, or candidate has been substituted.
            </p>
            <button
              type="button"
              onClick={() => setAttempt((current) => current + 1)}
              className="rounded border border-terminal-600 px-4 py-2 text-sm text-terminal-100 hover:bg-terminal-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-profit"
            >
              Retry research
            </button>
          </section>
        )}

        {state.kind === "result" && <ResearchResult bundle={state.bundle} symbol={symbol} />}
      </div>
    </div>
  );
}

function ResearchResult({ bundle, symbol }: { bundle: ResearchBundle; symbol: "SPY" | "QQQ" }) {
  const session = bundle.session;
  const archiveObservation = object(bundle.archive.observation);
  const candidates = Array.isArray(session.candidates) ? session.candidates : [];
  const researchStatus = session.status === "complete" ? "CANDIDATES AVAILABLE" : "NO ELIGIBLE CANDIDATES";
  const observationAt = displayDate(archiveObservation?.observed_at);
  const ageSeconds = object(bundle.archive.freshness)?.age_seconds;
  const archiveAge = typeof ageSeconds === "number" && Number.isFinite(ageSeconds) && ageSeconds >= 0
    ? `${Math.round(ageSeconds)} seconds at request time`
    : "not supplied";

  return (
    <section className="space-y-4" aria-live="polite">
      <div className="flex items-center gap-3">
        <h2 className="font-mono text-sm font-bold text-terminal-100">{symbol} archived research</h2>
        <StatusPill label={researchStatus} variant={candidates.length ? "archive" : "warning"} />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded border border-terminal-800 bg-terminal-900 p-4">
          <h3 className="font-mono text-xs text-terminal-400">Archive observation</h3>
          <p className="mt-2 font-mono text-sm text-terminal-100">{observationAt}</p>
        </div>
        <div className="rounded border border-terminal-800 bg-terminal-900 p-4">
          <h3 className="font-mono text-xs text-terminal-400">Archive freshness at request</h3>
          <p className="mt-2 font-mono text-sm text-terminal-100">{archiveAge}</p>
        </div>
      </div>
      <p className="font-mono text-xs text-terminal-400">
        The observation is historical archive evidence. Its freshness window is not a live-quote or execution guarantee.
      </p>
      {candidates.length > 0 ? (
        <ul className="space-y-2" aria-label="Research candidates">
          {candidates.map((candidate, index) => {
            const item = object(candidate);
            const family = typeof item?.strategy_family === "string"
              ? item.strategy_family.replaceAll("_", " ")
              : "Unspecified structure";
            return (
              <li key={`${family}-${index}`} className="rounded border border-terminal-800 bg-terminal-900 p-4 font-mono text-sm text-terminal-200">
                {family}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="rounded border border-terminal-800 bg-terminal-900 p-4 font-mono text-sm text-terminal-300">
          Research completed, but this archive snapshot produced no eligible candidates.
        </p>
      )}
      <p className="font-mono text-xs text-terminal-500">
        Candidate order is not a ranking. No candidate is a live quote, recommendation, probability, or expected-value claim.
      </p>
    </section>
  );
}
