"use client";

import { useRouter } from "next/navigation";
import { Header } from "@/components/shell/Header";
import Link from "next/link";

export function MarketUnavailable({ symbol, reason }: { symbol: string; reason: string }) {
  const router = useRouter();

  return (
    <div>
      <Header
        title={`Market Research — ${symbol}`}
        subtitle="Read-only market evidence is unavailable."
        badge={{ label: "UNAVAILABLE", variant: "warning" }}
      />
      <section className="p-8 space-y-5" aria-live="polite">
        <div className="rounded border border-warning/30 bg-terminal-900 p-5 space-y-3">
          <h2 className="font-mono font-bold text-terminal-100">Research unavailable</h2>
          <p className="font-mono text-sm text-terminal-300">{reason}</p>
          <p className="font-mono text-xs text-terminal-400">
            No substitute prices, signals, or strategy candidates are shown.
          </p>
          <button
            type="button"
            onClick={() => router.refresh()}
            className="rounded border border-terminal-600 px-4 py-2 text-sm text-terminal-100 hover:bg-terminal-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-profit"
          >
            Retry research
          </button>
        </div>
        <nav aria-label="Choose market symbol" className="flex gap-3">
          {["QQQ", "SPY"].map((item) => (
            <Link
              key={item}
              href={`/market?symbol=${item}`}
              aria-current={item === symbol ? "page" : undefined}
              className="rounded border border-terminal-700 px-3 py-2 font-mono text-xs text-terminal-200 hover:bg-terminal-900"
            >
              {item}
            </Link>
          ))}
        </nav>
      </section>
    </div>
  );
}
