import Link from "next/link";
import { CANDLE_SYMBOLS, type CandleInterval, type CandleSymbol } from "@/lib/candles";

const researchLink = "rounded border border-terminal-800 px-3 py-1.5 font-mono text-xs text-terminal-400 hover:border-terminal-600 hover:text-terminal-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-profit";

export function ChartResearchNavigation({ symbol, interval, legacy = false }: {
  symbol: CandleSymbol;
  interval: CandleInterval;
  legacy?: boolean;
}) {
  return (
    <nav aria-label="Candle symbol and related research" className="flex flex-wrap items-center gap-2">
      {CANDLE_SYMBOLS.map((item) => (
        <Link
          prefetch={false}
          key={item}
          href={`/market/chart?symbol=${item}&interval=${interval}${legacy ? "&view=legacy" : ""}`}
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
        className={researchLink}
      >
        Archive research
      </Link>
      <Link prefetch={false} href={`/workspace?symbol=${symbol}`} className={researchLink}>Trade research</Link>
      <Link prefetch={false} href={`/options?symbol=${symbol}`} className={researchLink}>Options research</Link>
      {!legacy && <Link prefetch={false} href={`/market/chart?symbol=${symbol}&interval=${interval}&view=legacy`} className={researchLink}>TradingView fallback</Link>}
    </nav>
  );
}
