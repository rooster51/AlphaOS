export const dynamic = "force-dynamic";
import React from "react";
import { Header } from "@/components/shell/Header";
import { StatusPill } from "@/components/shell/StatusPill";
import { MetricCard } from "@/components/ui/MetricCard";
import { getMarketSnapshotServer } from "@/lib/alphaos-server";
import Link from "next/link";
import { ShieldAlert, BarChart3, Info } from "lucide-react";

export default async function MarketResearchPage({
  searchParams,
}: {
  searchParams?: { symbol?: string };
}) {
  const symbol = searchParams?.symbol?.toUpperCase() === "SPY" ? "SPY" : "QQQ";
  const { data: snapshot, isLive, warning } = await getMarketSnapshotServer(symbol);

  return (
    <div>
      <Header
        title={`Market Research — ${symbol}`}
        subtitle="Opportunity classification envelope, ATR structural levels, and historical analogs."
        badge={{
          label: isLive ? "FRESH UNDERLYING" : "DEMO — NOT LIVE",
          variant: isLive ? "archive" : "mock",
        }}
      />

      <div className="p-8 space-y-6">
        {warning && (
          <div className="bg-warning-bg border border-warning/30 rounded p-4 flex items-start gap-3 text-warning font-mono text-xs">
            <Info className="w-4 h-4 shrink-0 mt-0.5" />
            <div>
              <span className="font-bold">Notice: </span> {warning}
            </div>
          </div>
        )}

        {/* Symbol Selector bar */}
        <div className="flex items-center gap-3">
          <span className="font-mono text-xs text-terminal-400">SELECT SYMBOL:</span>
          {["QQQ", "SPY"].map((s) => (
            <Link
              key={s}
              href={`/market?symbol=${s}`}
              className={`font-mono text-xs font-bold px-3 py-1.5 rounded transition ${
                s === symbol
                  ? "bg-profit-bg text-profit border border-profit/40"
                  : "bg-terminal-900 text-terminal-400 border border-terminal-800 hover:text-terminal-200"
              }`}
            >
              {s}
            </Link>
          ))}
        </div>

        {/* Key Market Metrics */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <MetricCard
            label={`${symbol} Current Spot`}
            value={`$${snapshot.current_spot.toFixed(2)}`}
            subValue={isLive ? "Fresh provider observation" : "Synthetic demo value"}
            trend="neutral"
            caption="Not an executable options quote"
          />
          <MetricCard
            label="ATR (14 Session)"
            value={`$${snapshot.atr_14.toFixed(2)}`}
            subValue={`${((snapshot.atr_14 / snapshot.current_spot) * 100).toFixed(2)}% of Spot`}
            trend="neutral"
            caption="True Range volatility envelope"
          />
          <MetricCard
            label="Expected 1-Day Move"
            value={snapshot.expected_move ? `±$${snapshot.expected_move.toFixed(2)}` : "Unavailable"}
            subValue="Not verified"
            trend="neutral"
            caption="Unavailable without matching option evidence"
          />
          <MetricCard
            label="Movement Regime"
            value={snapshot.opportunity_state.movement_state.toUpperCase()}
            subValue={snapshot.opportunity_state.direction.toUpperCase()}
            trend="neutral"
            caption="Unknown until supported by evidence"
          />
        </div>

        {/* Opportunity State Envelope */}
        <div className="bg-terminal-900 border border-terminal-800 rounded p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="font-mono text-sm font-bold text-terminal-100 uppercase tracking-wide">
                Simultaneous Market State Envelope
              </h2>
              <p className="text-xs font-mono text-terminal-400 mt-0.5">
                Only observed and validated dimensions are shown. Unverified classifications remain unknown.
              </p>
            </div>
            <StatusPill label="5-DIMENSIONAL" variant="neutral" />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-5 gap-3 my-4 font-mono text-xs">
            <div className="bg-terminal-950 p-3 rounded border border-terminal-850">
              <span className="text-[10px] text-terminal-500 uppercase block">1. Direction</span>
              <span className="text-sm font-bold text-profit capitalize block mt-1">
                {snapshot.opportunity_state.direction}
              </span>
              <span className="text-[10px] text-terminal-500 mt-1 block">EMA alignment requires independently validated bars</span>
            </div>

            <div className="bg-terminal-950 p-3 rounded border border-terminal-850">
              <span className="text-[10px] text-terminal-500 uppercase block">2. Premium State</span>
              <span className="text-sm font-bold text-warning capitalize block mt-1">
                {snapshot.opportunity_state.premium_state}
              </span>
              <span className="text-[10px] text-terminal-500 mt-1 block">IV/RV comparison not yet available</span>
            </div>

            <div className="bg-terminal-950 p-3 rounded border border-terminal-850">
              <span className="text-[10px] text-terminal-500 uppercase block">3. Movement State</span>
              <span className="text-sm font-bold text-accent capitalize block mt-1">
                {snapshot.opportunity_state.movement_state}
              </span>
              <span className="text-[10px] text-terminal-500 mt-1 block">Validated regime data required</span>
            </div>

            <div className="bg-terminal-950 p-3 rounded border border-terminal-850">
              <span className="text-[10px] text-terminal-500 uppercase block">4. Volatility</span>
              <span className="text-sm font-bold text-terminal-200 capitalize block mt-1">
                {snapshot.opportunity_state.volatility_state}
              </span>
              <span className="text-[10px] text-terminal-500 mt-1 block">Regime validation pending</span>
            </div>

            <div className="bg-terminal-950 p-3 rounded border border-terminal-850">
              <span className="text-[10px] text-terminal-500 uppercase block">5. Time State</span>
              <span className="text-sm font-bold text-terminal-300 capitalize block mt-1">
                {snapshot.opportunity_state.time_state}
              </span>
              <span className="text-[10px] text-terminal-500 mt-1 block">Session classifier pending</span>
            </div>
          </div>

          {/* Caveats / Disclosures */}
          <div className="mt-4 pt-4 border-t border-terminal-850 space-y-1.5 font-mono text-xs text-terminal-400">
            {snapshot.opportunity_state.caveats.map((c, idx) => (
              <div key={idx} className="flex items-start gap-2">
                <span className="text-warning mt-0.5">•</span>
                <span>{c}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Price Structure Levels Table */}
        <div className="bg-terminal-900 border border-terminal-800 rounded p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="font-mono text-sm font-bold text-terminal-100 uppercase tracking-wide">
                Price Structure & Nearest Structural Zones
              </h2>
              <p className="text-xs font-mono text-terminal-400 mt-0.5">
                Historical levels relative to current spot. Support/resistance describes structural zones, not guaranteed barriers.
              </p>
            </div>
            <StatusPill label="OBSERVED LEVELS ONLY" variant="neutral" />
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left font-mono text-xs border-collapse">
              <thead>
                <tr className="border-b border-terminal-800 text-[11px] text-terminal-400 uppercase">
                  <th className="py-2.5 px-3">Zone Label</th>
                  <th className="py-2.5 px-3">Level Price</th>
                  <th className="py-2.5 px-3">Distance ($)</th>
                  <th className="py-2.5 px-3">Distance (%)</th>
                  <th className="py-2.5 px-3">Type</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-terminal-850">
                {snapshot.levels.map((lvl, idx) => {
                  const isAbove = lvl.price > snapshot.current_spot;
                  return (
                    <tr key={idx} className="hover:bg-terminal-950/40">
                      <td className="py-2.5 px-3 font-semibold text-terminal-200">
                        {lvl.label}
                      </td>
                      <td className="py-2.5 px-3 font-numeric text-terminal-100">
                        ${lvl.price.toFixed(2)}
                      </td>
                      <td className={`py-2.5 px-3 font-numeric ${isAbove ? "text-loss" : "text-profit"}`}>
                        {lvl.distance >= 0 ? `+$${lvl.distance.toFixed(2)}` : `-$${Math.abs(lvl.distance).toFixed(2)}`}
                      </td>
                      <td className={`py-2.5 px-3 font-numeric ${isAbove ? "text-loss" : "text-profit"}`}>
                        {lvl.distance_pct >= 0 ? `+${lvl.distance_pct.toFixed(2)}%` : `${lvl.distance_pct.toFixed(2)}%`}
                      </td>
                      <td className="py-2.5 px-3">
                        <span className={`px-2 py-0.5 rounded text-[10px] ${
                          lvl.kind === "resistance" ? "bg-loss-bg text-loss" :
                          lvl.kind === "support" ? "bg-profit-bg text-profit" :
                          "bg-terminal-800 text-terminal-400"
                        }`}>
                          {lvl.kind.toUpperCase()}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
