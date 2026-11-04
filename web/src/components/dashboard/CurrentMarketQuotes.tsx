import { quoteAgeLimit } from "@/lib/current-quotes";
import { CurrentQuoteCards } from "./CurrentQuoteCards";

export function CurrentMarketQuotes() {
  return <CurrentQuoteCards limit={quoteAgeLimit(process.env.ALPHAOS_CURRENT_QUOTE_MAX_AGE_SECONDS)} />;
}
