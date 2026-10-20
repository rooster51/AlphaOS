"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { dashboardMessage, loadDashboardResearch } from "@/lib/dashboard-research";
import type { DashboardResult } from "@/lib/dashboard-research";

export function DashboardResearch({symbol}: {symbol: "SPY" | "QQQ"}) {
  const [result, setResult] = useState<DashboardResult | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setResult(null);
    loadDashboardResearch(symbol).then(value => { if (active) setResult(value); });
    return () => { active = false; };
  }, [symbol, attempt]);
  const data = result?.observation;
  useEffect(() => {
    if (!data || data.validUntil === null) return;
    const timer = setTimeout(() => setResult(previous => previous?.observation === data
      ? {observation:null, currentFailure:{code:"archive_stale"}} : previous),
      Math.max(0, data.validUntil - Date.now()));
    return () => clearTimeout(timer);
  }, [data]);
  return (
    <section aria-label={`${symbol} evidence`} className="bg-terminal-900 border border-terminal-800 rounded p-5 space-y-3">
      <h2 className="font-mono font-bold text-terminal-100">{symbol}</h2>
      <div aria-live="polite" className="space-y-3">
        {!result && <p className="text-xs font-mono">Checking verified archive evidence…</p>}
        {result?.currentFailure && <div className="text-warning text-sm">
          <p>{dashboardMessage(result.currentFailure.code)}</p>
          {result.currentFailure.requestId && <p className="text-xs">Current request ID: {result.currentFailure.requestId}</p>}
        </div>}
        {data && <>
          <p className="font-mono font-bold text-warning border border-warning rounded p-3">
            {data.mode === "historical" ? "HISTORICAL — COMPLETED SESSION ARCHIVE" : "CURRENT — VERIFIED ARCHIVE OBSERVATION"}
          </p>
          <p className="text-sm">{data.mode === "historical"
            ? "Historical context only. This is an intraday observation from a completed session, not a closing price, live quote, or current trading opportunity."
            : "Fresh archive evidence only. This is not an executable quote or trading recommendation."}</p>
          <dl className="font-mono text-xs space-y-2">
            <div><dt>Observed underlying price</dt><dd>${data.spot.toFixed(2)}</dd></div>
            <div><dt>Source</dt><dd>{data.provider} · verified Supabase archive</dd></div>
            <div><dt>Source timestamp</dt><dd>{data.observedAt}</dd></div>
            <div><dt>Session date (New York)</dt><dd>{data.sessionDate}</dd></div>
            <div><dt>Archive age at request</dt><dd>{data.ageSeconds} seconds</dd></div>
            <div><dt>Archived expiration</dt><dd>{data.expiration}</dd></div>
          </dl>
        </>}
        {result?.historicalFailure && <div className="text-warning text-sm">
          <p>Historical context unavailable: {dashboardMessage(result.historicalFailure.code)}</p>
          {result.historicalFailure.requestId && <p className="text-xs">Historical request ID: {result.historicalFailure.requestId}</p>}
        </div>}
        {result && !data && <p className="text-xs font-mono">No substitute or unverified market data has been displayed.</p>}
      </div>
      <p className="text-xs text-terminal-400">Live-only signals, probability estimates, expected value, and actionable trade recommendations are unavailable. No candidates are presented as trades.</p>
      <div className="flex gap-4 text-xs">
        <button className="text-accent underline" onClick={() => setAttempt(value => value + 1)}>Refresh {symbol} evidence</button>
        <Link href={`/market?symbol=${symbol}`} className="text-accent underline">Open {symbol} market research</Link>
      </div>
    </section>
  );
}
