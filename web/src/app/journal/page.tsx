import { Header } from "@/components/shell/Header";

export default function TradeJournalPage() {
  return (
    <div>
      <Header title="Trade Journal & Position Ledger"
        subtitle="Private account-scoped journal integration is pending."
        badge={{ label: "NOT CONNECTED — READ ONLY", variant: "warning" }} />
      <div className="p-8 space-y-5">
        <section className="bg-terminal-900 border border-terminal-800 rounded p-6 space-y-3">
          <h2 className="font-mono font-bold text-terminal-100">No verified positions loaded</h2>
          <p className="text-xs font-mono text-terminal-400">
            This does not mean your brokerage account has no positions. The website does not
            yet have authenticated, user-scoped access to a persistent trade ledger.
            Example positions and invented realized or unrealized P&L are intentionally hidden.
          </p>
          <p className="text-xs font-mono text-terminal-400">
            Trade entry, exit, editing, synchronization and journal writes remain disabled
            until account identity and row-level access controls are independently validated.
          </p>
        </section>
      </div>
    </div>
  );
}
