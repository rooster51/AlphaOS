import React from "react";

interface StatusPillProps {
  label: string;
  variant?: "archive" | "mock" | "live" | "warning" | "neutral";
  size?: "sm" | "md";
}

export function StatusPill({ label, variant = "neutral", size = "sm" }: StatusPillProps) {
  const styles = {
    archive: "bg-profit-bg text-profit border-profit/30",
    mock: "bg-warning-bg text-warning border-warning/30",
    live: "bg-accent-bg text-accent border-accent/30",
    warning: "bg-loss-bg text-loss border-loss/30",
    neutral: "bg-terminal-800 text-terminal-300 border-terminal-700",
  }[variant];

  const sizeStyle = size === "sm" ? "text-xs px-2 py-0.5" : "text-sm px-2.5 py-1";

  return (
    <span
      className={`inline-flex items-center gap-1.5 font-mono font-medium rounded-full border ${styles} ${sizeStyle}`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current opacity-80" />
      {label}
    </span>
  );
}
