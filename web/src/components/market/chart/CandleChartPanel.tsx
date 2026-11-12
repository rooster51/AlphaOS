"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { Header } from "@/components/shell/Header";
import { StatusPill } from "@/components/shell/StatusPill";
import {
  CANDLE_INTERVALS,
  CANDLE_REFRESH_MS,
  ageSeconds,
  completenessLabel,
  fetchCandles,
  fetchCurrentQuote,
  formatAge,
  lastBarLabel,
  warningLabel,
  type CandleClientError,
  type CandleInterval,
  type CandleQuote,
  type CandleSnapshot,
  type CandleSymbol,
} from "@/lib/candles";
import { EMA_PERIODS, toChartSeries, type EmaPeriod } from "@/lib/candle-chart";
import { LightweightCandleChart } from "./LightweightCandleChart";

const QUOTE_REFRESH_MS = 15_000;
const MAX_BACKOFF_MS = 160_000;

const ERROR_MESSAGES: Record<string, string> = {
  authentication_required: "Your website session is no longer valid. Sign in again to load authenticated candles.",
  owner_only: "Only the authenticated repository owner may view these candles. No data was returned to this account.",
  data_use_denied: "This account is not entitled to display this provider's candles. No substitute data was shown.",
  provider_rate_limited: "The provider is rate limiting candle requests. Retrying has been backed off; no tight retry loop is running.",
  provider_unavailable: "Native candles are temporarily unavailable from the provider. No bars were synthesized.",
  provider_timeout: "The provider did not return candles before the deadline. The previous snapshot, if any, remains labelled with its own age.",
  provider_schema_error: "The provider response failed AlphaOS contract validation. Nothing from that response was rendered.",
  response_schema_mismatch: "The candle response did not match the alphaos-candles-v1 contract. Nothing was rendered.",
  backend_unreachable: "The candle service could not be reached. No substitute data was shown.",
  request_timeout: "The candle request timed out. No substitute data was shown.",
  invalid_request: "The candle request is outside the supported SPY/QQQ, 1m/5m/15m regular-session surface.",
  cancelled: "The candle request was cancelled by a newer selection.",
};

function formatUtc(value: string): string {
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return "Unavailable";
  return `${new Date(parsed).toISOString().slice(0, 19).replace("T", " ")} UTC`;
}

function formatPrice(value: number): string {
  return value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  });
}

function errorCopy(error: CandleClientError | null): string {
  if (!error) return "";
  return ERROR_MESSAGES[error.code] ?? error.message;
}

function transientError(error: CandleClientError): boolean {
  return ["provider_rate_limited", "provider_unavailable", "provider_timeout", "request_timeout", "backend_unreachable"]
    .includes(error.code);
}

function StatusMetric({ label, value, title }: { label: string; value: string; title?: string }) {
  return (
    <div className="min-w-0 rounded border border-terminal-800 bg-terminal-950/70 p-3">
      <dt className="text-[10px] font-medium uppercase tracking-[0.12em] text-terminal-500">{label}</dt>
      <dd title={title} className="mt-1 break-words font-mono text-xs text-terminal-100">{value}</dd>
    </div>
  );
}

