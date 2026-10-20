
export const dynamic = "force-dynamic";

import Link from "next/link";
import { Header } from "@/components/shell/Header";
import { DashboardResearch } from "@/components/dashboard/DashboardResearch";

export default function DashboardPage() {
  return (
    <div>
      <Header
        title="Research Terminal Dashboard"
        subtitle="Evidence availability and read-only market research."
        badge={{
          label: "READ-ONLY RESEARCH",
          variant: "neutral",
        }}
      />

      <div className="p-8 space-y-6">
        <p className="text-terminal-400 text-xs font-mono">
          Account balance, daily P&amp;L, active risk limits, and trade
          journal state are unavailable until authenticated account data
          and enforcement are implemented. No demo balances or model
          predictions are represented as current.
        </p>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <DashboardResearch symbol="QQQ" />
          <DashboardResearch symbol="SPY" />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 font-mono text-sm">
          <Link
            className="bg-terminal-900 rounded border border-terminal-800 p-4"
            href="/strategies"
          >
            Strategy explorer — evidence-gated
          </Link>

          <Link
            className="bg-terminal-900 rounded border border-terminal-800 p-4"
            href="/session"
          >
            Session evidence
          </Link>

          <Link
            className="bg-terminal-900 rounded border border-terminal-800 p-4"
            href="/journal"
          >
            Journal — not connected
          </Link>
        </div>
      </div>
    </div>
  );
}
