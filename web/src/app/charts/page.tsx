export const dynamic = "force-dynamic";

import { ChartingAiWorkbench } from "@/components/charts/ChartingAiWorkbench";
import type { ChartSymbol } from "@/lib/chart-types";

export default async function ChartsPage({
  searchParams,
}: {
  searchParams: Promise<{ symbol?: string }>;
}) {
  const params = await searchParams;
  const requested = params?.symbol?.toUpperCase();
  const symbol: ChartSymbol = requested === "QQQ" ? "QQQ" : "SPY";
  return <ChartingAiWorkbench key={symbol} initialSymbol={symbol} />;
}
