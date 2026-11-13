"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import {
  Activity,
  Bot,
  CircleAlert,
  ExternalLink,
  Minus,
  RefreshCw,
  Send,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { Header } from "@/components/shell/Header";
import { StatusPill } from "@/components/shell/StatusPill";
import { TradingViewFallback } from "@/components/market/chart/TradingViewFallback";
import {
  answerWorkspaceQuestion,
  buildWorkspaceAssessment,
  normalizeMarketResponse,
  type WorkspaceDirection,
  type WorkspaceLevel,
  type WorkspaceSetup,
  type WorkspaceSnapshot,
  type WorkspaceSymbol,
} from "@/lib/workspace-evidence";

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "result"; snapshot: WorkspaceSnapshot };

type Message = { role: "assistant" | "user"; text: string };

const SUGGESTED_QUESTIONS = [
  "What would confirm a bullish entry?",
  "Is this breaking out or reversing?",
  "Where is the nearest invalidation?",
  "Why is AlphaOS saying WAIT?",
  "Which setup is closest?",
  "What changed since the previous confirmed candle?",
];

function formatPrice(value: number): string {
  return value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatAsOf(value: string | null): string {
  if (!value) return "Unavailable";
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return "Unavailable";
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZoneName: "short",
  }).format(new Date(timestamp));
}

function sourceLabel(snapshot: WorkspaceSnapshot): string {
  return snapshot.source === "live_public" ? "Public live observation" : "Verified archive";
}

function directionStyle(direction: WorkspaceDirection): string {
  if (direction === "bullish") return "text-profit";
  if (direction === "bearish") return "text-loss";
  if (direction === "neutral") return "text-terminal-200";
  return "text-warning";
}

function setupVariant(state: WorkspaceSetup["state"]): "live" | "warning" | "neutral" {
  if (state === "BUY") return "live";
  if (state === "SELL") return "warning";
  return "neutral";
}

function priceOrUnavailable(value: number | null): string {
  return value === null ? "Unavailable" : `$${formatPrice(value)}`;
}

