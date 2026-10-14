"use client";

import React from "react";
import { ResearchCandidate } from "@/types/research";

interface PayoffDiagramProps {
  candidate: ResearchCandidate;
  underlyingSpot: number;
}

export function PayoffDiagram({ candidate, underlyingSpot }: PayoffDiagramProps) {
  // Generate deterministic points around spot +/- 6%
  const minSpot = underlyingSpot * 0.94;
  const maxSpot = underlyingSpot * 1.06;
  const steps = 40;
  const stepSize = (maxSpot - minSpot) / steps;

  const points: { x: number; y: number }[] = [];

  for (let i = 0; i <= steps; i++) {
    const s = minSpot + i * stepSize;
    let payoff = 0;

    for (const leg of candidate.legs) {
      const mult = leg.action === "buy" ? 1 : -1;
      let intrinsic = 0;
      if (leg.option_type === "call") {
        intrinsic = Math.max(0, s - leg.strike);
      } else {
        intrinsic = Math.max(0, leg.strike - s);
      }
      payoff += mult * intrinsic * 100;
    }

    // subtract net cashflow
    payoff -= candidate.net_cashflow * 100;
    points.push({ x: s, y: payoff });
  }

  // Find min and max y for SVG coordinate mapping
  const yValues = points.map((p) => p.y);
  const minY = Math.min(-candidate.max_loss, Math.min(...yValues));
  const maxY = candidate.max_profit === "unlimited" ? Math.max(candidate.max_loss * 2, Math.max(...yValues)) : Math.max(Number(candidate.max_profit), Math.max(...yValues));
  const rangeY = maxY - minY || 1;

  const width = 360;
  const height = 140;
  const padX = 20;
  const padY = 20;

  const mapX = (x: number) => padX + ((x - minSpot) / (maxSpot - minSpot)) * (width - 2 * padX);
  const mapY = (y: number) => height - padY - ((y - minY) / rangeY) * (height - 2 * padY);

  const pathD = points
    .map((p, idx) => `${idx === 0 ? "M" : "L"} ${mapX(p.x).toFixed(1)} ${mapY(p.y).toFixed(1)}`)
    .join(" ");

  const zeroY = mapY(0);
  const spotX = mapX(underlyingSpot);

  return (
    <div className="bg-terminal-950 border border-terminal-800 rounded p-3 select-none">
      <div className="flex justify-between items-center text-[10px] font-mono text-terminal-400 mb-1">
        <span>PAYOFF AT EXPIRATION</span>
        <span className="text-terminal-500 font-numeric">Spot: ${underlyingSpot.toFixed(2)}</span>
      </div>

      <div className="relative w-full h-[140px]">
        <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-full">
          {/* Zero PnL axis */}
          <line
            x1={padX}
            y1={zeroY}
            x2={width - padX}
            y2={zeroY}
            stroke="#243042"
            strokeDasharray="3 3"
            strokeWidth="1"
          />

          {/* Current Spot indicator line */}
          <line
            x1={spotX}
            y1={padY}
            x2={spotX}
            y2={height - padY}
            stroke="#38BDF8"
            strokeOpacity="0.4"
            strokeWidth="1"
          />

          {/* Breakeven lines */}
          {candidate.breakevens.map((be, idx) => {
            const bx = mapX(be);
            return (
              <g key={idx}>
                <line
                  x1={bx}
                  y1={padY}
                  x2={bx}
                  y2={height - padY}
                  stroke="#F59E0B"
                  strokeDasharray="2 2"
                  strokeWidth="1"
                />
              </g>
            );
          })}

          {/* Payoff Curve */}
          <path
            d={pathD}
            fill="none"
            stroke="#10B981"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
      </div>

      <div className="flex justify-between items-center text-[10px] font-mono text-terminal-500 mt-1">
        <span>Max Loss: -${candidate.max_loss}</span>
        <span>
          Max Profit: {candidate.max_profit === "unlimited" ? "Unlimited" : `+$${candidate.max_profit}`}
        </span>
      </div>
    </div>
  );
}
