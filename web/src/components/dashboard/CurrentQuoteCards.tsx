"use client";

import { useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import type { CurrentQuote } from "@/lib/current-quotes";

export function CurrentQuoteCards({ quotes, limit }: { quotes: CurrentQuote[]; limit: number }) {
  const router = useRouter();
  const [now, setNow] = useState<number | null>(null);
  const [pending, startTransition] = useTransition();
  useEffect(() => {
    const tick = () => setNow(Date.now());
    tick();
    const timer = window.setInterval(tick, 250);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <section aria-labelledby="current-market-quotes" className="space-y-3">
      <h2 id="current-market-quotes" className="text-lg font-semibold">Current Market Quotes</h2>
      <p className="text-xs font-mono">Public · maximum age {limit} seconds across last, bid and ask.</p>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {(["SPY", "QQQ"] as const).map((symbol, index) => {
          const q = quotes[index];
          const live = q.status === "fresh" && now !== null && now < q.expiresAt && now >= Date.parse(q.retrievedAt);
          return (
            <section key={symbol} aria-label={`${symbol} current quote`} className="bg-terminal-900 border border-terminal-800 rounded p-5">
              <h3 className="font-semibold">{symbol}</h3>
              {live ? <dl className="text-xs font-mono space-y-1">
                <div><dt>Last</dt><dd>${q.last.toFixed(2)} · {q.lastAt}</dd></div>
                <div><dt>Bid</dt><dd>${q.bid.toFixed(2)} · {q.bidAt}</dd></div>
                <div><dt>Ask</dt><dd>${q.ask.toFixed(2)} · {q.askAt}</dd></div>
                <div><dt>Retrieved</dt><dd>{q.retrievedAt}</dd></div>
                <div><dt>Oldest quote age</dt><dd>{((now - q.expiresAt + limit * 1000) / 1000).toFixed(1)} seconds</dd></div>
                <div><dt>Provider outcome</dt><dd>SUCCESS</dd></div>
              </dl> : <p className="text-xs font-mono">{q.status === "unavailable"
                ? <>Unavailable. {q.reason}{q.ageSeconds !== undefined && ` Oldest age ${q.ageSeconds.toFixed(1)} seconds.`}</>
                : now === null ? "Checking quote freshness…"
                  : now >= q.expiresAt ? "Unavailable. Quote expired since refresh."
                    : "Unavailable. Browser time precedes provider retrieval."}</p>}
            </section>
          );
        })}
      </div>
      <button className="text-accent underline text-sm" disabled={pending}
        onClick={() => startTransition(() => router.refresh())}>Refresh Public quotes</button>
    </section>
  );
}
