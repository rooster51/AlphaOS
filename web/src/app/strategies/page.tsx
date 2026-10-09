"use client";

import React, { useState } from "react";
import { Header } from "@/components/shell/Header";
import { CandidateCard } from "@/components/ui/CandidateCard";
import { StatusPill } from "@/components/shell/StatusPill";
import { MOCK_CANDIDATES } from "@/lib/mock-data";
import { Filter, AlertCircle } from "lucide-react";

export default function StrategyExplorerPage() {
  const [selectedSymbol, setSelectedSymbol] = useState<string>("ALL");
  const [selectedFamily, setSelectedFamily] = useState<string>("ALL");
  const [maxCapital, setMaxCapital] = useState<number>(500);

  const filteredCandidates = MOCK_CANDIDATES.filter((c) => {
    if (selectedSymbol !== "ALL" && c.symbol !== selectedSymbol) return false;
    if (selectedFamily !== "ALL" && c.family !== selectedFamily) return false;
    if (c.capital_required > maxCapital) return false;
    return true;
  });

  return (
    <div>
      <Header
        title="Strategy Explorer"
        subtitle="Unranked candidate generation across defined-risk and directional structures."
        badge={{
          label: "GENERATOR ORDER",
          variant: "archive",
        }}
      />

      <div className="p-8 space-y-6">
        {/* Research Policy Notice */}
        <div className="bg-terminal-900 border border-terminal-800 rounded p-4 flex items-start gap-3 text-terminal-400 font-mono text-xs">
          <AlertCircle className="w-4 h-4 text-profit shrink-0 mt-0.5" />
          <div>
            <span className="text-terminal-200 font-bold">Generator Non-Ranking Rule: </span>
            Strategy routes identify structures consistent with observed market dimensions (direction, volatility, movement).
            Candidate order preserves generator output sequence; AlphaOS does not rank, score, or pick a &ldquo;winner.&rdquo;
          </div>
        </div>

        {/* Filters and Controls */}
        <div className="bg-terminal-900 border border-terminal-800 rounded p-5">
          <div className="flex items-center gap-2 mb-4 font-mono text-xs font-bold text-terminal-300">
            <Filter className="w-3.5 h-3.5 text-accent" />
            <span>RESEARCH FILTERS & CAPITAL CEILING</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 font-mono text-xs">
            {/* Symbol filter */}
            <div>
              <label className="block text-terminal-400 mb-1.5 uppercase text-[10px]">Symbol</label>
              <div className="flex gap-2">
                {["ALL", "QQQ", "SPY"].map((sym) => (
                  <button
                    key={sym}
                    onClick={() => setSelectedSymbol(sym)}
                    className={`px-3 py-1.5 rounded transition ${
                      selectedSymbol === sym
                        ? "bg-profit-bg text-profit border border-profit/40 font-bold"
                        : "bg-terminal-950 text-terminal-400 border border-terminal-800 hover:text-terminal-200"
                    }`}
                  >
                    {sym}
                  </button>
                ))}
              </div>
            </div>

            {/* Strategy Family filter */}
            <div>
              <label className="block text-terminal-400 mb-1.5 uppercase text-[10px]">Strategy Family</label>
              <select
                value={selectedFamily}
                onChange={(e) => setSelectedFamily(e.target.value)}
                className="w-full bg-terminal-950 border border-terminal-800 rounded px-3 py-1.5 text-terminal-200 focus:outline-none focus:border-terminal-600"
              >
                <option value="ALL">All Researched Families</option>
                <option value="cds">Call Debit Spread (CDS)</option>
                <option value="long_call">Long Call</option>
                <option value="pcs">Put Credit Spread (PCS)</option>
                <option value="iron_condor">Iron Condor</option>
              </select>
            </div>

            {/* Max Loss Capital Ceiling */}
            <div>
              <div className="flex justify-between text-terminal-400 mb-1.5 text-[10px]">
                <span className="uppercase">Max Capital at Risk:</span>
                <span className="text-terminal-200 font-bold font-numeric">${maxCapital}</span>
              </div>
              <input
                type="range"
                min={100}
                max={1000}
                step={25}
                value={maxCapital}
                onChange={(e) => setMaxCapital(Number(e.target.value))}
                className="w-full accent-profit cursor-pointer"
              />
            </div>
          </div>
        </div>

        {/* Candidates Section */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <div className="font-mono text-xs text-terminal-400">
              SHOWING <span className="text-terminal-200 font-bold">{filteredCandidates.length}</span> QUALIFYING RESEARCH CANDIDATE(S)
            </div>
            <StatusPill label="DESCRIPTIVE PAYOFF" variant="neutral" />
          </div>

          {filteredCandidates.length === 0 ? (
            <div className="bg-terminal-900 border border-terminal-800 rounded p-12 text-center font-mono text-xs text-terminal-400">
              No candidates meet the active filters and capital ceiling. Expand the capital budget or adjust the strategy family filter.
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {filteredCandidates.map((candidate) => (
                <CandidateCard
                  key={candidate.id}
                  candidate={candidate}
                  underlyingSpot={candidate.symbol === "QQQ" ? 492.35 : 574.6}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
