"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  LineChart,
  Compass,
  Layers,
  History,
  BookOpen,
  ShieldAlert,
  Settings,
  Terminal,
  Menu,
  X,
} from "lucide-react";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/market", label: "Market Research", icon: LineChart },
  { href: "/strategies", label: "Strategy Explorer", icon: Compass },
  { href: "/structures", label: "Structure Lab", icon: Layers },
  { href: "/session", label: "Session Review", icon: History },
  { href: "/journal", label: "Trade Journal", icon: BookOpen, badge: "Foundation" },
  { href: "/risk", label: "Portfolio Risk", icon: ShieldAlert },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar({ cloudflareLogin = false }: { cloudflareLogin?: boolean }) {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    if (!mobileOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [mobileOpen]);

  const navigation = (
    <nav aria-label="Primary navigation" className="p-3 space-y-1">
      {NAV_ITEMS.map((item) => {
        const Icon = item.icon;
        const isActive = pathname === item.href ||
          (item.href !== "/" && pathname?.startsWith(`${item.href}/`));

        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={isActive ? "page" : undefined}
            onClick={() => setMobileOpen(false)}
            className={`flex items-center justify-between px-3 py-2 rounded text-xs font-mono transition-colors ${
              isActive
                ? "bg-terminal-850 text-terminal-100 border border-terminal-700 font-semibold"
                : "text-terminal-400 hover:text-terminal-200 hover:bg-terminal-900"
            }`}
          >
            <span className="flex items-center gap-2.5">
              <Icon className={`w-4 h-4 ${isActive ? "text-profit" : "text-terminal-500"}`} />
              <span>{item.label}</span>
            </span>
            {item.badge && (
              <span className="text-[9px] px-1.5 py-0.5 rounded bg-terminal-800 border border-terminal-700 text-terminal-400">
                {item.badge}
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <>
      <div className="md:hidden fixed inset-x-0 top-0 z-30 h-14 border-b border-terminal-800 bg-terminal-950 flex items-center justify-between px-4">
        <div className="font-mono font-bold text-sm tracking-wider">
          ALPHA<span className="text-profit">OS</span>
        </div>
        <button
          type="button"
          aria-label={mobileOpen ? "Close navigation menu" : "Open navigation menu"}
          aria-expanded={mobileOpen}
          aria-controls="mobile-primary-navigation"
          onClick={() => setMobileOpen((open) => !open)}
          className="rounded border border-terminal-700 p-2 text-terminal-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-profit"
        >
          {mobileOpen ? <X aria-hidden="true" className="h-5 w-5" /> : <Menu aria-hidden="true" className="h-5 w-5" />}
        </button>
      </div>

      {mobileOpen && (
        <button
          type="button"
          aria-label="Close navigation menu"
          className="md:hidden fixed inset-0 z-30 bg-black/60"
          onClick={() => setMobileOpen(false)}
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-40 w-64 border-r border-terminal-800 bg-terminal-950 flex flex-col justify-between shrink-0 select-none transition-transform md:static md:z-auto md:translate-x-0 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div>
          <div className="h-16 flex items-center px-6 border-b border-terminal-800 gap-3">
            <div className="w-8 h-8 rounded bg-terminal-850 border border-terminal-700 flex items-center justify-center text-profit font-mono font-bold">
              <Terminal className="w-4 h-4 text-profit" />
            </div>
            <div>
              <div className="font-mono font-bold text-sm text-terminal-100 tracking-wider flex items-center gap-2">
                ALPHA<span className="text-profit">OS</span>
                <span className="text-[10px] px-1 py-0.2 bg-terminal-800 border border-terminal-700 text-terminal-400 rounded">
                  2.0
                </span>
              </div>
              <div className="text-[10px] text-terminal-500 font-mono tracking-tight">
                Quantitative Options Research
              </div>
            </div>
          </div>
          {cloudflareLogin && <form method="post" action="/auth/logout" className="px-6 py-2">
            <button type="submit" className="text-sm text-terminal-300 underline">Sign Out</button>
          </form>}
          <div className="hidden md:block">{navigation}</div>
          <div id="mobile-primary-navigation" className={mobileOpen ? "md:hidden" : "hidden"}>
            {navigation}
          </div>
        </div>

        <div className="hidden md:block p-4 border-t border-terminal-800/80 bg-terminal-950/60 font-mono text-[11px] text-terminal-500">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-terminal-400 font-semibold">Backend Status</span>
            <span className="text-terminal-400">Not assessed</span>
          </div>
          <div className="text-[10px] text-terminal-500">
            Health endpoint does not verify API access or market evidence.
          </div>
          <div className="text-[10px] text-terminal-500 mt-1">
            Read-only Mode: Active
          </div>
        </div>
      </aside>
    </>
  );
}
