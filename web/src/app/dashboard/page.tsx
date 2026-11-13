
export const dynamic = "force-dynamic";

import Link from "next/link";
import { Suspense } from "react";
import { CurrentMarketQuotes } from "@/components/dashboard/CurrentMarketQuotes";
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

        <Suspense fallback={<p>Checking current Public quotes…</p>}>
          <CurrentMarketQuotes />
        </Suspense>

        <h2 className="text-lg font-semibold">Archived Research Evidence</h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <DashboardResearch symbol="QQQ" />
          <DashboardResearch symbol="SPY" />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 font-mono text-sm">
          <Link
            prefetch={false}
            className="bg-terminal-900 rounded border border-profit/30 p-4 text-profit"
            href="/workspace"
          >
            Trading workspace — chart, structure &amp; assistant
          </Link>

          <Link
            prefetch={false}
            className="bg-terminal-900 rounded border border-terminal-800 p-4"
            href="/strategies"
          >
            Strategy explorer — evidence-gated
          </Link>

          <Link
            prefetch={false}
            className="bg-terminal-900 rounded border border-terminal-800 p-4"
            href="/session"
          >
            Session evidence
          </Link>

          <Link
            prefetch={false}
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
