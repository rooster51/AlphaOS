import { getServerConfig } from "@/lib/server-config";
import { currentQuote, quoteAgeLimit, quoteHttpFailure, unavailable } from "@/lib/current-quotes";
import { CurrentQuoteCards } from "./CurrentQuoteCards";

export async function CurrentMarketQuotes() {
  const { base, token, diagnostics } = getServerConfig();
  const limit = quoteAgeLimit(process.env.ALPHAOS_CURRENT_QUOTE_MAX_AGE_SECONDS);
  const symbols = ["SPY", "QQQ"] as const;
  const quotes = await Promise.all(symbols.map(async symbol => {
    if (!base || !token || diagnostics.configuration !== "ready") return unavailable("Preview quote backend is not configured.");
    try {
      const response = await fetch(new URL(`/v1/quote/${symbol}?refresh=true`, base), {
        headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(5000),
      });
      const payload: unknown = await response.json().catch(error => {
        if (error instanceof SyntaxError) return null;
        throw error;
      });
      if (!response.ok) return quoteHttpFailure(response.status, payload);
      if (payload === null) return unavailable("Quote backend response could not be read.");
      return currentQuote(payload, symbol, Date.now(), limit);
    } catch (error) {
      return unavailable(error instanceof DOMException && error.name === "TimeoutError"
        ? "Quote backend request timed out." : "Quote backend could not be reached.");
    }
  }));
  return <CurrentQuoteCards quotes={quotes} limit={limit} />;
}
