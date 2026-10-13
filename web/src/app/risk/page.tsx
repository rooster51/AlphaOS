import { Header } from "@/components/shell/Header";
import { MetricCard } from "@/components/ui/MetricCard";

export default function PortfolioRiskPage() {
  return (
    <div>
      <Header title="Portfolio & Risk" subtitle="Authenticated portfolio state is not connected."
        badge={{ label: "READ-ONLY — UNASSESSED", variant: "warning" }} />
      <div className="p-8 space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <MetricCard label="Account capital" value="Unavailable" caption="No verified broker account balance"/>
          <MetricCard label="Daily P&L" value="Unavailable" caption="No reconciled trade journal"/>
          <MetricCard label="Committed position risk" value="Unavailable" caption="No authenticated positions"/>
          <MetricCard label="Guardrail enforcement" value="Not active" caption="No brokerage trade blocking"/>
        </div>
        <section className="bg-terminal-900 border border-terminal-800 rounded p-6 space-y-3">
          <h2 className="text-terminal-100 font-mono font-bold">Risk monitoring is not yet connected</h2>
          <p className="text-xs font-mono text-terminal-400">
            AlphaOS can describe deterministic maximum expiration loss for individual researched
            option structures. It cannot currently confirm your account buying power, aggregate
            open-position risk, or enforce a daily-loss circuit breaker. No simulated positions
            or guessed account values are shown as real.
          </p>
        </section>
      </div>
    </div>
  );
}
