export const dynamic = "force-dynamic";

import { TradingWorkspace } from "@/components/workspace/TradingWorkspace";
import type { WorkspaceSymbol } from "@/lib/workspace-evidence";

export default async function WorkspacePage({
  searchParams,
}: {
  searchParams: Promise<{ symbol?: string }>;
}) {
  const params = await searchParams;
  const symbol: WorkspaceSymbol = params.symbol?.toUpperCase() === "QQQ" ? "QQQ" : "SPY";
  return <TradingWorkspace initialSymbol={symbol} />;
}
