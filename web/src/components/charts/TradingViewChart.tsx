"use client";

import { useEffect, useRef, useState } from "react";
import { CHART_INTERVALS, type ChartInterval, type ChartSymbol } from "@/lib/chart-types";

/**
 * Official TradingView Advanced Chart widget (`tv.js`). The widget is an
 * embedded visual component only: AlphaOS never reads its candles, indicators,
 * drawings or state, and the widget symbol can only be changed through the
 * AlphaOS symbol selector so the page and the assistant cannot disagree.
 */
const TRADINGVIEW_SYMBOL: Record<ChartSymbol, string> = {
  SPY: "AMEX:SPY",
  QQQ: "NASDAQ:QQQ",
};

const SCRIPT_ID = "tradingview-advanced-chart";
const SCRIPT_SRC = "https://s3.tradingview.com/tv.js";
const CONTAINER_ID = "alphaos-tradingview-chart";

declare global {
  interface Window {
    TradingView?: {
      widget: new (options: Record<string, unknown>) => unknown;
    };
  }
}

let scriptPromise: Promise<void> | null = null;

function loadWidgetScript(): Promise<void> {
  if (typeof window === "undefined") return Promise.reject(new Error("no browser"));
  if (window.TradingView?.widget) return Promise.resolve();
  if (scriptPromise) return scriptPromise;

  scriptPromise = new Promise<void>((resolve, reject) => {
    const existing = document.getElementById(SCRIPT_ID) as HTMLScriptElement | null;
    if (existing) {
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener("error", () => {
        scriptPromise = null;
        reject(new Error("TradingView script failed"));
      }, { once: true });
      return;
    }
    const script = document.createElement("script");
    script.id = SCRIPT_ID;
    script.src = SCRIPT_SRC;
    script.async = true;
    script.addEventListener("load", () => resolve(), { once: true });
    script.addEventListener("error", () => {
      scriptPromise = null;
      reject(new Error("TradingView script failed"));
    }, { once: true });
    document.head.appendChild(script);
  });
  return scriptPromise;
}

type WidgetStatus = "loading" | "ready" | "unavailable";

export function TradingViewChart({
  symbol,
  interval,
  onIntervalChange,
}: {
  symbol: ChartSymbol;
  interval: ChartInterval;
  onIntervalChange: (interval: ChartInterval) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [status, setStatus] = useState<WidgetStatus>("loading");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let active = true;

    setStatus((current) => (current === "unavailable" ? "loading" : current));

    void loadWidgetScript()
      .then(() => {
        if (!active) return;
        if (!window.TradingView?.widget) {
          setStatus("unavailable");
          return;
        }
        container.innerHTML = "";
        try {
          new window.TradingView.widget({
            container_id: CONTAINER_ID,
            autosize: true,
            symbol: TRADINGVIEW_SYMBOL[symbol],
            interval,
            timezone: "America/New_York",
            theme: "dark",
            style: "1",
            locale: "en",
            toolbar_bg: "#0D1117",
            backgroundColor: "#080B10",
            gridColor: "rgba(36, 48, 66, 0.35)",
            enable_publishing: false,
            allow_symbol_change: false,
            hide_side_toolbar: false,
            withdateranges: true,
            details: true,
            save_image: false,
            studies: ["Volume@tv-basicstudies", "RSI@tv-basicstudies"],
          });
          setStatus("ready");
        } catch {
          setStatus("unavailable");
        }
      })
      .catch(() => {
        if (active) setStatus("unavailable");
      });

    return () => {
      active = false;
      container.innerHTML = "";
    };
  }, [symbol, interval, attempt]);

  return (
    <section
      aria-label="TradingView advanced chart"
      className="rounded border border-terminal-800 bg-terminal-900 p-3 sm:p-4 space-y-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div
          role="group"
          aria-label="Chart timeframe"
          className="flex flex-wrap gap-1"
        >
          {CHART_INTERVALS.map((item) => (
            <button
              key={item.value}
              type="button"
              aria-pressed={interval === item.value}
              onClick={() => onIntervalChange(item.value)}
              className={`rounded border px-2.5 py-1 font-mono text-[11px] transition-colors ${
                interval === item.value
                  ? "border-profit/40 bg-profit-bg text-profit"
                  : "border-terminal-800 bg-terminal-950 text-terminal-400 hover:text-terminal-200"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
        <a
          href={`https://www.tradingview.com/chart/?symbol=${encodeURIComponent(TRADINGVIEW_SYMBOL[symbol])}`}
          target="_blank"
          rel="noopener noreferrer"
          className="font-mono text-[11px] text-terminal-400 underline decoration-terminal-600 hover:text-terminal-200"
        >
          Open in TradingView
        </a>
      </div>

      <div className="relative h-[360px] overflow-hidden rounded border border-terminal-800 bg-terminal-950 sm:h-[440px] xl:h-[560px]">
        <div
          id={CONTAINER_ID}
          ref={containerRef}
          className="absolute inset-0"
          data-tv-symbol={TRADINGVIEW_SYMBOL[symbol]}
          data-tv-interval={interval}
        />
        {status === "loading" && (
          <p
            role="status"
            className="absolute inset-0 flex items-center justify-center p-6 text-center font-mono text-xs text-terminal-400"
          >
            Loading the TradingView advanced chart…
          </p>
        )}
        {status === "unavailable" && (
          <div
            role="status"
            className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-6 text-center"
          >
            <p className="font-mono text-xs text-warning">
              The TradingView widget could not be loaded. This page never
              substitutes its own chart or prices.
            </p>
            <p className="font-mono text-[11px] text-terminal-400">
              A browser extension, network policy or CSP may be blocking
              `s3.tradingview.com`. AlphaOS research and the assistant remain
              available.
            </p>
            <div className="flex flex-wrap items-center justify-center gap-2">
              <button
                type="button"
                onClick={() => setAttempt((value) => value + 1)}
                className="rounded border border-terminal-600 px-3 py-1.5 font-mono text-[11px] text-terminal-100 hover:bg-terminal-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-profit"
              >
                Retry chart
              </button>
              <a
                href={`https://www.tradingview.com/chart/?symbol=${encodeURIComponent(TRADINGVIEW_SYMBOL[symbol])}`}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded border border-terminal-700 px-3 py-1.5 font-mono text-[11px] text-terminal-300 hover:bg-terminal-800"
              >
                Open TradingView
              </a>
            </div>
          </div>
        )}
      </div>

      <p className="font-mono text-[11px] leading-relaxed text-terminal-500">
        Chart source: TradingView Advanced Chart widget ({TRADINGVIEW_SYMBOL[symbol]}).
        TradingView market data may be delayed, is provided under TradingView&apos;s
        terms, and is not an authorized AlphaOS market-data API. AlphaOS does not
        scrape, mirror or read this widget. Symbol changes are made only with the
        SPY/QQQ selector above.
      </p>
    </section>
  );
}
