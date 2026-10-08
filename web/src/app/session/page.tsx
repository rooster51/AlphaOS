import React from "react";
import { Header } from "@/components/shell/Header";
import { MetricCard } from "@/components/ui/MetricCard";
import { StatusPill } from "@/components/shell/StatusPill";
import { Clock, ShieldCheck, AlertTriangle, CheckCircle2 } from "lucide-react";

export default function SessionReviewPage() {
  return (
    <div>
      <Header
        title="Session Review & Execution Quality Gate"
        subtitle="NYSE market session boundaries, 0DTE observation cutoff, and quote freshness telemetry."
        badge={{
          label: "AUDITED SESSION",
          variant: "archive",
        }}
      />

      <div className="p-8 space-y-6">
        {/* Top Session Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <MetricCard
            label="Exchange Calendar"
            value="NYSE Arca"
            subValue="America/New_York"
            trend="neutral"
            caption="Regular market hours: 09:30–16:00"
          />
          <MetricCard
            label="0DTE Policy"
            value="60 Min"
            subValue="Late Threshold"
            trend="neutral"
            caption="Zero-time construction enabled; POP suppressed"
          />
          <MetricCard
            label="Freshness Gate"
            value="< 600s"
            subValue="Archive Age"
            trend="bullish"
            caption="Fail-closed on stale or mismatched quotes"
          />
          <MetricCard
            label="Slot Idempotency"
            value="Active"
            subValue="Supabase Storage"
            trend="bullish"
            caption="Immutable archive slots"
          />
        </div>

        {/* 0DTE and Market Hours Timeline */}
        <div className="bg-terminal-900 border border-terminal-800 rounded p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="font-mono text-sm font-bold text-terminal-100 uppercase tracking-wide">
                Trading Session Lifecycle & 0DTE Rules
              </h2>
              <p className="text-xs font-mono text-terminal-400 mt-0.5">
                Explicit temporal states prevent fabricating probability models on expired contracts.
              </p>
            </div>
            <StatusPill label="SESSION GATE" variant="neutral" />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 font-mono text-xs my-4">
            <div className="bg-terminal-950 p-4 rounded border border-terminal-850">
              <div className="flex items-center gap-2 text-accent mb-2">
                <Clock className="w-4 h-4" />
                <span className="font-bold">Standard Session</span>
              </div>
              <p className="text-terminal-400 leading-relaxed text-[11px]">
                09:30 to 15:00 EDT. Full analytical suite enabled including Black-Scholes probability models, forward analog distributions, and vertical discovery.
              </p>
            </div>

            <div className="bg-terminal-950 p-4 rounded border border-terminal-850">
              <div className="flex items-center gap-2 text-warning mb-2">
                <AlertTriangle className="w-4 h-4" />
                <span className="font-bold">Late 0DTE Window</span>
              </div>
              <p className="text-terminal-400 leading-relaxed text-[11px]">
                15:00 to 16:00 EDT (final 60 minutes). Modeled probability of profit (POP) is mathematically suppressed to zero time; quote-based payoff economics remain accessible.
              </p>
            </div>

            <div className="bg-terminal-950 p-4 rounded border border-terminal-850">
              <div className="flex items-center gap-2 text-loss mb-2">
                <ShieldCheck className="w-4 h-4" />
                <span className="font-bold">After-Hours / Closed</span>
              </div>
              <p className="text-terminal-400 leading-relaxed text-[11px]">
                16:00 to 09:30 EDT. Live quote validation fails closed; research defaults to the most recent verified archive session snapshot.
              </p>
            </div>
          </div>
        </div>

        {/* Observation Quality Audit Table */}
        <div className="bg-terminal-900 border border-terminal-800 rounded p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="font-mono text-sm font-bold text-terminal-100 uppercase tracking-wide">
                Archive Observation Audit Logs
              </h2>
              <p className="text-xs font-mono text-terminal-400 mt-0.5">
                Integrity metrics from the latest minute-level market data collection pass.
              </p>
            </div>
            <StatusPill label="FAIL-CLOSED" variant="archive" />
          </div>

          <div className="space-y-3 font-mono text-xs">
            <div className="flex items-center justify-between p-3 bg-terminal-950 rounded border border-terminal-850">
              <div className="flex items-center gap-3">
                <CheckCircle2 className="w-4 h-4 text-profit" />
                <div>
                  <span className="font-bold text-terminal-200">SPY Minute Observation Slot</span>
                  <div className="text-[10px] text-terminal-500">Slot: 2026-10-07-1545 • SHA-256 validated</div>
                </div>
              </div>
              <span className="text-profit font-semibold">100% Valid (79 Contracts)</span>
            </div>

            <div className="flex items-center justify-between p-3 bg-terminal-950 rounded border border-terminal-850">
              <div className="flex items-center gap-3">
                <CheckCircle2 className="w-4 h-4 text-profit" />
                <div>
                  <span className="font-bold text-terminal-200">QQQ Minute Observation Slot</span>
                  <div className="text-[10px] text-terminal-500">Slot: 2026-10-07-1545 • SHA-256 validated</div>
                </div>
              </div>
              <span className="text-profit font-semibold">100% Valid (77 Contracts)</span>
            </div>

            <div className="flex items-center justify-between p-3 bg-terminal-950 rounded border border-terminal-850">
              <div className="flex items-center gap-3">
                <CheckCircle2 className="w-4 h-4 text-profit" />
                <div>
                  <span className="font-bold text-terminal-200">Historical Analog Alignment</span>
                  <div className="text-[10px] text-terminal-500">Horizon: 3 sessions • Sample N: 250 sessions</div>
                </div>
              </div>
              <span className="text-terminal-300">Synchronized</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
