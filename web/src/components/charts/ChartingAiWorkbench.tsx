"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Header } from "@/components/shell/Header";
import { StatusPill } from "@/components/shell/StatusPill";
import { TradingViewChart } from "@/components/charts/TradingViewChart";
import {
  CHART_SYMBOLS,
  DEFAULT_CHART_INTERVAL,
  type ChartEvidence,
  type ChartInterval,
  type ChartSymbol,
  type ChatSuccessBody,
  type ChatTurn,
} from "@/lib/chart-types";

const SUGGESTED_QUESTIONS = [
  "What is the current market structure?",
  "Where are the important support and resistance levels?",
  "Is this a breakout or a potential fakeout?",
  "Is the market trending or consolidating?",
  "What would invalidate a bullish or bearish setup?",
  "Are there any options strategies worth researching?",
] as const;

const CHAT_ERROR_MESSAGES: Record<string, string> = {
  chat_not_configured:
    "The AlphaOS AI assistant is not configured on this deployment. An operator must set the assistant API key and model server-side. No answer was generated.",
  chat_timeout:
    "The assistant did not answer in time. No answer was generated; retry when ready.",
  chat_provider_error:
    "The assistant provider could not complete the request. No answer was generated.",
  chat_response_invalid:
    "The assistant returned an unreadable answer, so it was not displayed.",
  chat_rate_limited:
    "Too many assistant requests from this browser. Wait briefly and retry.",
  cross_origin_rejected: "The assistant rejected a cross-origin request.",
  market_evidence_not_configured:
    "AlphaOS market evidence is not configured on this deployment. The assistant cannot ground an answer without it.",
  market_evidence_unreachable:
    "AlphaOS market evidence is unreachable. No substitute prices or levels were used.",
  market_evidence_timeout:
    "AlphaOS market evidence timed out. No substitute prices or levels were used.",
  market_evidence_backend_error:
    "The AlphaOS research backend returned an unsuccessful response. No substitute prices or levels were used.",
  market_evidence_schema_mismatch:
    "AlphaOS market evidence failed verification. Nothing was substituted.",
  market_evidence_mismatch:
    "AlphaOS market and structure evidence do not describe the same verified snapshot. Nothing was substituted.",
  unsupported_chart_symbol: "Only SPY and QQQ are supported.",
  invalid_request: "The assistant request was rejected as invalid.",
};

type EvidenceState =
  | { kind: "loading" }
  | { kind: "ready"; evidence: ChartEvidence }
  | { kind: "unavailable"; message: string };

type ChatMessage = ChatTurn & { blocked?: boolean };
type Pending = { question: string; status: "sending" | "error"; message?: string };

function messageForCode(code: string): string {
  return CHAT_ERROR_MESSAGES[code] ??
    "The assistant is unavailable. No answer was generated.";
}

/**
 * Provider failures carry a sanitised status and category (never a provider
 * message), so the operator can tell a rejected key from a missing model,
 * exhausted quota or unreachable endpoint after a single attempt.
 */
function providerDetail(data: Record<string, unknown> | null): string {
  const status = typeof data?.provider_status === "number" ? `HTTP ${data.provider_status}` : null;
  const category = typeof data?.provider_error_category === "string"
    ? data.provider_error_category.replace(/_/g, " ") : null;
  const host = typeof data?.provider_host === "string" && data.provider_host ? data.provider_host : null;
  const parts = [status, category, host].filter((part): part is string => Boolean(part));
  return parts.length > 0 ? ` (provider ${parts.join(" · ")})` : "";
}

function formatTimestamp(value: string): string {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? new Date(parsed).toISOString() : "timestamp unavailable";
}

function object(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown> : null;
}

function isSuccessBody(value: unknown): value is ChatSuccessBody {
  const body = object(value);
  return body?.status === "ok" && typeof body.reply === "string" &&
    typeof body.chart_claim_blocked === "boolean" && object(body.evidence) !== null;
}

