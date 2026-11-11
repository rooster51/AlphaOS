export const dynamic = "force-dynamic";

import { Header } from "@/components/shell/Header";
import Link from "next/link";
import { CandleChartPanel } from "@/components/market/chart/CandleChartPanel";
import { TradingViewFallback } from "@/components/market/chart/TradingViewFallback";
import { CANDLE_INTERVALS, type CandleInterval, type CandleSymbol } from "@/lib/candles";

type ChartSearch = {
  symbol?: string;
  interval?: string;
  view?: string;
};

export default async function CandleChartPage({
  searchParams,
}: {
  searchParams: Promise<ChartSearch>;
}) {
  const params = await searchParams;
  const requested = params.symbol?.toUpperCase();
  const symbol: CandleSymbol = requested === "SPY" ? "SPY" : "QQQ";
  const requestedInterval = params.interval;
  const interval: CandleInterval = CANDLE_INTERVALS.includes(requestedInterval as CandleInterval)
    ? requestedInterval as CandleInterval
    : "1m";
  const legacy = process.env.ALPHAOS_CANDLE_CHART_ENABLED !== "true" || params.view === "legacy";

  if (requested !== undefined && requested !== "SPY" && requested !== "QQQ") {
    return (
      <div>
        <Header
          title="Candle Chart"
          subtitle="Authenticated provider-native candles"
          badge={{ label: "UNAVAILABLE", variant: "warning" }}
        />
        <section className="p-8" aria-live="polite">
          <div className="rounded border border-warning/30 bg-terminal-900 p-5">
            <h2 className="font-mono font-bold text-terminal-100">Unsupported symbol</h2>
            <p className="mt-2 font-mono text-sm text-terminal-300">The AlphaOS candle API supports SPY and QQQ only.</p>
            <Link href="/market/chart?symbol=SPY" className="mt-4 inline-block rounded border border-terminal-600 px-4 py-2 text-sm">
              Open SPY candles
            </Link>
          </div>
        </section>
      </div>
    );
  }

  if (legacy) {
    return (
      <div>
        <Header
          title={`Candle Chart — ${symbol}`}
          subtitle="Legacy external chart fallback"
          badge={{ label: "FALLBACK", variant: "warning" }}
        />
        <div className="mx-auto w-full max-w-[1440px] space-y-4 px-4 py-5 sm:px-6 sm:py-7 lg:px-8">
          <TradingViewFallback symbol={symbol} />
        </div>
      </div>
    );
  }

  return <CandleChartPanel symbol={symbol} initialInterval={interval} />;
}
