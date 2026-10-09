import React from "react";
import { Header } from "@/components/shell/Header";
import { StatusPill } from "@/components/shell/StatusPill";
import { MOCK_GUARDRAILS } from "@/lib/mock-data";
import { Shield, Key, Sliders, Database, Cpu, Info } from "lucide-react";

export default function SettingsPage() {
  return (
    <div>
      <Header
        title="Terminal Settings & Infrastructure"
        subtitle="Account sizing, discipline parameters, API connection, and Supabase RLS configuration."
        badge={{
          label: "READ-ONLY PREVIEW",
          variant: "neutral",
        }}
      />

      <div className="p-8 space-y-6 max-w-5xl">
        {/* Identity & Codex Boundary Notice */}
        <div className="bg-terminal-900 border border-terminal-800 rounded p-4 flex items-start gap-3 text-terminal-400 font-mono text-xs">
          <Info className="w-4 h-4 text-accent shrink-0 mt-0.5" />
          <div>
            <span className="text-terminal-200 font-bold">Identity & Authentication Notice: </span>
            End-user authentication, Supabase account linking, and identity grant state machines are controlled by Codex&apos;s active identity foundation milestone (<code className="text-accent">alphaos2/identity-readiness-gate</code>).
            Settings changes on this screen currently operate in read-only preview mode.
          </div>
        </div>

        {/* Account Sizing & Risk Preferences */}
        <div className="bg-terminal-900 border border-terminal-800 rounded p-6">
          <div className="flex items-center gap-2 mb-4 font-mono text-sm font-bold text-terminal-100 uppercase">
            <Sliders className="w-4 h-4 text-profit" />
            <span>Account Sizing & Discipline Parameters</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5 font-mono text-xs">
            <div>
              <label className="block text-terminal-400 mb-1 text-[11px] uppercase">Default Portfolio Capital ($)</label>
              <input
                type="number"
                disabled
                defaultValue={MOCK_GUARDRAILS.default_account_size}
                className="w-full bg-terminal-950 border border-terminal-800 rounded px-3 py-2 text-terminal-200 opacity-80 cursor-not-allowed font-numeric"
              />
              <span className="text-[10px] text-terminal-500 mt-1 block">Used as denominator for percentage risk calculations.</span>
            </div>

            <div>
              <label className="block text-terminal-400 mb-1 text-[11px] uppercase">Max Risk Per Trade (%)</label>
              <input
                type="number"
                disabled
                defaultValue={MOCK_GUARDRAILS.default_risk_pct}
                className="w-full bg-terminal-950 border border-terminal-800 rounded px-3 py-2 text-terminal-200 opacity-80 cursor-not-allowed font-numeric"
              />
              <span className="text-[10px] text-terminal-500 mt-1 block">Cap on single-structure maximum loss.</span>
            </div>

            <div>
              <label className="block text-terminal-400 mb-1 text-[11px] uppercase">Max Daily Loss Limit (%)</label>
              <input
                type="number"
                disabled
                defaultValue={MOCK_GUARDRAILS.max_daily_loss_pct}
                className="w-full bg-terminal-950 border border-terminal-800 rounded px-3 py-2 text-terminal-200 opacity-80 cursor-not-allowed font-numeric"
              />
              <span className="text-[10px] text-terminal-500 mt-1 block">Session circuit-breaker threshold.</span>
            </div>

            <div>
              <label className="block text-terminal-400 mb-1 text-[11px] uppercase">Consecutive Loss Cooldown (Minutes)</label>
              <input
                type="number"
                disabled
                defaultValue={MOCK_GUARDRAILS.cooldown_minutes}
                className="w-full bg-terminal-950 border border-terminal-800 rounded px-3 py-2 text-terminal-200 opacity-80 cursor-not-allowed font-numeric"
              />
              <span className="text-[10px] text-terminal-500 mt-1 block">Mandatory timeout after 2 losses.</span>
            </div>
          </div>
        </div>

        {/* Backend & Supabase Connectivity Status */}
        <div className="bg-terminal-900 border border-terminal-800 rounded p-6">
          <div className="flex items-center gap-2 mb-4 font-mono text-sm font-bold text-terminal-100 uppercase">
            <Database className="w-4 h-4 text-warning" />
            <span>Infrastructure Connectivity</span>
          </div>

          <div className="space-y-3 font-mono text-xs">
            <div className="flex items-center justify-between p-3.5 bg-terminal-950 rounded border border-terminal-850">
              <div className="flex items-center gap-3">
                <Cpu className="w-4 h-4 text-accent" />
                <div>
                  <span className="font-bold text-terminal-200">AlphaOS Research API (Render)</span>
                  <div className="text-[10px] text-terminal-500">https://alphaos.onrender.com/v1 • Python 3.12.14</div>
                </div>
              </div>
              <StatusPill label="DEPLOYED (SHA 6d6bb56)" variant="archive" />
            </div>

            <div className="flex items-center justify-between p-3.5 bg-terminal-950 rounded border border-terminal-850">
              <div className="flex items-center gap-3">
                <Database className="w-4 h-4 text-warning" />
                <div>
                  <span className="font-bold text-terminal-200">Supabase Cloud Database & Storage</span>
                  <div className="text-[10px] text-terminal-500">PostgreSQL 15 • Storage Archive • RLS Enabled</div>
                </div>
              </div>
              <StatusPill label="CONFIGURED" variant="archive" />
            </div>

            <div className="flex items-center justify-between p-3.5 bg-terminal-950 rounded border border-terminal-850">
              <div className="flex items-center gap-3">
                <Key className="w-4 h-4 text-profit" />
                <div>
                  <span className="font-bold text-terminal-200">Public.com Options Market Data</span>
                  <div className="text-[10px] text-terminal-500">Canonical provider • 600s observation freshness gate</div>
                </div>
              </div>
              <StatusPill label="ACTIVE" variant="archive" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
