import React from "react";
import { Header } from "@/components/shell/Header";
import { MetricCard } from "@/components/ui/MetricCard";
import { StatusPill } from "@/components/shell/StatusPill";
import { getMarketSnapshotServer } from "@/lib/alphaos-server";
import { MOCK_GUARDRAILS, MOCK_CANDIDATES } from "@/lib/mock-data";
import Link from "next/link";
import {
  ArrowRight,
  TrendingUp,
  Activity,
  Layers,
  Shield,
  Clock,
  Compass,
} from "lucide-react";

export default async function DashboardPage() {
  const qqqSnapshot = await getMarketSnapshotServer("QQQ");
  const spySnapshot = await getMarketSnapshotServer("SPY");

  return (
    <div>
      <Header
        title="Research Terminal Dashboard"
        subtitle="Live state classification, deterministic strategy routing, and discipline guardrails."
        badge={{
          label: qqqSnapshot.isLive ? "API CONNECTED" : "RESEARCH FIXTURE",
          variant: qqqSnapshot.isLive ? "live" : "mock",
        }}
      />

      <div className="p-8 space-y-6">
        {/* Top Operational Metrics */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <MetricCard
            label="Monitored Symbols"
            value="QQQ / SPY"
            subValue="ETF Universe"
            trend="neutral"
            caption="Verified minute archive ingest"
          />
          <MetricCard
            label="Capital Budget Cap"
            value={`$${MOCK_GUARDRAILS.default_account_size.toLocaleString()}`}
            subValue="Sizing Base"
            trend="neutral"
            caption="Default account configuration"
          />
          <MetricCard
            label="Max Daily Loss Limit"
            value={`$${((MOCK_GUARDRAILS.default_account_size * MOCK_GUARDRAILS.max_daily_loss_pct) / 100).toFixed(0)}`}
            subValue={`${MOCK_GUARDRAILS.max_daily_loss_pct}% Guardrail`}
            trend="bearish"
            caption="Hard stop discipline rule"
          />
          <MetricCard
            label="Strategy Routes"
            value={MOCK_CANDIDATES.length}
            subValue="Unranked"
            trend="bullish"
            caption="Directional, income & neutral"
          />
        </div>

        {/* Active Market Regimes (QQQ & SPY) */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* QQQ Snapshot Card */}
          <div className="bg-terminal-900 border border-terminal-800 rounded p-6">
            <div className="flex items-start justify-between mb-4">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-lg font-bold text-terminal-100">
                    QQQ
                  </span>
                  <span className="font-mono text-xs text-terminal-400 font-numeric">
                    ${qqqSnapshot.data.current_spot.toFixed(2)}
                  </span>
                </div>
                <div className="text-xs font-mono text-terminal-400 mt-0.5">
                  ATR(14): ${qqqSnapshot.data.atr_14.toFixed(2)} • 1-Day Expected Move: ${qqqSnapshot.data.expected_move?.toFixed(2) || "N/A"}
                </div>
              </div>
              <StatusPill
                label={qqqSnapshot.data.opportunity_state.movement_state.toUpperCase()}
                variant="archive"
              />
            </div>

            {/* State Envelope Dimensions */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 my-4 font-mono text-xs">
              <div className="bg-terminal-950 p-2.5 rounded border border-terminal-850">
                <span className="text-[10px] text-terminal-500 uppercase block">Direction</span>
                <span className="font-semibold text-profit capitalize">
                  {qqqSnapshot.data.opportunity_state.direction}
                </span>
              </div>
              <div className="bg-terminal-950 p-2.5 rounded border border-terminal-850">
                <span className="text-[10px] text-terminal-500 uppercase block">Premium</span>
                <span className="font-semibold text-warning capitalize">
                  {qqqSnapshot.data.opportunity_state.premium_state}
                </span>
              </div>
              <div className="bg-terminal-950 p-2.5 rounded border border-terminal-850">
                <span className="text-[10px] text-terminal-500 uppercase block">Volatility</span>
                <span className="font-semibold text-accent capitalize">
                  {qqqSnapshot.data.opportunity_state.volatility_state}
                </span>
              </div>
              <div className="bg-terminal-950 p-2.5 rounded border border-terminal-850">
                <span className="text-[10px] text-terminal-500 uppercase block">Time State</span>
                <span className="font-semibold text-terminal-300 capitalize">
                  {qqqSnapshot.data.opportunity_state.time_state}
                </span>
              </div>
            </div>

            <div className="text-[11px] font-mono text-terminal-400 bg-terminal-950/70 p-3 rounded border border-terminal-850 mb-4">
              <span className="text-terminal-300 font-semibold">Evidence: </span>
              {qqqSnapshot.data.opportunity_state.evidence.breakout_status || "Standard trend alignment"}
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-terminal-800">
              <span className="text-xs font-mono text-terminal-500">
                As of {new Date(qqqSnapshot.data.as_of).toLocaleTimeString()}
              </span>
              <Link
                href="/market?symbol=QQQ"
                className="text-xs font-mono text-profit hover:underline flex items-center gap-1"
              >
                Deep Market Research <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          </div>

          {/* SPY Snapshot Card */}
          <div className="bg-terminal-900 border border-terminal-800 rounded p-6">
            <div className="flex items-start justify-between mb-4">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-lg font-bold text-terminal-100">
                    SPY
                  </span>
                  <span className="font-mono text-xs text-terminal-400 font-numeric">
                    ${spySnapshot.data.current_spot.toFixed(2)}
                  </span>
                </div>
                <div className="text-xs font-mono text-terminal-400 mt-0.5">
                  ATR(14): ${spySnapshot.data.atr_14.toFixed(2)} • 1-Day Expected Move: ${spySnapshot.data.expected_move?.toFixed(2) || "N/A"}
                </div>
              </div>
              <StatusPill
                label={spySnapshot.data.opportunity_state.movement_state.toUpperCase()}
                variant="archive"
              />
            </div>

            {/* State Envelope Dimensions */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 my-4 font-mono text-xs">
              <div className="bg-terminal-950 p-2.5 rounded border border-terminal-850">
                <span className="text-[10px] text-terminal-500 uppercase block">Direction</span>
                <span className="font-semibold text-profit capitalize">
                  {spySnapshot.data.opportunity_state.direction}
                </span>
              </div>
              <div className="bg-terminal-950 p-2.5 rounded border border-terminal-850">
                <span className="text-[10px] text-terminal-500 uppercase block">Premium</span>
                <span className="font-semibold text-warning capitalize">
                  {spySnapshot.data.opportunity_state.premium_state}
                </span>
              </div>
              <div className="bg-terminal-950 p-2.5 rounded border border-terminal-850">
                <span className="text-[10px] text-terminal-500 uppercase block">Volatility</span>
                <span className="font-semibold text-accent capitalize">
                  {spySnapshot.data.opportunity_state.volatility_state}
                </span>
              </div>
              <div className="bg-terminal-950 p-2.5 rounded border border-terminal-850">
                <span className="text-[10px] text-terminal-500 uppercase block">Time State</span>
                <span className="font-semibold text-terminal-300 capitalize">
                  {spySnapshot.data.opportunity_state.time_state}
                </span>
              </div>
            </div>

            <div className="text-[11px] font-mono text-terminal-400 bg-terminal-950/70 p-3 rounded border border-terminal-850 mb-4">
              <span className="text-terminal-300 font-semibold">Evidence: </span>
              Completed close above EMA 9, 21, and 50.
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-terminal-800">
              <span className="text-xs font-mono text-terminal-500">
                As of {new Date(spySnapshot.data.as_of).toLocaleTimeString()}
              </span>
              <Link
                href="/market?symbol=SPY"
                className="text-xs font-mono text-profit hover:underline flex items-center gap-1"
              >
                Deep Market Research <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          </div>
        </div>

        {/* Quick Route Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Link
            href="/strategies"
            className="p-5 rounded bg-terminal-900 border border-terminal-800 hover:border-terminal-700 transition group"
          >
            <div className="flex items-center justify-between mb-2">
              <Compass className="w-5 h-5 text-profit" />
              <ArrowRight className="w-4 h-4 text-terminal-500 group-hover:text-profit transition-colors" />
            </div>
            <h3 className="font-mono text-sm font-semibold text-terminal-100">
              Strategy Explorer
            </h3>
            <p className="text-xs font-mono text-terminal-400 mt-1">
              Unranked multi-strategy candidates with capital budget filters, breakevens, and payoff charts.
            </p>
          </Link>

          <Link
            href="/session"
            className="p-5 rounded bg-terminal-900 border border-terminal-800 hover:border-terminal-700 transition group"
          >
            <div className="flex items-center justify-between mb-2">
              <Clock className="w-5 h-5 text-warning" />
              <ArrowRight className="w-4 h-4 text-terminal-500 group-hover:text-warning transition-colors" />
            </div>
            <h3 className="font-mono text-sm font-semibold text-terminal-100">
              Session Review
            </h3>
            <p className="text-xs font-mono text-terminal-400 mt-1">
              Inspect NYSE trading sessions, 0DTE time-of-day bounds, and quote freshness telemetry.
            </p>
          </Link>

          <Link
            href="/risk"
            className="p-5 rounded bg-terminal-900 border border-terminal-800 hover:border-terminal-700 transition group"
          >
            <div className="flex items-center justify-between mb-2">
              <Shield className="w-5 h-5 text-accent" />
              <ArrowRight className="w-4 h-4 text-terminal-500 group-hover:text-accent transition-colors" />
            </div>
            <h3 className="font-mono text-sm font-semibold text-terminal-100">
              Portfolio & Risk
            </h3>
            <p className="text-xs font-mono text-terminal-400 mt-1">
              Deterministic expiration risk envelopes and discipline loss-cap monitoring.
            </p>
          </Link>
        </div>
      </div>
    </div>
  );
}
