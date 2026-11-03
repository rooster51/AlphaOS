export const dynamic = "force-dynamic";
import { MarketUnavailable } from "@/components/market/MarketUnavailable";
import { StrategyResearchDashboard } from "@/components/market/StrategyResearchDashboard";

export default async function StrategyResearchPage({
  searchParams,
}: {
  searchParams: Promise<{ symbol?: string }>;
}) {
  const params = await searchParams;
  const requestedSymbol = params?.symbol?.toUpperCase();
  const symbol =
    requestedSymbol === undefined || requestedSymbol === "QQQ" || requestedSymbol === "SPY"
      ? requestedSymbol ?? "QQQ"
      : null;

  if (!symbol) {
    return <MarketUnavailable symbol={requestedSymbol ?? "UNKNOWN"} reason="Unsupported market symbol." />;
  }

  return <StrategyResearchDashboard initialSymbol={symbol} />;
}
