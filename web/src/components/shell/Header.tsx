import { StatusPill } from "./StatusPill";

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
    <header className="min-h-16 border-b border-terminal-800 bg-terminal-950/80 px-8 py-3 flex items-center justify-between gap-4">
      <div>
        <div className="flex items-center gap-3">
          <h1 className="font-mono text-base font-bold text-terminal-100 uppercase">{title}</h1>
          {badge && <StatusPill label={badge.label} variant={badge.variant}/>}
        </div>
        {subtitle && <p className="text-xs text-terminal-400 font-mono mt-1">{subtitle}</p>}
      </div>
      <div className="hidden md:block text-xs font-mono text-terminal-400">
        Research only · No broker execution
      </div>
    </header>
  );
}
