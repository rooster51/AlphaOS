import React from "react";
import { Header } from "@/components/shell/Header";
import { StatusPill } from "@/components/shell/StatusPill";
import { MOCK_JOURNAL_POSITIONS } from "@/lib/mock-data";
import { AlertCircle, Lock, BookOpen, Layers } from "lucide-react";

export default function TradeJournalPage() {
  return (
    <div>
      <Header
        title="Trade Journal & Position Ledger"
        subtitle="Append-only lifecycle events, immutable entry evidence, and realized performance tracking."
        badge={{
          label: "FOUNDATION PREVIEW (READ-ONLY)",
          variant: "warning",
        }}
      />

      <div className="p-8 space-y-6">
        {/* Foundation Notice */}
        <div className="bg-warning-bg border border-warning/30 rounded p-5 flex items-start gap-3.5 text-warning font-mono text-xs">
          <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <div className="font-bold uppercase tracking-wide">
              Persistent Trade Journal Status: Foundation Only (Not Deployed)
            </div>
            <p className="text-terminal-300 leading-relaxed text-[11px]">
              The trade ledger SQL architecture (<code className="text-warning">supabase/alphaos2_trade_ledger.sql</code>) defines an append-only, RLS-protected database schema for durable position lifecycles and frozen research snapshots.
              Journal mutation endpoints and account linking are intentionally disabled pending Codex&apos;s identity foundation rollout. All position entries displayed below are simulated fixtures.
            </p>
          </div>
        </div>

        {/* Ledger Architectural Highlights */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 font-mono text-xs">
          <div className="bg-terminal-900 border border-terminal-800 rounded p-4">
            <div className="flex items-center gap-2 text-profit mb-2 font-bold uppercase text-[11px]">
              <Lock className="w-4 h-4" />
              <span>Immutable Evidence</span>
            </div>
            <p className="text-terminal-400 text-[11px] leading-relaxed">
              Every position freezes its Opportunity State classification (direction, premium, movement, time) at entry to enable accurate historical calibration.
            </p>
          </div>

          <div className="bg-terminal-900 border border-terminal-800 rounded p-4">
            <div className="flex items-center gap-2 text-accent mb-2 font-bold uppercase text-[11px]">
              <Layers className="w-4 h-4" />
              <span>Multi-Leg Normalization</span>
            </div>
            <p className="text-terminal-400 text-[11px] leading-relaxed">
              Positions store discrete, signed option legs with strike, expiration, and observed entry bid/ask/mid prices for full lifecycle tracking.
            </p>
          </div>

          <div className="bg-terminal-900 border border-terminal-800 rounded p-4">
            <div className="flex items-center gap-2 text-warning mb-2 font-bold uppercase text-[11px]">
              <BookOpen className="w-4 h-4" />
              <span>Row-Level Security</span>
            </div>
            <p className="text-terminal-400 text-[11px] leading-relaxed">
              All ledger tables enforce Supabase <code className="text-warning">auth.uid()</code> policies so authenticated traders can access only their own positions.
            </p>
          </div>
        </div>

        {/* Simulated Positions Table */}
        <div className="bg-terminal-900 border border-terminal-800 rounded p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="font-mono text-sm font-bold text-terminal-100 uppercase tracking-wide">
                Simulated Position Ledger
              </h2>
              <p className="text-xs font-mono text-terminal-400 mt-0.5">
                Demonstrates schema presentation for open and realized option trades.
              </p>
            </div>
            <StatusPill label="MOCK DATA" variant="mock" />
          </div>

          <div className="space-y-4">
            {MOCK_JOURNAL_POSITIONS.map((pos) => {
              const isProfit = (pos.realized_pnl ?? pos.unrealized_pnl) >= 0;
              return (
                <div
                  key={pos.id}
                  className="bg-terminal-950 border border-terminal-850 rounded p-4 font-mono text-xs space-y-3"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="font-bold px-2 py-0.5 rounded bg-terminal-800 text-terminal-200 border border-terminal-700">
                        {pos.symbol}
                      </span>
                      <span className="font-semibold text-terminal-100 uppercase">
                        {pos.family.toUpperCase()} Strategy
                      </span>
                      <span className="text-[10px] px-2 py-0.5 rounded bg-terminal-900 text-terminal-400 border border-terminal-800 uppercase">
                        Status: {pos.status}
                      </span>
                    </div>

                    <div className="text-right">
                      <div className="text-[10px] text-terminal-500 uppercase">
                        {pos.status === "closed" ? "Realized P&L" : "Unrealized P&L"}
                      </div>
                      <div className={`text-sm font-bold font-numeric ${isProfit ? "text-profit" : "text-loss"}`}>
                        {isProfit ? `+$${pos.realized_pnl ?? pos.unrealized_pnl}` : `-$${Math.abs(pos.realized_pnl ?? pos.unrealized_pnl)}`}
                      </div>
                    </div>
                  </div>

                  {/* Legs */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-[11px] text-terminal-400 bg-terminal-900/60 p-2.5 rounded border border-terminal-850">
                    <div>
                      <span className="text-terminal-500 block text-[10px] uppercase">Legs:</span>
                      {pos.legs.map((l, i) => (
                        <div key={i}>
                          • {l.action.toUpperCase()} {l.strike} {l.option_type.toUpperCase()} @ ${l.mid.toFixed(2)}
                        </div>
                      ))}
                    </div>
                    <div>
                      <span className="text-terminal-500 block text-[10px] uppercase">Frozen Market State at Entry:</span>
                      <div>
                        Direction: <span className="text-profit">{pos.frozen_opportunity_state.direction}</span> | 
                        Movement: <span className="text-accent">{pos.frozen_opportunity_state.movement_state}</span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between text-[10px] text-terminal-500 pt-1">
                    <span>Entry Spot: ${pos.entry_spot.toFixed(2)} • Entry Time: {new Date(pos.entry_time).toLocaleString()}</span>
                    <span>Max Loss Budget: ${pos.max_loss_budget}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
