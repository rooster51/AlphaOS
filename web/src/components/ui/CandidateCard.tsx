import React from "react";
import { ResearchCandidate } from "@/types/research";
import { PayoffDiagram } from "./PayoffDiagram";
import { StatusPill } from "../shell/StatusPill";

interface CandidateCardProps {
  candidate: ResearchCandidate;
  underlyingSpot: number;
}

export function CandidateCard({ candidate, underlyingSpot }: CandidateCardProps) {
  const isCredit = candidate.net_cashflow < 0;

  return (
    <div className="bg-terminal-900 border border-terminal-800 rounded p-5 flex flex-col justify-between hover:border-terminal-700 transition-colors">
      <div>
        {/* Header */}
        <div className="flex items-start justify-between gap-4 mb-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs font-bold px-2 py-0.5 rounded bg-terminal-800 text-terminal-200 border border-terminal-700">
                {candidate.symbol}
              </span>
              <h3 className="font-mono text-sm font-semibold text-terminal-100">
                {candidate.family_label}
              </h3>
            </div>
            <div className="text-[11px] font-mono text-terminal-400 mt-1">
              Exp: {candidate.expiration} ({candidate.dte} DTE)
            </div>
          </div>
          <StatusPill
            label={isCredit ? `CREDIT $${Math.abs(candidate.net_cashflow * 100)}` : `DEBIT $${(candidate.net_cashflow * 100).toFixed(0)}`}
            variant={isCredit ? "archive" : "neutral"}
          />
        </div>

        {/* Legs representation */}
        <div className="bg-terminal-950 border border-terminal-850 rounded p-2.5 my-3 space-y-1 font-mono text-xs">
          {candidate.legs.map((leg, idx) => (
            <div key={idx} className="flex items-center justify-between">
              <span className={leg.action === "buy" ? "text-accent" : "text-warning"}>
                {leg.action.toUpperCase()} {leg.strike} {leg.option_type.toUpperCase()}
              </span>
              <span className="text-terminal-400 font-numeric">
                Mid: ${leg.mid.toFixed(2)} (B/A: {leg.bid.toFixed(2)}/{leg.ask.toFixed(2)})
              </span>
            </div>
          ))}
        </div>

        {/* Key Metrics Grid */}
        <div className="grid grid-cols-3 gap-2 my-3 text-center font-mono">
          <div className="bg-terminal-950/60 p-2 rounded border border-terminal-850">
            <div className="text-[10px] text-terminal-500 uppercase">Max Loss</div>
            <div className="text-sm font-bold text-loss font-numeric">
              ${candidate.max_loss}
            </div>
          </div>

          <div className="bg-terminal-950/60 p-2 rounded border border-terminal-850">
            <div className="text-[10px] text-terminal-500 uppercase">Max Profit</div>
            <div className="text-sm font-bold text-profit font-numeric">
              {candidate.max_profit === "unlimited" ? "Unlimited" : `$${candidate.max_profit}`}
            </div>
          </div>

          <div className="bg-terminal-950/60 p-2 rounded border border-terminal-850">
            <div className="text-[10px] text-terminal-500 uppercase">Breakeven</div>
            <div className="text-xs font-bold text-terminal-200 font-numeric">
              {candidate.breakevens.map((b) => `$${b.toFixed(2)}`).join(" / ")}
            </div>
          </div>
        </div>

        {/* Payoff chart */}
        <div className="my-3">
          <PayoffDiagram candidate={candidate} underlyingSpot={underlyingSpot} />
        </div>

        {/* Disclosures & Caveats */}
        {candidate.disclosures.length > 0 && (
          <div className="mt-3 space-y-1">
            {candidate.disclosures.map((disc, idx) => (
              <div key={idx} className="text-[10px] font-mono text-terminal-500">
                • {disc}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="mt-4 pt-3 border-t border-terminal-800/80 flex items-center justify-between text-[11px] font-mono text-terminal-500">
        <span>Capital Required: ${candidate.capital_required}</span>
        <span className="text-terminal-400">Order: Generator (Unranked)</span>
      </div>
    </div>
  );
}
