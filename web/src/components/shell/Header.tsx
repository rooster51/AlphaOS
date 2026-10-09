import React from "react";
import { StatusPill } from "./StatusPill";
import { ShieldCheck, Database, Cpu } from "lucide-react";

interface HeaderProps {
  title: string;
  subtitle?: string;
  badge?: {
    label: string;
    variant: "archive" | "mock" | "live" | "warning" | "neutral";
  };
}

export function Header({ title, subtitle, badge }: HeaderProps) {
  return (
    <header className="h-16 border-b border-terminal-800 bg-terminal-950/80 backdrop-blur px-8 flex items-center justify-between shrink-0">
      <div>
        <div className="flex items-center gap-3">
          <h1 className="font-mono text-base font-bold text-terminal-100 uppercase tracking-wide">
            {title}
          </h1>
          {badge && <StatusPill label={badge.label} variant={badge.variant} />}
        </div>
        {subtitle && (
          <p className="text-xs text-terminal-400 font-mono mt-0.5">
            {subtitle}
          </p>
        )}
      </div>

      <div className="flex items-center gap-4 font-mono text-xs">
        {/* Backend connectivity telemetry */}
        <div className="flex items-center gap-2 px-2.5 py-1 rounded bg-terminal-900 border border-terminal-800 text-terminal-400">
          <Cpu className="w-3.5 h-3.5 text-accent" />
          <span>API /v1</span>
          <span className="w-1.5 h-1.5 rounded-full bg-profit" />
        </div>

        <div className="flex items-center gap-2 px-2.5 py-1 rounded bg-terminal-900 border border-terminal-800 text-terminal-400">
          <Database className="w-3.5 h-3.5 text-warning" />
          <span>Supabase RLS</span>
          <span className="text-terminal-500">auth.uid()</span>
        </div>

        <div className="flex items-center gap-2 px-2.5 py-1 rounded bg-terminal-900 border border-terminal-800 text-profit">
          <ShieldCheck className="w-3.5 h-3.5" />
          <span>Descriptive Research</span>
        </div>
      </div>
    </header>
  );
}
