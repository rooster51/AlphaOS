import { Header } from "@/components/shell/Header";
import { CandidateCard } from "@/components/ui/CandidateCard";
import { getStrategyCandidatesServer } from "@/lib/alphaos-server";

export default async function StrategyExplorerPage() {
  const result = await getStrategyCandidatesServer("ALL");
  const candidates = result.candidates;
  return (
    <div>
      <Header
        title="Strategy Explorer"
        subtitle="Read-only candidate research; only validated market evidence can be treated as current."
        badge={{ label: result.isLive ? "VERIFIED RESEARCH" : "NOT LIVE", variant: "mock" }}
      />
      <div className="p-8 space-y-6">
        <div className="bg-terminal-900 border border-terminal-800 rounded p-5 text-terminal-300 font-mono text-xs">
          {candidates.length
            ? "DEMO MODE: all candidates, premiums, probabilities, and pricing shown below are synthetic examples, not current trades."
            : "Current market-generated strategy candidates are unavailable in the web interface. This is not a market signal and does not mean no trading opportunities exist. Use the connected AlphaOS research tools until the audited market-candidate adapter is complete."}
        </div>
        {candidates.length > 0 && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {candidates.map(candidate => (
              <CandidateCard key={candidate.id} candidate={candidate} underlyingSpot={0} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
