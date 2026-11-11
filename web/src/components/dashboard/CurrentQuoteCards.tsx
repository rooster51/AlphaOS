"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { retainVerifiedQuote, unavailable, type CurrentQuote } from "@/lib/current-quotes";

function QuoteCard({ symbol, limit }: { symbol: "SPY" | "QQQ"; limit: number }) {
  const [latest, setLatest] = useState<CurrentQuote | null>(null);
  const [verified, setVerified] = useState<CurrentQuote | null>(null);
  const [now, setNow] = useState<number | null>(null);
  const [pending, setPending] = useState(false);
  const active = useRef<AbortController | null>(null);
  const refresh = useCallback(async () => {
    if (active.current) return;
    const controller = new AbortController();
    active.current = controller;
    setPending(true);
    let result: CurrentQuote;
    try {
      const response = await fetch(`/api/current-quote?symbol=${symbol}`, {
        cache: "no-store", signal: controller.signal,
      });
      if (response.status === 401 || response.status === 403 || response.redirected) {
        result = unavailable("authentication_failure", "Preview authorization failed.");
      } else {
        const payload = await response.json() as CurrentQuote | null;
        if (payload?.status === "unavailable") result = payload;
        else if (response.ok && payload?.status === "fresh" && payload.symbol === symbol) result = payload;
        else result = unavailable("invalid_quote", "Preview quote response was invalid.");
      }
    } catch {
      result = unavailable("backend_unreachable", "Preview quote request failed.");
    }
    if (active.current !== controller) return;
    active.current = null;
    setLatest(result);
    setVerified(previous => retainVerifiedQuote(previous, result));
    setNow(Date.now());
    setPending(false);
  }, [symbol]);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 250);
    return () => {
      active.current?.abort();
      active.current = null;
      window.clearInterval(timer);
    };
  }, []);

  const q = verified?.status === "fresh" ? verified : null;
  const age = q && now !== null ? (now - q.expiresAt + limit * 1000) / 1000 : null;
  const stale = age !== null && age >= limit;
  const clockValid = q && now !== null && now >= Date.parse(q.retrievedAt);
  return (
    <section aria-label={`${symbol} current quote`} className="bg-terminal-900 border border-terminal-800 rounded p-5 space-y-2">
      <h3 className="font-semibold">{symbol}</h3>
      {latest?.status === "unavailable" && (
        <p role="status" className="text-xs font-mono">
          Unavailable · {latest.code} · {latest.reason}
          {latest.ageSeconds !== undefined && ` Oldest age ${latest.ageSeconds.toFixed(1)} seconds.`}
        </p>
      )}
      {q && clockValid ? <>
        <p className="text-xs font-mono">{stale ? "STALE · Last verified observation" :
          latest?.status === "unavailable" ? "Last verified observation · refresh failed" : "Current Public quote"}</p>
        <dl className="text-xs font-mono space-y-1">
          <div><dt>Last</dt><dd>${q.last.toFixed(2)} · {q.lastAt}</dd></div>
          <div><dt>Bid</dt><dd>${q.bid.toFixed(2)} · {q.bidAt}</dd></div>
          <div><dt>Ask</dt><dd>${q.ask.toFixed(2)} · {q.askAt}</dd></div>
          <div><dt>Retrieved</dt><dd>{q.retrievedAt}</dd></div>
          <div><dt>Oldest quote age</dt><dd>{age?.toFixed(1)} seconds</dd></div>
          <div><dt>Observation outcome</dt><dd>SUCCESS</dd></div>
        </dl>
      </> : q ? <p className="text-xs font-mono">Unavailable · Browser time precedes provider retrieval.</p>
        : latest === null ? <p className="text-xs font-mono">Refresh this symbol to request a current Public quote.</p> : null}
      <button className="text-accent underline text-sm" disabled={pending} onClick={() => void refresh()}>
        {pending ? `Refreshing ${symbol}…` : `Refresh ${symbol} quote`}
      </button>
    </section>
  );
}

export function CurrentQuoteCards({ limit }: { limit: number }) {
  return (
    <section aria-labelledby="current-market-quotes" className="space-y-3">
      <h2 id="current-market-quotes" className="text-lg font-semibold">Current Market Quotes</h2>
      <p className="text-xs font-mono">Public · maximum age {limit} seconds across last, bid and ask.</p>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <QuoteCard symbol="SPY" limit={limit} />
        <QuoteCard symbol="QQQ" limit={limit} />
      </div>
    </section>
  );
}
