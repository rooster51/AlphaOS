import { getServerConfig } from "@/lib/server-config";
import { currentQuote, quoteAgeLimit } from "@/lib/current-quotes";
import { CurrentQuoteCards } from "./CurrentQuoteCards";

export async function CurrentMarketQuotes() {
  const { base, token, diagnostics } = getServerConfig();
  const limit = quoteAgeLimit(process.env.ALPHAOS_CURRENT_QUOTE_MAX_AGE_SECONDS);
  const symbols = ["SPY", "QQQ"] as const;
  const quotes = await Promise.all(symbols.map(async symbol => {
    if (!base || !token || diagnostics.configuration !== "ready") return null;
    try {
      const response = await fetch(new URL(`/v1/quote/${symbol}?refresh=true`, base), {
        headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(5000),
      });
      if (!response.ok) return null;
      return currentQuote(await response.json(), symbol, Date.now(), limit);
    } catch {
      return null;
    }
  }));
  return <CurrentQuoteCards quotes={quotes} limit={limit} />;
}