export function CandleChartPanel({
  symbol,
  initialInterval,
}: {
  symbol: CandleSymbol;
  initialInterval: CandleInterval;
}) {
  const [interval, setInterval] = useState<CandleInterval>(initialInterval);
  const [snapshot, setSnapshot] = useState<CandleSnapshot | null>(null);
  const [error, setError] = useState<CandleClientError | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [retryAt, setRetryAt] = useState<number | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [quote, setQuote] = useState<CandleQuote | null>(null);
  const [activeEmas, setActiveEmas] = useState<EmaPeriod[]>([9, 21]);
  const [now, setNow] = useState(() => Date.now());
  const requestGeneration = useRef(0);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 5_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const generation = ++requestGeneration.current;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let transientFailures = 0;

    function schedule(delay: number) {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => void load(false), delay);
    }

    async function load(first: boolean) {
      if (stopped || generation !== requestGeneration.current) return;
      if (!first && document.visibilityState === "hidden") {
        schedule(CANDLE_REFRESH_MS);
        return;
      }
      if (first) {
        setLoading(true);
        setRetryAt(null);
        setError(null);
      } else {
        setRefreshing(true);
      }
      const result = await fetchCandles(symbol, interval, { signal: controller.signal });
      if (stopped || generation !== requestGeneration.current) return;
      if (result.ok) {
        transientFailures = 0;
        setSnapshot(result.snapshot);
        setError(null);
        setRetryAt(null);
        setLoading(false);
        setRefreshing(false);
        schedule(CANDLE_REFRESH_MS);
        return;
      }
      if (result.error.code === "cancelled") return;
      setLoading(false);
      setRefreshing(false);
      setError(result.error);
      if (transientError(result.error)) {
        transientFailures += 1;
        const delay = Math.min(CANDLE_REFRESH_MS * 2 ** transientFailures, MAX_BACKOFF_MS);
        setRetryAt(Date.now() + delay);
        schedule(delay);
      } else {
        setRetryAt(null);
      }
    }

    void load(true);
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      controller.abort();
    };
  }, [attempt, interval, symbol]);

  useEffect(() => {
    const controller = new AbortController();
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    async function load() {
      const result = await fetchCurrentQuote(symbol, { signal: controller.signal });
      if (stopped || controller.signal.aborted) return;
      setQuote(result.quote);
      if (result.quote.status === "unavailable" &&
          ["authentication_failure", "session_expired", "forbidden"].includes(result.quote.code)) return;
      const retryable = result.quote.status === "unavailable" &&
        ["provider_unavailable", "request_timeout", "quote_unavailable"].includes(result.quote.code);
      timer = setTimeout(load, retryable ? 60_000 : QUOTE_REFRESH_MS);
    }

    void load();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      controller.abort();
    };
  }, [attempt, symbol]);

  const activeSnapshot = snapshot?.symbol === symbol && snapshot.interval === interval ? snapshot : null;
  const chartSeries = useMemo(() => (activeSnapshot ? toChartSeries(activeSnapshot) : null), [activeSnapshot]);
  const quoteAge = quote?.status === "fresh" ? ageSeconds(quote.lastAt, now) : null;
  const quoteMarker = quote?.status === "fresh"
    ? {
        price: quote.last,
        label: `Quote ${formatPrice(quote.last)} · ${formatAge(quoteAge)}${quoteAge !== null && quoteAge > 15 ? " · stale" : ""}`,
      }
    : null;
  const snapshotAge = activeSnapshot ? ageSeconds(activeSnapshot.retrieved_at, now) : null;
  const retryIn = retryAt === null ? null : Math.max(0, Math.ceil((retryAt - now) / 1000));
  const busy = loading || refreshing;
  const severe = activeSnapshot
    ? activeSnapshot.freshness === "stale" || activeSnapshot.completeness !== "complete" ||
      activeSnapshot.last_bar_status !== "complete"
    : false;

  function chooseInterval(next: CandleInterval) {
    if (next === interval) return;
    setInterval(next);
    setError(null);
    setRetryAt(null);
    setLoading(true);
    setRefreshing(false);
  }

  function toggleEma(period: EmaPeriod) {
    setActiveEmas((current) => current.includes(period)
      ? current.filter((value) => value !== period)
      : [...current, period]);
  }

  return (
    <div className="min-w-0">
      <Header
        title={`Candle Chart — ${symbol}`}
        subtitle="Owner-authenticated provider-native candles · regular session · UTC time scale"
        badge={{ label: "ALPHAOS CANDLES", variant: "live" }}
      />

      <div className="mx-auto w-full max-w-[1440px] min-w-0 space-y-5 px-4 py-5 sm:px-6 sm:py-7 lg:px-8">
        <nav aria-label="Candle symbol and related research" className="flex flex-wrap items-center gap-2">
          {(["SPY", "QQQ"] as const).map((item) => (
            <Link
              prefetch={false}
              key={item}
              href={`/market/chart?symbol=${item}&interval=${interval}`}
              aria-current={item === symbol ? "page" : undefined}
              className={`rounded border px-3 py-1.5 font-mono text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-profit ${
                item === symbol
                  ? "border-profit/40 bg-profit-bg text-profit"
                  : "border-terminal-800 bg-terminal-900 text-terminal-400 hover:text-terminal-200"
              }`}
            >
              {item}
            </Link>
          ))}
          <span className="mx-1 h-4 w-px bg-terminal-800" aria-hidden="true" />
          <Link
            prefetch={false}
            href={`/market?symbol=${symbol}`}
            className="rounded border border-terminal-800 px-3 py-1.5 font-mono text-xs text-terminal-400 hover:border-terminal-600 hover:text-terminal-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-profit"
          >
            Archive research
          </Link>
        </nav>

        <section aria-label="Chart controls" className="flex flex-wrap items-end gap-3 rounded-lg border border-terminal-800 bg-terminal-900/60 p-3 sm:p-4">
          <div>
            <p className="mb-1 text-[10px] font-medium uppercase tracking-[0.12em] text-terminal-500">Timeframe</p>
            <div role="group" aria-label="Candle timeframe" className="flex flex-wrap gap-1">
              {CANDLE_INTERVALS.map((item) => (
                <button
                  key={item}
                  type="button"
                  aria-pressed={item === interval}
                  onClick={() => chooseInterval(item)}
                  className={`rounded border px-3 py-2 font-mono text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-profit ${
                    item === interval
                      ? "border-profit/50 bg-profit-bg text-profit"
                      : "border-terminal-700 bg-terminal-950 text-terminal-300 hover:text-terminal-100"
                  }`}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>

          <button
            type="button"
            disabled={busy}
            onClick={() => setAttempt((value) => value + 1)}
            className="rounded border border-terminal-700 px-3 py-2 font-mono text-xs text-terminal-200 hover:border-profit/50 hover:text-profit disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-profit"
          >
            {busy ? "Refreshing…" : "Refresh now"}
          </button>

          <fieldset className="min-w-0">
            <legend className="mb-1 text-[10px] font-medium uppercase tracking-[0.12em] text-terminal-500">
              EMA overlays
            </legend>
            <div className="flex flex-wrap gap-2">
              {EMA_PERIODS.map((period) => (
                <label key={period} className="inline-flex cursor-pointer items-center gap-1.5 rounded border border-terminal-800 bg-terminal-950 px-2 py-1.5 font-mono text-[11px] text-terminal-300">
                  <input
                    type="checkbox"
                    checked={activeEmas.includes(period)}
                    onChange={() => toggleEma(period)}
                    className="h-3.5 w-3.5 accent-[#10B981]"
                  />
                  EMA {period}
                </label>
              ))}
            </div>
          </fieldset>
          <p className="basis-full text-[11px] text-terminal-500">
            EMAs are derived client-side from the returned native closes only; they are not provider observations.
            Missing bars remain gaps and are never filled or interpolated.
          </p>
        </section>

        {error && activeSnapshot && (
          <section role="alert" className="rounded border border-warning/40 bg-warning-bg/20 p-4">
            <p className="font-mono text-sm font-semibold text-warning">Refresh failed</p>
            <p className="mt-1 text-xs text-terminal-200">{errorCopy(error)}</p>
            <p className="mt-2 text-[11px] text-terminal-400">
              The last successful snapshot remains visible. Its status row shows the snapshot&apos;s own retrieval time and freshness;
              it is not relabelled as current.
              {retryIn !== null ? ` Automatic retry in ${retryIn}s.` : ""}
            </p>
          </section>
        )}

        {error && !activeSnapshot && (
          <section role="alert" className="space-y-3 rounded-lg border border-warning/40 bg-terminal-900 p-5">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-mono text-sm font-semibold text-terminal-100">Candles unavailable</h2>
              <StatusPill label="NO SUBSTITUTE DATA" variant="warning" />
            </div>
            <p className="text-sm text-terminal-300">{errorCopy(error)}</p>
            <p className="text-xs text-terminal-500">
              No candles, quotes, or indicators are synthesized in the browser.
              {retryIn !== null ? ` Automatic retry in ${retryIn}s.` : ""}
            </p>
            <div className="flex flex-wrap gap-2">
              {error.code === "authentication_required" ? (
                <Link
                  href="/login"
                  className="rounded border border-terminal-600 px-4 py-2 text-sm text-terminal-100 hover:bg-terminal-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-profit"
                >
                  Sign in again
                </Link>
              ) : (
                <button
                  type="button"
                  onClick={() => setAttempt((value) => value + 1)}
                  className="rounded border border-terminal-600 px-4 py-2 text-sm text-terminal-100 hover:bg-terminal-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-profit"
                >
                  Retry candles
                </button>
              )}
            </div>
          </section>
        )}

        {loading && !activeSnapshot && (
          <section role="status" aria-busy="true" className="grid h-[330px] place-items-center rounded-lg border border-terminal-800 bg-terminal-900/40 px-6 text-center sm:h-[440px]">
            <div>
              <p className="font-mono text-sm text-terminal-200">Loading authenticated {symbol} {interval} candles…</p>
              <p className="mt-2 text-xs text-terminal-500">Validating the complete AlphaOS candle snapshot before rendering.</p>
            </div>
          </section>
        )}

        {activeSnapshot && activeSnapshot.candles.length === 0 && (
          <section role="status" className="rounded-lg border border-warning/30 bg-terminal-900 p-5">
            <h2 className="font-mono text-sm font-semibold text-terminal-100">No native candles returned</h2>
            <p className="mt-1 text-xs text-terminal-300">
              The provider snapshot contains zero bars. No empty range is filled with synthetic candles or carried over from another timeframe.
            </p>
          </section>
        )}

        {activeSnapshot && activeSnapshot.candles.length > 0 && (
          <section
            aria-label={`${symbol} ${interval} native candle chart`}
            aria-busy={busy}
            data-snapshot-id={activeSnapshot.snapshot_id}
            data-interval={interval}
            className="relative min-w-0"
          >
            {busy && (
              <p role="status" className="mb-2 text-right font-mono text-[11px] text-terminal-400">
                Refreshing · last snapshot remains visible
              </p>
            )}
            <LightweightCandleChart
              series={chartSeries}
              activeEmas={activeEmas}
              quote={quoteMarker}
              label={`${symbol} ${interval} candlesticks with volume, UTC time scale, snapshot ${activeSnapshot.snapshot_id.slice(0, 12)}, ${activeSnapshot.returned_bars} native bars`}
            />
            <p className="mt-2 text-[10px] text-terminal-500">
              Time axis is UTC. Volume is in the lower pane. Gaps in the returned timestamps remain visible.
            </p>
          </section>
        )}

        {activeSnapshot && (
          <section aria-label="Candle snapshot status" aria-live="polite" className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-mono text-sm font-bold text-terminal-100">Snapshot status</h2>
              <StatusPill
                label={`${(activeSnapshot.freshness === "latest_available" ? "latest available" : activeSnapshot.freshness).toUpperCase()} SNAPSHOT`}
                variant={severe ? "warning" : activeSnapshot.freshness === "fresh" ? "live" : "neutral"}
              />
              {activeSnapshot.completeness !== "complete" && (
                <StatusPill label={activeSnapshot.completeness.toUpperCase()} variant="warning" />
              )}
            </div>

            <dl className="grid min-w-0 grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
              <StatusMetric label="Provider" value={activeSnapshot.provider} />
              <StatusMetric label="Snapshot retrieved" value={formatUtc(activeSnapshot.retrieved_at)} />
              <StatusMetric
                label="Freshness age"
                value={`${activeSnapshot.freshness} · ${formatAge(snapshotAge)}`}
              />
              <StatusMetric label="Last bar" value={lastBarLabel(activeSnapshot)} />
              <StatusMetric label="Completeness" value={completenessLabel(activeSnapshot)} />
              <StatusMetric
                label="Snapshot ID"
                value={`${activeSnapshot.snapshot_id.slice(0, 12)}…`}
                title={activeSnapshot.snapshot_id}
              />
            </dl>

            <div className="rounded border border-terminal-800 bg-terminal-950/60 p-3">
              <p className="text-[10px] font-medium uppercase tracking-[0.12em] text-terminal-500">Quality warnings</p>
              {activeSnapshot.warnings.length > 0 ? (
                <div role="list" aria-label="Candle quality warnings" className="mt-2 flex flex-wrap gap-2">
                  {activeSnapshot.warnings.map((warning) => (
                    <span
                      key={warning}
                      role="listitem"
                      className="rounded-full border border-warning/40 bg-warning-bg/30 px-2.5 py-1 font-mono text-[11px] text-warning"
                      title={warning}
                    >
                      {warningLabel(warning)}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="mt-2 font-mono text-xs text-terminal-300">No candle warnings reported.</p>
              )}
              <p className="mt-2 text-[10px] text-terminal-500">
                Missing bars and incomplete sessions are reported by the server; the chart does not repair them.
              </p>
            </div>
          </section>
        )}

        <section aria-label="Current quote marker" className="rounded-lg border border-terminal-800 bg-terminal-900/50 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-mono text-sm font-bold text-terminal-100">Current quote marker</h2>
            <StatusPill
              label={quote?.status === "fresh" ? "SEPARATE FROM CANDLES" : "QUOTE UNAVAILABLE"}
              variant={quote?.status === "fresh" && quoteAge !== null && quoteAge <= 15 ? "live" : "neutral"}
            />
          </div>
          {quote?.status === "fresh" ? (
            <div className="mt-3 grid min-w-0 grid-cols-2 gap-2 sm:grid-cols-4">
              <StatusMetric label="Last" value={formatPrice(quote.last)} />
              <StatusMetric label="Bid / ask" value={`${formatPrice(quote.bid)} / ${formatPrice(quote.ask)}`} />
              <StatusMetric label="Quote time" value={formatUtc(quote.lastAt)} />
              <StatusMetric
                label="Quote freshness"
                value={`${formatAge(quoteAge)}${quoteAge !== null && quoteAge > 15 ? " · stale" : ""}`}
              />
              <p className="col-span-2 text-[11px] text-terminal-500 sm:col-span-4">
                The marker uses the authenticated quote surface and its own timestamp. It is never merged into the last candle,
                and candle freshness is reported separately above.
              </p>
            </div>
          ) : (
            <div className="mt-3 space-y-2">
              <p className="text-xs text-terminal-300">
                {quote?.status === "unavailable" ? quote.reason : "Waiting for a current quote."}
              </p>
              <p className="text-[11px] text-terminal-500">
                Candle rendering continues independently. No quote price is inserted into the candle series.
              </p>
            </div>
          )}
        </section>

        <footer className="space-y-1 border-t border-terminal-800 pt-4 text-[10px] leading-relaxed text-terminal-500">
          <p>
            Charts by{" "}
            <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer" className="text-terminal-300 underline underline-offset-2">
              TradingView
            </a>
            . TradingView Lightweight Charts™ Copyright (c) 2023 TradingView, Inc. Licensed under Apache-2.0.{" "}
            <a href="/licenses/lightweight-charts.txt" className="text-terminal-300 underline underline-offset-2">License</a>.
          </p>
          <p>
            AlphaOS renders only the returned native SPY/QQQ observations. No browser-side gap filling, interpolation, relabelling,
            quote-to-candle synthesis, order execution, or public redistribution is performed.
          </p>
        </footer>
      </div>
    </div>
  );
}
