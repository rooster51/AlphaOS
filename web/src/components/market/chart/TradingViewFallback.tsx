import Link from "next/link";
import type { CandleSymbol } from "@/lib/candles";
import { tradingViewEmbedUrl, tradingViewSymbol } from "@/lib/tradingview";

/**
 * Route-level rollback. The archive page never used an embedded TradingView
 * widget, so this minimal external embed is the legacy chart available when
 * ALPHAOS_CANDLE_CHART_ENABLED=false or ?view=legacy is requested.
 */
export function TradingViewFallback({ symbol }: { symbol: CandleSymbol }) {
  const src = tradingViewEmbedUrl(symbol);
  return (
    <div className="space-y-4">
      <p className="rounded border border-warning/30 bg-warning-bg/20 p-4 font-mono text-xs text-terminal-300">
        First-party AlphaOS candles are disabled on this route. The external TradingView widget
        below is the legacy fallback; it is not sourced from the authenticated AlphaOS candle API
        and may not reflect this account&apos;s provider entitlement.
      </p>
      <div className="overflow-hidden rounded-lg border border-terminal-800 bg-terminal-950">
        <iframe
          title={`TradingView ${tradingViewSymbol(symbol)} legacy chart`}
          src={src}
          className="block h-[420px] w-full sm:h-[560px]"
          loading="lazy"
          referrerPolicy="strict-origin-when-cross-origin"
        />
      </div>
      <Link
        href={`/market/chart?symbol=${symbol}`}
        prefetch={false}
        className="inline-flex rounded border border-terminal-700 px-3 py-2 font-mono text-xs text-terminal-200 hover:border-profit/50 hover:text-profit focus-visible:outline focus-visible:outline-2 focus-visible:outline-profit"
      >
        Open full candle route
      </Link>
    </div>
  );
}