function SetupCard({ setup }: { setup: WorkspaceSetup }) {
  return (
    <article className={`min-w-0 rounded-lg border p-3 ${
      setup.state === "BUY"
        ? "border-profit/30 bg-profit-bg/10"
        : setup.state === "SELL"
          ? "border-loss/30 bg-loss-bg/10"
          : "border-terminal-800 bg-terminal-950/60"
    }`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="break-words text-xs font-semibold text-terminal-100">{setup.name}</h3>
          <p className="mt-0.5 text-[10px] uppercase tracking-[0.1em] text-terminal-500">
            {setup.direction} · {setup.freshness}
          </p>
        </div>
        <StatusPill label={setup.state} variant={setupVariant(setup.state)} />
      </div>
      {setup.waitReason && (
        <p className="mt-2 break-words text-[11px] leading-relaxed text-terminal-300">
          {setup.waitReason}
        </p>
      )}
      <dl className="mt-2 grid grid-cols-2 gap-2">
        <Metric
          label="Entry trigger"
          value={setup.entry ? priceOrUnavailable(setup.entry.price) : "Not supplied"}
          detail={setup.entry?.condition}
        />
        <Metric
          label="Invalidation"
          value={setup.invalidation ? priceOrUnavailable(setup.invalidation.price) : "Not supplied"}
          detail={setup.invalidation?.condition}
        />
        <Metric
          label="Stop reference"
          value={setup.stop ? priceOrUnavailable(setup.stop.price) : "Not supplied"}
          detail={setup.stop?.basis}
        />
        <Metric
          label="Target reference"
          value={setup.target ? priceOrUnavailable(setup.target.price) : "Not supplied"}
          detail={setup.target?.basis}
        />
      </dl>
      {setup.risk && (
        <p className="mt-2 break-words font-mono text-[10px] text-terminal-500">
          Risk {priceOrUnavailable(setup.risk.underlyingRiskDistance)} · Target distance{" "}
          {setup.risk.targetDistance === null ? "unavailable" : priceOrUnavailable(setup.risk.targetDistance)} · R:R{" "}
          {setup.risk.rewardToRisk === null ? "unavailable" : setup.risk.rewardToRisk.toFixed(2)}
        </p>
      )}
      {setup.missingConditions.length > 0 && (
        <div className="mt-2 rounded border border-warning/20 bg-warning-bg/10 p-2">
          <p className="text-[9px] font-semibold uppercase tracking-[0.12em] text-warning">Missing</p>
          <ul className="mt-1 list-disc space-y-1 pl-4 text-[10px] leading-relaxed text-terminal-300">
            {setup.missingConditions.map((condition) => <li key={condition}>{condition}</li>)}
          </ul>
        </div>
      )}
      {setup.evidence.length > 0 && (
        <details className="mt-2 border-t border-terminal-800 pt-2">
          <summary className="cursor-pointer list-none text-[10px] text-terminal-400 hover:text-profit">
            Evidence
          </summary>
          <ul className="mt-1 list-disc space-y-1 pl-4 text-[10px] leading-relaxed text-terminal-500">
            {setup.evidence.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </details>
      )}
    </article>
  );
}

function DirectionIcon({ direction }: { direction: WorkspaceDirection }) {
  if (direction === "bullish") return <TrendingUp className="h-4 w-4" aria-hidden="true" />;
  if (direction === "bearish") return <TrendingDown className="h-4 w-4" aria-hidden="true" />;
  if (direction === "neutral") return <Minus className="h-4 w-4" aria-hidden="true" />;
  return <CircleAlert className="h-4 w-4" aria-hidden="true" />;
}

function Metric({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <div className="min-w-0 rounded-lg border border-terminal-800 bg-terminal-950/70 p-3">
      <p className="text-[10px] font-medium uppercase tracking-[0.12em] text-terminal-500">{label}</p>
      <p className="mt-1 break-words font-mono text-sm font-semibold tabular-nums text-terminal-100">
        {value}
      </p>
      {detail && <p className="mt-1 break-words text-[10px] leading-relaxed text-terminal-500">{detail}</p>}
    </div>
  );
}

function LevelList({
  title,
  levels,
  empty,
}: {
  title: string;
  levels: WorkspaceLevel[];
  empty: string;
}) {
  return (
    <div className="min-w-0 rounded-lg border border-terminal-800 bg-terminal-950/60 p-3">
      <h3 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-terminal-500">
        {title}
      </h3>
      {levels.length ? (
        <ul className="mt-2 space-y-2">
          {levels.slice(0, 5).map((level) => (
            <li key={`${level.kind}-${level.label}-${level.price}`} className="min-w-0">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                <span className="min-w-0 break-words text-xs text-terminal-300">{level.label}</span>
                <span className="font-mono text-sm tabular-nums text-terminal-100">
                  ${formatPrice(level.price)}
                </span>
              </div>
              <p className="font-mono text-[10px] text-terminal-500">
                {level.distancePct === null
                  ? "Distance unavailable"
                  : `${level.distancePct > 0 ? "+" : ""}${level.distancePct.toFixed(2)}% from spot`}
              </p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-xs leading-relaxed text-terminal-500">{empty}</p>
      )}
    </div>
  );
}

function EvidenceAssistant({
  symbol,
  snapshot,
}: {
  symbol: WorkspaceSymbol;
  snapshot: WorkspaceSnapshot | null;
}) {
  const opening = snapshot
    ? `I’m grounded in the ${snapshot.isLive ? "live" : "archive"} ${symbol} snapshot observed ${formatAsOf(snapshot.asOf)}. Ask why the state is WAIT, what would confirm a bullish or bearish entry, where the nearest invalidation is, which setup is closest, what changed since the previous confirmed candle, or about pivots, opening range, VWAP, EMA 9, and freshness. I will not invent missing fields or a confidence score.`
    : `No verified ${symbol} market snapshot is loaded. I can explain market concepts, but I cannot provide symbol-specific price, trend, or setup analysis. No quote, signal, or setup state is substituted.`;
  const [messages, setMessages] = useState<Message[]>([{ role: "assistant", text: opening }]);
  const [question, setQuestion] = useState("");

  function ask(value: string) {
    const trimmed = value.trim();
    if (!trimmed) return;
    const answer = answerWorkspaceQuestion(snapshot, trimmed);
    setMessages((current) => [
      ...current,
      { role: "user", text: trimmed },
      { role: "assistant", text: answer },
    ]);
    setQuestion("");
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    ask(question);
  }

  return (
    <section aria-labelledby="assistant-heading" className="min-w-0 rounded-xl border border-terminal-800 bg-terminal-900/70">
      <div className="flex items-start justify-between gap-3 border-b border-terminal-800 p-4">
        <div className="min-w-0">
          <h2 id="assistant-heading" className="flex items-center gap-2 text-sm font-semibold text-terminal-100">
            <Bot className="h-4 w-4 text-accent" aria-hidden="true" />
            Evidence assistant
          </h2>
          <p className="mt-1 text-[11px] leading-relaxed text-terminal-500">
            Deterministic answers from the current verified snapshot. No external AI provider call.
          </p>
        </div>
        <StatusPill label="GROUNDED" variant="archive" />
      </div>

      <div
        role="log"
        aria-live="polite"
        aria-relevant="additions"
        className="max-h-[340px] min-w-0 space-y-2 overflow-y-auto p-4"
      >
        {messages.map((message, index) => (
          <div
            key={`${message.role}-${index}`}
            className={
              message.role === "assistant"
                ? "min-w-0 rounded-lg border border-terminal-800 bg-terminal-950/70 p-3"
                : "ml-auto max-w-[88%] rounded-lg border border-profit/20 bg-profit-bg p-3"
            }
          >
            <p className="text-[9px] font-semibold uppercase tracking-[0.14em] text-terminal-500">
              {message.role === "assistant" ? "ALPHAOS EVIDENCE" : "YOU"}
            </p>
            <p className="mt-1 whitespace-pre-wrap break-words text-xs leading-relaxed text-terminal-200">
              {message.text}
            </p>
          </div>
        ))}
      </div>

      <div className="border-t border-terminal-800 p-4">
        <div className="flex flex-wrap gap-1.5" aria-label="Suggested questions">
          {SUGGESTED_QUESTIONS.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              onClick={() => ask(suggestion)}
              className="rounded-full border border-terminal-700 bg-terminal-950 px-2.5 py-1 text-[10px] text-terminal-300 transition hover:border-profit/50 hover:text-terminal-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-profit"
            >
              {suggestion}
            </button>
          ))}
        </div>
        <form onSubmit={submit} className="mt-3 flex min-w-0 items-center gap-2">
          <label htmlFor="assistant-question" className="sr-only">
            Ask about {symbol}
          </label>
          <input
            id="assistant-question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder={`Ask about ${symbol}…`}
            autoComplete="off"
            className="h-10 min-w-0 flex-1 rounded-lg border border-terminal-700 bg-terminal-950 px-3 text-sm text-terminal-100 outline-none placeholder:text-terminal-600 focus:border-profit focus:ring-1 focus:ring-profit"
          />
          <button
            type="submit"
            aria-label="Send question"
            className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-profit/40 bg-profit-bg text-profit transition hover:border-profit disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-profit"
            disabled={!question.trim()}
          >
            <Send className="h-4 w-4" aria-hidden="true" />
          </button>
        </form>
        <p className="mt-2 text-[10px] leading-relaxed text-terminal-600">
          Answers use only fields supplied by the authenticated AlphaOS market bridge. Missing fields are reported, never filled.
        </p>
      </div>
    </section>
  );
}

export function TradingWorkspace({ initialSymbol }: { initialSymbol: WorkspaceSymbol }) {
  const [symbol, setSymbol] = useState<WorkspaceSymbol>(initialSymbol);
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setState({ kind: "loading" });

    void (async () => {
      try {
        const response = await fetch(`/api/market?symbol=${symbol}`, {
          cache: "no-store",
          signal: controller.signal,
        });
        let body: unknown = null;
        try {
          body = await response.json();
        } catch {
          body = null;
        }
        if (!active) return;
        if (!response.ok) {
          setState({
            kind: "error",
            message: response.status === 400
              ? "This workspace supports SPY and QQQ only."
              : "Verified market research is unavailable. No market data was substituted.",
          });
          return;
        }
        const snapshot = normalizeMarketResponse(body);
        if (!snapshot) {
          setState({
            kind: "error",
            message: "The market response did not pass AlphaOS evidence validation. Nothing was displayed.",
          });
          return;
        }
        setState({ kind: "result", snapshot });
      } catch (error) {
        if (!active || (error instanceof DOMException && error.name === "AbortError")) return;
        setState({
          kind: "error",
          message: "The AlphaOS market bridge could not be reached. No quote or level was substituted.",
        });
      }
    })();

    return () => {
      active = false;
      controller.abort();
    };
  }, [attempt, symbol]);

  const snapshot = state.kind === "result" ? state.snapshot : null;
  const assessment = buildWorkspaceAssessment(snapshot);
  const otherLevels = snapshot?.levels.filter((level) => level.kind === "atr" || level.kind === "mid") ?? [];

  function chooseSymbol(next: WorkspaceSymbol) {
    if (next === symbol) return;
    setSymbol(next);
    window.history.replaceState(null, "", `/workspace?symbol=${next}`);
  }

  return (
    <div className="min-w-0">
      <Header
        title="Trading Workspace"
        subtitle="Unified read-only SPY/QQQ research · verified evidence only"
        badge={{ label: "READ-ONLY", variant: "neutral" }}
      />

      <div className="mx-auto w-full max-w-[1440px] min-w-0 space-y-4 px-4 py-5 sm:px-6 sm:py-7 lg:px-8">
        <section className="relative overflow-hidden rounded-2xl border border-terminal-800 bg-gradient-to-br from-terminal-900 via-terminal-950 to-terminal-900 p-4 sm:p-6">
          <div className="pointer-events-none absolute -right-12 -top-20 h-56 w-56 rounded-full bg-profit/5 blur-3xl" />
          <div className="relative flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
            <div className="min-w-0">
              <p className="text-[10px] font-semibold uppercase tracking-[0.24em] text-profit">
                ALPHAOS · UNIFIED WORKSPACE
              </p>
              <h1 className="mt-2 text-2xl font-semibold tracking-tight text-terminal-50 sm:text-3xl">
                Chart, structure, research, and assistant in one place.
              </h1>
              <p className="mt-2 max-w-2xl text-sm leading-relaxed text-terminal-400">
                Reuses the existing AlphaOS market bridge, archive research, and option tools. It does not execute orders or invent missing evidence.
              </p>
            </div>
            <div
              role="group"
              aria-label="Select market symbol"
              className="grid w-full shrink-0 grid-cols-2 gap-2 sm:w-auto"
            >
              {(["SPY", "QQQ"] as const).map((item) => (
                <button
                  key={item}
                  type="button"
                  aria-pressed={item === symbol}
                  onClick={() => chooseSymbol(item)}
                  className={`h-11 rounded-lg border px-4 font-mono text-sm transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-profit ${
                    item === symbol
                      ? "border-profit/50 bg-profit-bg font-semibold text-profit"
                      : "border-terminal-700 bg-terminal-950 text-terminal-300 hover:border-terminal-600 hover:text-terminal-100"
                  }`}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>

          <div className="relative mt-5 flex flex-col gap-4 border-t border-terminal-800/80 pt-4 sm:flex-row sm:items-end sm:justify-between">
            <div className="min-w-0">
              <p className="text-[10px] uppercase tracking-[0.12em] text-terminal-500">
                {symbol} verified spot
              </p>
              <p className="mt-1 break-words font-mono text-3xl font-semibold tabular-nums text-terminal-50 sm:text-4xl">
                {snapshot ? `$${formatPrice(snapshot.spot)}` : state.kind === "loading" ? "Loading…" : "Unavailable"}
              </p>
              <p className="mt-1 break-words text-xs text-terminal-400">
                {snapshot ? `${sourceLabel(snapshot)} · ${formatAsOf(snapshot.asOf)}` : "No verified observation is displayed."}
              </p>
              {snapshot?.tradeIntelligence && (
                <p className="mt-1 break-words text-[10px] text-terminal-500">
                  Session {snapshot.tradeIntelligence.sessionState} · data {snapshot.tradeIntelligence.dataStatus} · confirmed through{" "}
                  {formatAsOf(snapshot.tradeIntelligence.latestConfirmedAt)}
                </p>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {snapshot ? (
                <>
                  <StatusPill
                    label={snapshot.isLive ? "LIVE OBSERVATION" : "ARCHIVE OBSERVATION"}
                    variant={snapshot.isLive ? "live" : "archive"}
                  />
                  <span className={`inline-flex items-center gap-1.5 rounded-full border border-terminal-700 bg-terminal-950 px-2.5 py-1 font-mono text-xs ${directionStyle(snapshot.direction)}`}>
                    <DirectionIcon direction={snapshot.direction} />
                    {assessment.biasLabel}
                  </span>
                </>
              ) : (
                <StatusPill label="NO VERIFIED DATA" variant="warning" />
              )}
              <StatusPill
                label={
                  assessment.stance === "UNAVAILABLE"
                    ? "NO VERIFIED STATE"
                    : `${assessment.stance} / RESEARCH STATE`
                }
                variant={
                  assessment.stance === "BUY"
                    ? "live"
                    : assessment.stance === "SELL"
                      ? "warning"
                      : "neutral"
                }
              />
            </div>
          </div>
        </section>

        {state.kind === "error" && (
          <section role="alert" className="flex flex-col gap-3 rounded-xl border border-warning/30 bg-terminal-900 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 items-start gap-3">
              <CircleAlert className="mt-0.5 h-5 w-5 shrink-0 text-warning" aria-hidden="true" />
              <div>
                <h2 className="font-semibold text-terminal-100">Market evidence unavailable</h2>
                <p className="mt-1 text-sm text-terminal-300">{state.message}</p>
                <p className="mt-1 text-[11px] text-terminal-500">The chart below is an external fallback and is not AlphaOS market evidence.</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setAttempt((value) => value + 1)}
              className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-lg border border-terminal-700 px-4 text-sm text-terminal-200 transition hover:border-profit/50 hover:text-profit focus-visible:outline focus-visible:outline-2 focus-visible:outline-profit"
            >
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              Retry evidence
            </button>
          </section>
        )}

        <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(340px,0.95fr)]">
          <div className="min-w-0 space-y-4">
            <section aria-labelledby="chart-heading" className="min-w-0 rounded-xl border border-terminal-800 bg-terminal-900/50 p-4">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 id="chart-heading" className="text-sm font-semibold text-terminal-100">
                    {symbol} chart
                  </h2>
                  <p className="mt-1 text-[11px] text-terminal-500">
                    External TradingView fallback. First-party AlphaOS candles stay disabled until provider display authorization is confirmed.
                  </p>
                </div>
                <Link
                  prefetch={false}
                  href={`/market/chart?symbol=${symbol}`}
                  className="inline-flex items-center gap-1.5 rounded border border-terminal-700 px-2.5 py-1.5 text-[11px] text-terminal-300 transition hover:border-profit/50 hover:text-profit focus-visible:outline focus-visible:outline-2 focus-visible:outline-profit"
                >
                  Full candle route <ExternalLink className="h-3 w-3" aria-hidden="true" />
                </Link>
              </div>
              <TradingViewFallback symbol={symbol} />
            </section>

            <section aria-labelledby="structure-heading" className="min-w-0 rounded-xl border border-terminal-800 bg-terminal-900/50 p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h2 id="structure-heading" className="flex items-center gap-2 text-sm font-semibold text-terminal-100">
                    <Activity className="h-4 w-4 text-profit" aria-hidden="true" />
                    Structure &amp; levels
                  </h2>
                  <p className="mt-1 text-[11px] leading-relaxed text-terminal-500">
                    Backend structure levels only. Nothing is recalculated or extended in the browser.
                  </p>
                </div>
                <StatusPill label={snapshot ? `${snapshot.levels.length} LEVELS` : "UNAVAILABLE"} variant={snapshot ? "archive" : "warning"} />
              </div>

              {snapshot ? (
                <>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <LevelList
                      title="Support"
                      levels={assessment.support}
                      empty="No verified support level is present in this snapshot."
                    />
                    <LevelList
                      title="Resistance"
                      levels={assessment.resistance}
                      empty="No verified resistance level is present in this snapshot."
                    />
                  </div>

                  {otherLevels.length > 0 && (
                    <div className="mt-3">
                      <LevelList
                        title="ATR / midpoint references"
                        levels={otherLevels}
                        empty="No other backend reference levels are present."
                      />
                    </div>
                  )}

                  <dl className="mt-3 grid grid-cols-2 gap-2">
                    <Metric label="ATR (14)" value={`$${formatPrice(snapshot.atr)}`} detail="Backend risk-context measurement." />
                    <Metric
                      label="Expected move"
                      value={snapshot.expectedMove === null ? "Unavailable" : `$${formatPrice(snapshot.expectedMove)}`}
                      detail={snapshot.expectedMove === null ? "No verified estimate supplied." : "Backend-supplied context, not a forecast."}
                    />
                  </dl>

                  {snapshot.tradeIntelligence ? (
                    <>
                      <div className="mt-3 rounded-lg border border-terminal-800 bg-terminal-950/60 p-3">
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <div>
                            <h3 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-terminal-500">
                              Session, pivots &amp; opening range
                            </h3>
                            <p className="mt-1 text-[10px] text-terminal-500">
                              Calculated only from completed prior-session OHLC and confirmed regular-session bars.
                            </p>
                          </div>
                          <StatusPill
                            label={`${snapshot.tradeIntelligence.dataStatus.toUpperCase()} · ${snapshot.tradeIntelligence.confirmedBars} BARS`}
                            variant={snapshot.tradeIntelligence.dataStatus === "verified" ? "archive" : "warning"}
                          />
                        </div>
                        <dl className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                          <Metric
                            label="Prior session"
                            value={`H ${formatPrice(snapshot.tradeIntelligence.previousSession.high)} / L ${formatPrice(snapshot.tradeIntelligence.previousSession.low)}`}
                            detail={`${snapshot.tradeIntelligence.previousSession.date} · C $${formatPrice(snapshot.tradeIntelligence.previousSession.close)}`}
                          />
                          <Metric
                            label="Current session"
                            value={snapshot.tradeIntelligence.currentSession.high === null
                              ? "Unavailable"
                              : `H ${formatPrice(snapshot.tradeIntelligence.currentSession.high)} / L ${formatPrice(snapshot.tradeIntelligence.currentSession.low ?? snapshot.tradeIntelligence.currentSession.high)}`}
                            detail="Confirmed regular-session bars."
                          />
                          <Metric
                            label="Opening range"
                            value={snapshot.tradeIntelligence.openingRange
                              ? `H ${formatPrice(snapshot.tradeIntelligence.openingRange.high)} / L ${formatPrice(snapshot.tradeIntelligence.openingRange.low)}`
                              : "Forming / unavailable"}
                            detail="First three confirmed five-minute bars."
                          />
                          <Metric
                            label="VWAP / EMA 9"
                            value={`${priceOrUnavailable(snapshot.tradeIntelligence.vwap)} / ${priceOrUnavailable(snapshot.tradeIntelligence.ema9)}`}
                            detail="Confirmed regular-session bars only."
                          />
                        </dl>
                        <dl className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-5">
                          {([
                            ["R2", snapshot.tradeIntelligence.pivots.r2],
                            ["R1", snapshot.tradeIntelligence.pivots.r1],
                            ["Pivot", snapshot.tradeIntelligence.pivots.pivot],
                            ["S1", snapshot.tradeIntelligence.pivots.s1],
                            ["S2", snapshot.tradeIntelligence.pivots.s2],
                          ] as const).map(([label, value]) => (
                            <div key={label} className="min-w-0 rounded border border-terminal-800 bg-terminal-900/60 p-2 text-center">
                              <dt className="text-[9px] uppercase tracking-[0.1em] text-terminal-500">{label}</dt>
                              <dd className="mt-1 font-mono text-xs tabular-nums text-terminal-200">${formatPrice(value)}</dd>
                            </div>
                          ))}
                        </dl>
                      </div>
                      {snapshot.tradeIntelligence.warnings.length > 0 && (
                        <div className="mt-3 rounded-lg border border-warning/25 bg-warning-bg/10 p-3">
                          <h3 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-warning">Session warnings</h3>
                          <ul className="mt-1 list-disc space-y-1 pl-4 text-[10px] leading-relaxed text-terminal-300">
                            {snapshot.tradeIntelligence.warnings.map((warning) => <li key={warning}>{warning}</li>)}
                          </ul>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="mt-3 rounded-lg border border-warning/20 bg-terminal-950/60 p-4">
                      <p className="text-sm text-terminal-300">
                        The verified session/pivot contract is unavailable. No pivot, opening-range, VWAP, or EMA value is inferred.
                      </p>
                      {snapshot.tradeIntelligenceWarning && (
                        <p className="mt-1 text-[10px] text-terminal-500">{snapshot.tradeIntelligenceWarning}</p>
                      )}
                    </div>
                  )}

                  {snapshot.levels.length > 0 && (
                    <details className="group mt-3 border-t border-terminal-800 pt-3">
                      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 text-xs font-medium text-terminal-300 outline-none hover:text-profit focus-visible:ring-2 focus-visible:ring-profit [&::-webkit-details-marker]:hidden">
                        All backend reference levels
                        <span className="font-mono text-terminal-500">{snapshot.levels.length}</span>
                      </summary>
                      <ul className="mt-2 divide-y divide-terminal-800">
                        {snapshot.levels.map((level) => (
                          <li key={`${level.kind}-${level.label}-${level.price}`} className="flex min-w-0 flex-wrap items-baseline justify-between gap-x-3 gap-y-1 py-2">
                            <span className="min-w-0 break-words text-xs text-terminal-300">
                              {level.label}
                              <span className="ml-2 rounded border border-terminal-700 px-1.5 py-0.5 font-mono text-[9px] uppercase text-terminal-500">
                                {level.kind}
                              </span>
                            </span>
                            <span className="font-mono text-sm tabular-nums text-terminal-100">${formatPrice(level.price)}</span>
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                </>
              ) : (
                <div className="mt-3 rounded-lg border border-warning/20 bg-terminal-950/60 p-4">
                  <p className="text-sm text-terminal-300">
                    No support, resistance, pivot, or ATR values are displayed without a validated snapshot.
                  </p>
                </div>
              )}
            </section>
          </div>

          <div className="min-w-0 space-y-4">
            <section aria-labelledby="research-heading" className="min-w-0 rounded-xl border border-terminal-800 bg-terminal-900/70 p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 id="research-heading" className="flex items-center gap-2 text-sm font-semibold text-terminal-100">
                    <ShieldCheck className="h-4 w-4 text-profit" aria-hidden="true" />
                    Trading research
                  </h2>
                  <p className="mt-1 text-[11px] text-terminal-500">Evidence-gated, read-only assessment.</p>
                </div>
                <StatusPill
                  label={assessment.stance}
                  variant={
                    assessment.stance === "BUY"
                      ? "live"
                      : assessment.stance === "SELL"
                        ? "warning"
                        : "neutral"
                  }
                />
              </div>

              <div className={`mt-4 rounded-lg border p-4 ${
                assessment.stance === "WAIT"
                  ? "border-warning/30 bg-warning-bg/15"
                  : "border-terminal-800 bg-terminal-950/60"
              }`}>
                <p className="font-mono text-2xl font-semibold tracking-tight text-terminal-50">
                  {assessment.stance}
                </p>
                <p className="mt-2 text-xs leading-relaxed text-terminal-300">{assessment.reason}</p>
              </div>

              <dl className="mt-3 grid grid-cols-2 gap-2">
                <Metric label="Directional bias" value={assessment.biasLabel} detail="Descriptive, not a signal." />
                <Metric label="Data state" value={snapshot ? (snapshot.isLive ? "Live observation" : "Archive") : "Unavailable"} detail={snapshot ? formatAsOf(snapshot.asOf) : "No verified snapshot."} />
              </dl>

              <div className="mt-3 space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-terminal-500">
                    Setup candidates
                  </h3>
                  <span className="font-mono text-[10px] text-terminal-500">
                    {assessment.sessionState} session
                  </span>
                </div>
                {assessment.setups.length ? (
                  assessment.setups.map((setup) => <SetupCard key={setup.id} setup={setup} />)
                ) : (
                  <div className="rounded-lg border border-warning/20 bg-terminal-950/60 p-3">
                    <p className="text-xs leading-relaxed text-terminal-300">
                      No validated setup candidates were returned. Nothing is inferred from the descriptive bias.
                    </p>
                  </div>
                )}
              </div>

              {assessment.evidenceGaps.length > 0 && (
                <div className="mt-3 rounded-lg border border-warning/25 bg-warning-bg/10 p-3">
                  <h3 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-warning">
                    Missing evidence / conditions
                  </h3>
                  <ul className="mt-1 list-disc space-y-1 pl-4 text-[10px] leading-relaxed text-terminal-300">
                    {assessment.evidenceGaps.map((gap) => <li key={gap}>{gap}</li>)}
                  </ul>
                </div>
              )}

              <div className="mt-3 rounded-lg border border-terminal-800 bg-terminal-950/60 p-3">
                <h3 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-terminal-500">
                  Early exit
                </h3>
                <p className="mt-1 text-xs leading-relaxed text-terminal-300">
                  {assessment.exitEarly
                    ? `${assessment.exitEarly.state}. ${assessment.exitEarly.reason}`
                    : "UNAVAILABLE. No modeled position is connected to this workspace."}
                </p>
                <p className="mt-1 text-[10px] leading-relaxed text-terminal-500">
                  EXIT EARLY is generated only for a specific modeled position with verified exit evidence.
                  An underlying setup never creates an exit state.
                </p>
              </div>

              <div className="mt-3 grid gap-2 sm:grid-cols-3 xl:grid-cols-1">
                <Link prefetch={false} href={`/strategies?symbol=${symbol}`} className="rounded-lg border border-terminal-700 px-3 py-2 text-xs text-terminal-200 transition hover:border-profit/50 hover:text-profit focus-visible:outline focus-visible:outline-2 focus-visible:outline-profit">
                  Strategy Explorer · evidence-gated structures
                </Link>
                <Link prefetch={false} href={`/options?symbol=${symbol}`} className="rounded-lg border border-terminal-700 px-3 py-2 text-xs text-terminal-200 transition hover:border-profit/50 hover:text-profit focus-visible:outline focus-visible:outline-2 focus-visible:outline-profit">
                  Options Chain · contracts
                </Link>
                <Link prefetch={false} href={`/market?symbol=${symbol}`} className="rounded-lg border border-terminal-700 px-3 py-2 text-xs text-terminal-200 transition hover:border-profit/50 hover:text-profit focus-visible:outline focus-visible:outline-2 focus-visible:outline-profit">
                  Market Research · archive diagnostics
                </Link>
              </div>
            </section>

            <EvidenceAssistant
              key={`${symbol}-${snapshot?.asOf ?? "unavailable"}`}
              symbol={symbol}
              snapshot={snapshot}
            />

            {snapshot && (snapshot.caveats.length > 0 || snapshot.warning) && (
              <details className="rounded-xl border border-terminal-800 bg-terminal-900/40 px-4 py-3">
                <summary className="cursor-pointer text-xs font-medium text-terminal-300 outline-none hover:text-profit focus-visible:ring-2 focus-visible:ring-profit">
                  Evidence caveats
                </summary>
                <ul className="mt-2 list-disc space-y-1 pl-4 text-[11px] leading-relaxed text-terminal-500">
                  {snapshot.warning && <li>{snapshot.warning}</li>}
                  {snapshot.caveats.map((caveat) => <li key={caveat}>{caveat}</li>)}
                </ul>
              </details>
            )}
          </div>
        </div>

        <footer className="border-t border-terminal-800 pt-4 text-[10px] leading-relaxed text-terminal-500">
          <p>
            AlphaOS is read-only research software. It does not place orders, provide individualized advice, or guarantee fills.
            External chart data is not AlphaOS market evidence. No Public data is sent to an AI provider by this page.
          </p>
        </footer>
      </div>
    </div>
  );
}
