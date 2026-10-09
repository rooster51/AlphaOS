export const dynamic = "force-dynamic";
import Link from "next/link";
import { Header } from "@/components/shell/Header";
import { getMarketSnapshotServer } from "@/lib/alphaos-server";

export default async function DashboardPage() {
  const checks = await Promise.all(["QQQ", "SPY"].map(async (symbol) => {
    try {
      const response = await getMarketSnapshotServer(symbol);
      return { symbol, response };
    } catch {
      return { symbol, response: null };
    }
  }));

  return (
    <div>
      <Header title="Research Terminal Dashboard"
        subtitle="Evidence availability and read-only market research."
        badge={{ label: "READ-ONLY RESEARCH", variant: "neutral" }} />
      <div className="p-8 space-y-6">
        <p className="text-terminal-400 text-xs font-mono">
          Account balance, daily P&L, active risk limits, and trade journal state are unavailable
          until authenticated account data and enforcement are implemented. No demo balances
          or model predictions are represented as current.
        </p>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {checks.map(({ symbol, response }) => (
            <section key={symbol} className="bg-terminal-900 border border-terminal-800 rounded p-5 space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="font-mono font-bold text-terminal-100">{symbol}</h2>
                <span className="text-xs font-mono text-terminal-400">
                  {response?.isLive ? "VERIFIED UNDERLYING OBSERVATION" : response ? "DEMO ONLY" : "UNAVAILABLE"}
                </span>
              </div>
              {response ? (
                <>
                  <div className="font-mono text-lg text-terminal-100">
                    ${response.data.current_spot.toFixed(2)}
                  </div>
                  <p className="text-xs text-terminal-400 font-mono">
                    Observation: {response.data.as_of} · ATR: ${response.data.atr_14.toFixed(2)}
                  </p>
                  <p className="text-xs text-terminal-400 font-mono">
                    Direction: {response.data.opportunity_state.direction} ·
                    Premium: {response.data.opportunity_state.premium_state} ·
                    Volatility: {response.data.opportunity_state.volatility_state}
                  </p>
                  {response.warning && <p className="text-xs text-warning">{response.warning}</p>}
                </>
              ) : (
                <p className="font-mono text-xs text-warning">
                  No verified matching current market evidence. Nothing has been substituted.
                </p>
              )}
              <Link href={`/market?symbol=${symbol}`} className="text-xs text-accent underline">
                Open market research
              </Link>
            </section>
          ))}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 font-mono text-sm">
          <Link className="bg-terminal-900 rounded border border-terminal-800 p-4" href="/strategies">Strategy explorer — evidence-gated</Link>
          <Link className="bg-terminal-900 rounded border border-terminal-800 p-4" href="/session">Session evidence</Link>
          <Link className="bg-terminal-900 rounded border border-terminal-800 p-4" href="/journal">Journal — not connected</Link>
        </div>
      </div>
    </div>
  );
}
