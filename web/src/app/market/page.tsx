export const dynamic = "force-dynamic";
import { MarketUnavailable } from "@/components/market/MarketUnavailable";
import { MarketResearchPanel } from "@/components/market/MarketResearchPanel";

export default async function MarketResearchPage({
  searchParams,
}: {
  searchParams?: { symbol?: string };
}) {
  const requestedSymbol = searchParams?.symbol?.toUpperCase();
  const symbol = requestedSymbol === undefined || requestedSymbol === "QQQ" || requestedSymbol === "SPY"
    ? requestedSymbol ?? "QQQ" : null;
  if (!symbol) {
    return <MarketUnavailable symbol={requestedSymbol ?? "UNKNOWN"} reason="Unsupported market symbol." />;
  }
  return <MarketResearchPanel key={symbol} symbol={symbol} />;
}
