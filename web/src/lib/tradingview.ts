/**
 * TradingView's symbol format is exchange-qualified. SPY is listed on NYSE
 * Arca (TradingView prefix AMEX); QQQ is listed on Nasdaq (prefix NASDAQ).
 * Using one hardcoded exchange for both symbols is what produced the
 * "This symbol doesn't exist" error for QQQ.
 */
export type TradingViewSymbol = "SPY" | "QQQ";

const EXCHANGES: Record<TradingViewSymbol, string> = {
  SPY: "AMEX",
  QQQ: "NASDAQ",
};

export function tradingViewSymbol(symbol: TradingViewSymbol): string {
  return `${EXCHANGES[symbol]}:${symbol}`;
}

export function tradingViewEmbedUrl(
  symbol: TradingViewSymbol,
  interval: "1" | "5" | "15" = "5",
): string {
  const qualified = encodeURIComponent(tradingViewSymbol(symbol));
  return `https://s.tradingview.com/widgetembed/?symbol=${qualified}&interval=${interval}&hidesidetoolbar=1&symboledit=0&saveimage=0&toolbarbg=080b10&theme=dark&style=1&timezone=Etc%2FUTC&locale=en`;
}
