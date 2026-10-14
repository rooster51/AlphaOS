import React from "react";

interface MetricCardProps {
  label: string;
  value: string | number;
  subValue?: string;
  trend?: "bullish" | "bearish" | "neutral";
  caption?: string;
}

export function MetricCard({
  label,
  value,
  subValue,
  trend = "neutral",
  caption,
}: MetricCardProps) {
  const trendColor = {
    bullish: "text-profit",
    bearish: "text-loss",
    neutral: "text-terminal-100",
  }[trend];

  return (
    <div className="bg-terminal-900 border border-terminal-800 rounded p-4 flex flex-col justify-between">
      <div className="text-[11px] font-mono text-terminal-400 uppercase tracking-wider mb-1">
        {label}
      </div>
      <div className="flex items-baseline gap-2">
        <div className={`font-mono text-xl font-bold font-numeric ${trendColor}`}>
          {value}
        </div>
        {subValue && (
          <div className="font-mono text-xs text-terminal-400 font-numeric">
            {subValue}
          </div>
        )}
      </div>
      {caption && (
        <div className="text-[10px] font-mono text-terminal-500 mt-2 truncate">
          {caption}
        </div>
      )}
    </div>
  );
}