export function ChartingAiWorkbench({ initialSymbol }: { initialSymbol: ChartSymbol }) {
  const [symbol, setSymbol] = useState<ChartSymbol>(initialSymbol);
  const [interval, setInterval] = useState<ChartInterval>(DEFAULT_CHART_INTERVAL);
  const [evidence, setEvidence] = useState<EvidenceState>({ kind: "loading" });
  const [evidenceAttempt, setEvidenceAttempt] = useState(0);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState<Pending | null>(null);
  const [disclosures, setDisclosures] = useState<string[]>([]);
  const logRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setMessages([]);
    setPending(null);
    setDisclosures([]);
    setEvidence({ kind: "loading" });
    const controller = new AbortController();
    let active = true;
    void (async () => {
      try {
        const response = await fetch(
          `/api/charts/evidence?symbol=${encodeURIComponent(symbol)}`,
          { cache: "no-store", signal: controller.signal },
        );
        const body = object(await response.json().catch(() => null));
        if (!active) return;
        if (!response.ok || body?.status !== "ok" || !object(body.evidence)) {
          setEvidence({
            kind: "unavailable",
            message: messageForCode(typeof body?.code === "string" ? body.code : ""),
          });
          return;
        }
        setEvidence({ kind: "ready", evidence: body.evidence as ChartEvidence });
      } catch (error) {
        if (!active || (error instanceof DOMException && error.name === "AbortError")) return;
        setEvidence({ kind: "unavailable", message: messageForCode("market_evidence_unreachable") });
      }
    })();
    return () => {
      active = false;
      controller.abort();
    };
  }, [symbol, evidenceAttempt]);

  const changeSymbol = useCallback((next: ChartSymbol) => {
    setSymbol(next);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("symbol", next);
      window.history.replaceState(null, "", url.toString());
    }
  }, []);

  // Scroll only the conversation log: a page-level scroll here pulled the
  // mobile layout away from the chart and header on load.
  useEffect(() => {
    const log = logRef.current;
    if (log) log.scrollTop = log.scrollHeight;
  }, [messages, pending]);

  const sendQuestion = useCallback(async (rawQuestion: string) => {
    const question = rawQuestion.trim();
    if (!question || question.length > 2_000) return;
    const history: ChatTurn[] = [
      ...messages.map(({ role, content }) => ({ role, content })),
      { role: "user", content: question },
    ];
    setInput("");
    setPending({ question, status: "sending" });

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30_000);
    try {
      const response = await fetch("/api/charts/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol, messages: history }),
        cache: "no-store",
        signal: controller.signal,
      });
      const body: unknown = await response.json().catch(() => null);
      const data = object(body);
      if (response.ok && isSuccessBody(body)) {
        setMessages((current) => [
          ...current,
          { role: "user", content: question },
          { role: "assistant", content: body.reply, blocked: body.chart_claim_blocked },
        ]);
        setDisclosures(Array.isArray(body.disclosures)
          ? body.disclosures.filter((item): item is string => typeof item === "string")
          : []);
        if (object(body.evidence)) {
          setEvidence((current) => current.kind === "ready"
            ? { kind: "ready", evidence: { ...current.evidence, ...body.evidence } }
            : current);
        }
        setPending(null);
        return;
      }
      setPending({
        question,
        status: "error",
        message: messageForCode(typeof data?.code === "string" ? data.code : "") +
          (data?.code === "chat_provider_error" ? providerDetail(data) : ""),
      });
    } catch {
      const timedOut = controller.signal.aborted;
      setPending({
        question,
        status: "error",
        message: timedOut
          ? "The assistant request timed out. No answer was generated; retry when ready."
          : "The assistant could not be reached. No answer was generated.",
      });
    } finally {
      clearTimeout(timeout);
    }
  }, [messages, symbol]);

  const busy = pending?.status === "sending";
  const readyEvidence = evidence.kind === "ready" ? evidence.evidence : null;

  return (
    <div>
      <Header
        title="Charting & AI"
        subtitle="Embedded TradingView charting with an evidence-grounded AlphaOS research assistant."
        badge={{ label: "RESEARCH ONLY", variant: "neutral" }}
      />

      <div className="p-4 sm:p-6 lg:p-8 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <nav aria-label="Select chart symbol" className="flex items-center gap-2">
            <span className="font-mono text-[11px] uppercase tracking-wide text-terminal-500">
              Symbol
            </span>
            {CHART_SYMBOLS.map((item) => (
              <button
                key={item}
                type="button"
                aria-pressed={symbol === item}
                onClick={() => changeSymbol(item)}
                className={`rounded border px-3 py-1.5 font-mono text-xs transition-colors ${
                  symbol === item
                    ? "border-profit/40 bg-profit-bg text-profit"
                    : "border-terminal-800 bg-terminal-900 text-terminal-400 hover:text-terminal-200"
                }`}
              >
                {item}
              </button>
            ))}
          </nav>
          <p className="font-mono text-[11px] text-terminal-500">
            Read-only research · no broker execution
          </p>
        </div>

        <p className="rounded border border-terminal-800 bg-terminal-900 p-3 font-mono text-[11px] leading-relaxed text-terminal-300">
          The chart is an embedded TradingView widget that may be delayed. The
          assistant never reads it. Every answer is grounded in independently
          retrieved, timestamped AlphaOS evidence and says so when that evidence
          is stale, missing or insufficient.
        </p>

        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_400px]">
          <div className="space-y-4">
            <TradingViewChart
              symbol={symbol}
              interval={interval}
              onIntervalChange={setInterval}
            />

            <section
              aria-label="AlphaOS market evidence status"
              className="rounded border border-terminal-800 bg-terminal-900 p-3 sm:p-4 space-y-2"
            >
              <div className="flex flex-wrap items-center gap-3">
                <h2 className="font-mono text-xs font-bold uppercase tracking-wide text-terminal-200">
                  AlphaOS evidence · {symbol}
                </h2>
                {evidence.kind === "ready" && (
                  <StatusPill
                    label={evidence.evidence.mode === "current" ? "CURRENT AT RETRIEVAL" : "POINT-IN-TIME"}
                    variant={evidence.evidence.mode === "current" ? "archive" : "warning"}
                  />
                )}
                {evidence.kind === "loading" && <StatusPill label="LOADING" variant="neutral" />}
                {evidence.kind === "unavailable" && <StatusPill label="UNAVAILABLE" variant="warning" />}
              </div>

              {evidence.kind === "ready" && (
                <div className="grid gap-2 font-mono text-[11px] text-terminal-400 sm:grid-cols-2">
                  <p>
                    Source: <span className="text-terminal-200">{evidence.evidence.source}</span>{" "}
                    via AlphaOS research API (not TradingView)
                  </p>
                  <p>
                    Market data as of:{" "}
                    <span className="text-terminal-200">{formatTimestamp(evidence.evidence.as_of)}</span>
                  </p>
                  <p>
                    Age at retrieval:{" "}
                    <span className="text-terminal-200">{evidence.evidence.age_seconds}s</span>{" "}
                    · status {evidence.evidence.data_status}
                  </p>
                  <p>
                    Spot{" "}
                    <span className="text-terminal-200">{evidence.evidence.spot.toFixed(2)}</span>{" "}
                    · ATR(14){" "}
                    <span className="text-terminal-200">{evidence.evidence.atr_14.toFixed(2)}</span>
                  </p>
                  <p className="sm:col-span-2">
                    Backend structure:{" "}
                    <span className="text-terminal-200">
                      {evidence.evidence.market_state.ema_structure ?? "not reported"}
                    </span>{" "}
                    · direction:{" "}
                    <span className="text-terminal-200">
                      {evidence.evidence.market_state.direction_reported
                        ? evidence.evidence.market_state.direction
                        : "not reported"}
                    </span>
                  </p>
                  {evidence.evidence.levels.length > 0 && (
                    <p className="sm:col-span-2">
                      Backend levels:{" "}
                      {evidence.evidence.levels.map((level) => (
                        <span key={`${level.label}-${level.price}`} className="mr-2 inline-block">
                          <span className="text-terminal-300">{level.label}</span>{" "}
                          <span className="text-terminal-200">{level.price.toFixed(2)}</span>{" "}
                          <span className="text-terminal-500">
                            ({level.kind}
                            {level.zone_low !== undefined && level.zone_high !== undefined
                              ? ` · zone ${level.zone_low.toFixed(2)}–${level.zone_high.toFixed(2)}`
                              : ""})
                          </span>
                        </span>
                      ))}
                    </p>
                  )}
                  {evidence.evidence.mode === "point_in_time" && (
                    <p role="status" className="sm:col-span-2 text-warning">
                      This evidence is point-in-time and is not current market
                      conditions. The market may have moved since the recorded
                      observation.
                    </p>
                  )}
                </div>
              )}

              {evidence.kind === "loading" && (
                <p role="status" className="font-mono text-xs text-terminal-400">
                  Loading verified {symbol} evidence…
                </p>
              )}

              {evidence.kind === "unavailable" && (
                <div className="space-y-2">
                  <p role="status" className="font-mono text-xs text-warning">
                    {evidence.message}
                  </p>
                  <p className="font-mono text-[11px] text-terminal-400">
                    No price, level, signal or substitute observation is shown.
                  </p>
                  <button
                    type="button"
                    onClick={() => setEvidenceAttempt((value) => value + 1)}
                    className="rounded border border-terminal-600 px-3 py-1.5 font-mono text-[11px] text-terminal-100 hover:bg-terminal-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-profit"
                  >
                    Retry evidence
                  </button>
                </div>
              )}
            </section>
          </div>

          <section
            aria-label="AlphaOS AI assistant"
            className="flex h-[560px] flex-col rounded border border-terminal-800 bg-terminal-900 xl:h-auto xl:min-h-[640px]"
          >
            <div className="space-y-1 border-b border-terminal-800 p-3 sm:p-4">
              <div className="flex items-center justify-between gap-2">
                <h2 className="font-mono text-xs font-bold uppercase tracking-wide text-terminal-200">
                  AlphaOS AI · {symbol}
                </h2>
                <button
                  type="button"
                  onClick={() => {
                    setMessages([]);
                    setPending(null);
                    setDisclosures([]);
                  }}
                  className="rounded border border-terminal-700 px-2 py-1 font-mono text-[10px] text-terminal-400 hover:text-terminal-200"
                >
                  Clear
                </button>
              </div>
              <p className="font-mono text-[10px] leading-relaxed text-terminal-500">
                Assistant context: {symbol} ·{" "}
                {readyEvidence ? formatTimestamp(readyEvidence.as_of) : "evidence timestamp pending"}
                <br />
                The assistant cannot see the TradingView chart, its candles,
                indicators or drawings.
              </p>
            </div>

            <div
              role="log"
              aria-live="polite"
              ref={logRef}
              className="flex-1 space-y-3 overflow-y-auto p-3 sm:p-4"
            >
              {messages.length === 0 && !pending && (
                <div className="space-y-2">
                  <p className="font-mono text-[11px] leading-relaxed text-terminal-400">
                    Ask about market structure, AlphaOS levels, trend context or
                    options research areas. Answers use only the timestamped
                    AlphaOS evidence shown beside the chart. This assistant is not
                    a signal service and does not place orders.
                  </p>
                  <p className="font-mono text-[11px] text-terminal-500">Suggested questions:</p>
                  <div className="flex flex-wrap gap-2">
                    {SUGGESTED_QUESTIONS.map((question) => (
                      <button
                        key={question}
                        type="button"
                        disabled={busy}
                        onClick={() => void sendQuestion(question)}
                        className="rounded-full border border-terminal-700 bg-terminal-950 px-2.5 py-1 text-left font-mono text-[10px] text-terminal-300 hover:border-terminal-600 hover:text-terminal-100 disabled:opacity-50"
                      >
                        {question}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((message, index) => (
                <div
                  key={`${message.role}-${index}`}
                  className={`rounded border p-3 font-mono text-[11px] leading-relaxed whitespace-pre-wrap ${
                    message.role === "user"
                      ? "border-terminal-700 bg-terminal-950 text-terminal-200"
                      : "border-terminal-800 bg-terminal-850 text-terminal-200"
                  }`}
                >
                  <p className="mb-1 text-[9px] uppercase tracking-wide text-terminal-500">
                    {message.role === "user" ? "You" : "AlphaOS AI"}
                  </p>
                  {message.content}
                  {message.blocked && (
                    <p className="mt-2 border-t border-warning/30 pt-2 text-warning">
                      Guardrail: the model tried to describe the TradingView chart.
                      That answer was replaced because AlphaOS has no chart access.
                    </p>
                  )}
                </div>
              ))}

              {pending && (
                <div className="rounded border border-terminal-700 bg-terminal-950 p-3 font-mono text-[11px] text-terminal-300">
                  <p className="mb-1 text-[9px] uppercase tracking-wide text-terminal-500">You</p>
                  {pending.question}
                </div>
              )}

              {pending?.status === "sending" && (
                <p role="status" className="font-mono text-[11px] text-terminal-400">
                  Retrieving verified evidence and requesting an answer…
                </p>
              )}

              {pending?.status === "error" && (
                <div role="alert" className="space-y-2 rounded border border-warning/30 bg-terminal-950 p-3">
                  <p className="font-mono text-[11px] text-warning">{pending.message}</p>
                  <button
                    type="button"
                    onClick={() => void sendQuestion(pending.question)}
                    className="rounded border border-terminal-600 px-3 py-1.5 font-mono text-[11px] text-terminal-100 hover:bg-terminal-800"
                  >
                    Retry question
                  </button>
                </div>
              )}

              {disclosures.length > 0 && (
                <ul className="space-y-1 border-t border-terminal-800 pt-2 font-mono text-[10px] text-terminal-500">
                  {disclosures.map((item) => <li key={item}>{item}</li>)}
                </ul>
              )}
            </div>

            <form
              className="space-y-2 border-t border-terminal-800 p-3 sm:p-4"
              onSubmit={(event) => {
                event.preventDefault();
                void sendQuestion(input);
              }}
            >
              <label htmlFor="charts-ai-question" className="sr-only">
                Ask the AlphaOS assistant about {symbol}
              </label>
              <textarea
                id="charts-ai-question"
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void sendQuestion(input);
                  }
                }}
                rows={2}
                maxLength={2_000}
                placeholder={`Ask about ${symbol} structure, AlphaOS levels or options research…`}
                className="w-full resize-none rounded border border-terminal-700 bg-terminal-950 p-2 font-mono text-[11px] text-terminal-100 placeholder:text-terminal-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-profit"
              />
              <div className="flex items-center justify-between gap-2">
                <p className="font-mono text-[10px] text-terminal-500">
                  Session history only · not advice
                </p>
                <button
                  type="submit"
                  disabled={busy || !input.trim()}
                  className="rounded border border-terminal-600 px-4 py-1.5 font-mono text-[11px] text-terminal-100 hover:bg-terminal-800 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-profit"
                >
                  {busy ? "Asking…" : "Send"}
                </button>
              </div>
            </form>
          </section>
        </div>
      </div>
    </div>
  );
}
