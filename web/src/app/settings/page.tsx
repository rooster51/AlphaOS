import { Header } from "@/components/shell/Header";
export default function SettingsPage() {
  return (
    <div>
      <Header title="Settings & Infrastructure" subtitle="Read-only release configuration"
        badge={{ label: "CONFIGURATION NOT EDITABLE", variant: "neutral" }} />
      <div className="p-8 space-y-5">
        <section className="bg-terminal-900 border border-terminal-800 rounded p-6 space-y-2">
          <h2 className="font-mono font-bold text-terminal-100">Research backend</h2>
          <p className="font-mono text-xs text-terminal-400">
            The website uses a server-side API token when configured. API health and
            authenticated market availability are distinct checks. Connection status
            is not proof of fresh market evidence.
          </p>
        </section>
        <section className="bg-terminal-900 border border-terminal-800 rounded p-6 space-y-2">
          <h2 className="font-mono font-bold text-terminal-100">Personal account preferences unavailable</h2>
          <p className="font-mono text-xs text-terminal-400">
            Capital balances, risk thresholds, trading limits and user identity are
            not synchronized with a verified personal account. No default portfolio
            amounts or active stop-trading controls are asserted here.
          </p>
        </section>
        <section className="bg-terminal-900 border border-terminal-800 rounded p-6 space-y-2">
          <h2 className="font-mono font-bold text-terminal-100">Journal access</h2>
          <p className="font-mono text-xs text-terminal-400">
            Identity, user-scoped storage, and row-level policies require separate
            production validation before journal access or mutation is enabled.
          </p>
        </section>
      </div>
    </div>
  );
}
