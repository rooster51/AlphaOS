export const dynamic = "force-dynamic";

import Link from "next/link";
import { Header } from "@/components/shell/Header";
import { MarketUnavailable } from "@/components/market/MarketUnavailable";
import { POST as researchMarket } from "@/app/api/research/market/route";

type Symbol = "SPY" | "QQQ";
type JsonRecord = Record<string, unknown>;

function record(value: unknown): JsonRecord | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as JsonRecord : null;
}

async function loadResearch(symbol: Symbol): Promise<JsonRecord | null> {
  // Reuse the validated, server-only POST bridge. No browser credentials or
  // legacy GET endpoints are involved in this page's research request.
  const response = await researchMarket(new Request("http://localhost/api/research/market", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol }),
  }));
  if (!response.ok) return null;
  const body = record(await response.json());
  const envelope = record(body?.research);
  const request = record(envelope?.request);
  if (body?.verified_for_trading !== false ||
      envelope?.schema_version !== "alphaos-interface-v2" ||
      envelope?.read_only !== true || request?.symbol !== symbol ||
      !record(envelope?.research) || !record(envelope?.provenance) ||
      !Array.isArray(envelope?.caveats)) return null;
  return envelope;
}

export default async function MarketResearchPage({
  searchParams,
}: {
  searchParams?: { symbol?: string };
}) {
  const requested = searchParams?.symbol?.toUpperCase() ?? "QQQ";
  if (requested !== "SPY" && requested !== "QQQ") {
    return <MarketUnavailable symbol={requested} reason="Unsupported market symbol." />;
  }
  const symbol = requested as Symbol;
  let envelope: JsonRecord | null = null;
  try {
    envelope = await loadResearch(symbol);
  } catch {
    // Fail closed: network, backend, and malformed data never produce mock quotes.
  }
  if (!envelope) {
    return <MarketUnavailable symbol={symbol} reason="Authenticated research or verified evidence is unavailable." />;
  }

  const research = record(envelope.research)!;
  const provenance = record(envelope.provenance)!;
  const caveats = envelope.caveats as unknown[];
  const status = typeof research.status === "string" ? research.status : "Research received";
  return (
    <div>
      <Header
        title={`Market Research — ${symbol}`}
        subtitle="Read-only research from the authenticated AlphaOS backend."
        badge={{ label: "READ ONLY", variant: "archive" }}
      />
      <main className="p-8 space-y-6 font-mono">
        <nav aria-label="Choose market symbol" className="flex gap-3">
          {(["QQQ", "SPY"] as const).map(item => (
            <Link key={item} href={`/market?symbol=${item}`}
              aria-current={item === symbol ? "page" : undefined}
              className="rounded border border-terminal-700 px-3 py-2 text-xs text-terminal-200 hover:bg-terminal-900">
              {item}
            </Link>
          ))}
        </nav>
        <div className="rounded border border-terminal-700 bg-terminal-900 p-5 space-y-2">
          <h2 className="font-bold text-terminal-100">Research response — {symbol}</h2>
          <p className="text-sm text-terminal-300">{status}</p>
          <p className="text-xs text-terminal-400">
            Research evidence only. No execution, verified trading quotes, or inferred POP/EV.
          </p>
        </div>
        <section className="rounded border border-terminal-700 bg-terminal-900 p-5 space-y-3">
          <h2 className="font-bold text-terminal-100">Research evidence</h2>
          <pre className="overflow-x-auto whitespace-pre-wrap break-words text-xs text-terminal-300">
            {JSON.stringify(research, null, 2)}
          </pre>
        </section>
        <section className="rounded border border-terminal-700 bg-terminal-900 p-5 space-y-3">
          <h2 className="font-bold text-terminal-100">Provenance</h2>
          <pre className="overflow-x-auto whitespace-pre-wrap break-words text-xs text-terminal-300">
            {JSON.stringify(provenance, null, 2)}
          </pre>
        </section>
        <section className="rounded border border-terminal-700 bg-terminal-900 p-5 space-y-3">
          <h2 className="font-bold text-terminal-100">Caveats</h2>
          {caveats.length === 0
            ? <p className="text-xs text-terminal-400">No additional caveats supplied.</p>
            : <ul className="list-disc pl-5 text-xs text-terminal-300">
                {caveats.map((item, index) => <li key={index}>{typeof item === "string" ? item : "Unstructured caveat"}</li>)}
              </ul>}
        </section>
      </main>
    </div>
  );
}
