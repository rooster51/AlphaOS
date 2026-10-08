import React from "react";
import { Header } from "@/components/shell/Header";
import { MetricCard } from "@/components/ui/MetricCard";
import { StatusPill } from "@/components/shell/StatusPill";
import { MOCK_GUARDRAILS, MOCK_CANDIDATES } from "@/lib/mock-data";
import { ShieldCheck, AlertOctagon, CheckSquare, Activity } from "lucide-react";

export default function PortfolioRiskPage() {
  const accountSize = MOCK_GUARDRAILS.default_account_size;
  const maxLossCap = (accountSize * MOCK_GUARDRAILS.max_daily_loss_pct) / 100;
  const currentRiskCommitted = 390; // mock combined max loss from active candidates

  return (
    <div>
      <Header
        title="Portfolio & Expiration Risk"
        subtitle="Deterministic capital ceilings, expiration shock scenarios, and discipline guardrails."
        badge={{
          label: "RISK GUARDS ACTIVE",
          variant: "archive",
        }}
      />

      <div className="p-8 space-y-6">
        {/* Risk Metrics */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <MetricCard
            label="Total Account Capital"
            value={`$${accountSize.toLocaleString()}`}
            subValue="Base Portfolio"
            trend="neutral"
            caption="Configured in Settings"
          />
          <MetricCard
            label="Max Daily Loss Cap"
            value={`$${maxLossCap.toFixed(0)}`}
            subValue={`${MOCK_GUARDRAILS.max_daily_loss_pct}% of Capital`}
            trend="bearish"
            caption="Discipline circuit breaker"
          />
          <MetricCard
            label="Active Committed Risk"
            value={`$${currentRiskCommitted}`}
            subValue={`${((currentRiskCommitted / maxLossCap) * 100).toFixed(1)}% of Loss Budget`}
            trend="neutral"
            caption="Sum of max defined loss"
          />
          <MetricCard
            label="Guardrail Status"
            value="GREEN"
            subValue="Compliant"
            trend="bullish"
            caption="0 violations detected"
          />
        </div>

        {/* Discipline Guardrail Checklist */}
        <div className="bg-terminal-900 border border-terminal-800 rounded p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="font-mono text-sm font-bold text-terminal-100 uppercase tracking-wide">
                Active Discipline Guardrails
              </h2>
              <p className="text-xs font-mono text-terminal-400 mt-0.5">
                Mechanical constraints preventing revenge trading, over-allocation, and excessive sizing.
              </p>
            </div>
            <StatusPill label="POLICY ENFORCED" variant="neutral" />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 font-mono text-xs">
            <div className="bg-terminal-950 p-4 rounded border border-terminal-850 space-y-2">
              <div className="flex items-center gap-2 text-profit font-semibold">
                <CheckSquare className="w-4 h-4" />
                <span>Max Trades Per Session</span>
              </div>
              <div className="text-lg font-bold text-terminal-100 font-numeric">
                0 / {MOCK_GUARDRAILS.max_trades_per_day} Trades
              </div>
              <p className="text-terminal-500 text-[10px]">
                Restricts daily turnover to maintain focus on high-conviction structural alignments.
              </p>
            </div>

            <div className="bg-terminal-950 p-4 rounded border border-terminal-850 space-y-2">
              <div className="flex items-center gap-2 text-profit font-semibold">
                <CheckSquare className="w-4 h-4" />
                <span>Loss Cooldown Rule</span>
              </div>
              <div className="text-lg font-bold text-terminal-100 font-numeric">
                {MOCK_GUARDRAILS.cooldown_minutes} Min Cooldown
              </div>
              <p className="text-terminal-500 text-[10px]">
                Mandates timeout after {MOCK_GUARDRAILS.cooldown_after_losses} consecutive realized losses.
              </p>
            </div>

            <div className="bg-terminal-950 p-4 rounded border border-terminal-850 space-y-2">
              <div className="flex items-center gap-2 text-profit font-semibold">
                <CheckSquare className="w-4 h-4" />
                <span>Minimum Backtest Win Rate</span>
              </div>
              <div className="text-lg font-bold text-terminal-100 font-numeric">
                {MOCK_GUARDRAILS.min_backtest_win_rate}% Survival
              </div>
              <p className="text-terminal-500 text-[10px]">
                Filters out credit structures whose historical analog baseline fails survival criteria.
              </p>
            </div>
          </div>
        </div>

        {/* Shock Scenario EV Stress Matrix */}
        <div className="bg-terminal-900 border border-terminal-800 rounded p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="font-mono text-sm font-bold text-terminal-100 uppercase tracking-wide">
                Underlying Shock Scenario Matrix (QQQ Base: $492.35)
              </h2>
              <p className="text-xs font-mono text-terminal-400 mt-0.5">
                Deterministic price shock analysis across researched structures at expiration.
              </p>
            </div>
            <StatusPill label="SCENARIO STRESS" variant="archive" />
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left font-mono text-xs border-collapse">
              <thead>
                <tr className="border-b border-terminal-800 text-[11px] text-terminal-400 uppercase">
                  <th className="py-2.5 px-3">Structure</th>
                  <th className="py-2.5 px-3 text-loss">-3% Shock ($477.58)</th>
                  <th className="py-2.5 px-3 text-loss">-1% Shock ($487.43)</th>
                  <th className="py-2.5 px-3 text-terminal-300">0% Base ($492.35)</th>
                  <th className="py-2.5 px-3 text-profit">+1% Shock ($497.27)</th>
                  <th className="py-2.5 px-3 text-profit">+3% Shock ($507.12)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-terminal-850">
                {MOCK_CANDIDATES.map((cand) => (
                  <tr key={cand.id} className="hover:bg-terminal-950/40">
                    <td className="py-3 px-3 font-semibold text-terminal-200">
                      {cand.family_label}
                    </td>
                    <td className="py-3 px-3 font-numeric text-loss">-${cand.max_loss}</td>
                    <td className="py-3 px-3 font-numeric text-loss">
                      {cand.family === "pcs" ? `-$${cand.max_loss}` : `-$${(cand.max_loss * 0.7).toFixed(0)}`}
                    </td>
                    <td className="py-3 px-3 font-numeric text-terminal-200">
                      {cand.family === "pcs" ? `+$${cand.max_profit}` : "-$40"}
                    </td>
                    <td className="py-3 px-3 font-numeric text-profit">
                      {cand.max_profit === "unlimited" ? "+$350" : `+$${cand.max_profit}`}
                    </td>
                    <td className="py-3 px-3 font-numeric text-profit">
                      {cand.max_profit === "unlimited" ? "+$1,335" : `+$${cand.max_profit}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
