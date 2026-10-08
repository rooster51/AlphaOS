"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  LineChart,
  Compass,
  History,
  BookOpen,
  ShieldAlert,
  Settings,
  Terminal,
} from "lucide-react";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/market", label: "Market Research", icon: LineChart },
  { href: "/strategies", label: "Strategy Explorer", icon: Compass },
  { href: "/session", label: "Session Review", icon: History },
  { href: "/journal", label: "Trade Journal", icon: BookOpen, badge: "Foundation" },
  { href: "/risk", label: "Portfolio Risk", icon: ShieldAlert },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 border-r border-terminal-800 bg-terminal-950 flex flex-col justify-between shrink-0 select-none">
      <div>
        {/* Brand header */}
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

        {/* Navigation links */}
        <nav className="p-3 space-y-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href || (item.href !== "/" && pathname?.startsWith(item.href));

            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center justify-between px-3 py-2 rounded text-xs font-mono transition-colors ${
                  isActive
                    ? "bg-terminal-850 text-terminal-100 border border-terminal-700 font-semibold"
                    : "text-terminal-400 hover:text-terminal-200 hover:bg-terminal-900"
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <Icon className={`w-4 h-4 ${isActive ? "text-profit" : "text-terminal-500"}`} />
                  <span>{item.label}</span>
                </div>
                {item.badge && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-terminal-800 border border-terminal-700 text-terminal-400">
                    {item.badge}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Terminal System Footnote */}
      <div className="p-4 border-t border-terminal-800/80 bg-terminal-950/60 font-mono text-[11px] text-terminal-500">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-terminal-400 font-semibold">Engine Runtime</span>
          <span className="text-profit flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-profit animate-pulse" />
            Verified
          </span>
        </div>
        <div className="text-[10px] text-terminal-500 truncate">
          SHA: <code className="text-terminal-300">6d6bb56</code> (Render)
        </div>
        <div className="text-[10px] text-terminal-500 mt-1">
          Read-only Mode: Active
        </div>
      </div>
    </aside>
  );
}
