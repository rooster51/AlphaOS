import { Header } from "@/components/shell/Header";
import { StatusPill } from "@/components/shell/StatusPill";

export default function SessionReviewPage() {
  return (
    <div>
      <Header title="Session Evidence" subtitle="Research observation and quote-freshness diagnostics"
        badge={{ label: "NOT VERIFIED LIVE", variant: "neutral" }} />
      <div className="p-8 space-y-5">
        <section className="bg-terminal-900 border border-terminal-800 rounded p-6 space-y-3">
          <h2 className="font-mono font-bold text-terminal-100">Current-session audit unavailable</h2>
          <p className="text-xs font-mono text-terminal-400">
            The web interface does not yet retrieve verified archive slot audit records or
            session-level freshness telemetry. No collection success percentages, option
            contract counts, or historical sample sizes can be asserted here.
          </p>
          <StatusPill label="NO AUDIT EVIDENCE" variant="warning" />
        </section>
        <section className="bg-terminal-900 border border-terminal-800 rounded p-6 space-y-2">
          <h2 className="font-mono font-bold text-terminal-100">Research rules</h2>
          <p className="text-xs font-mono text-terminal-400">
            Opening-range and intraday exit economics remain unavailable in this interface.
            A completed-session historical scenario is not a live execution signal.
            Trade eligibility and broker execution are disabled.
          </p>
        </section>
      </div>
    </div>
  );
}
