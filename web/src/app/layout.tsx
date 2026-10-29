import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/shell/Sidebar";
import { readRuntimeBindings } from "#alphaos-runtime";

export const metadata: Metadata = {
  title: "AlphaOS | Quantitative Options Research Terminal",
  description: "Descriptive options research, deterministic strategy routing, and risk analytics.",
  robots: { index: false, follow: false },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark h-full">
      <body className="h-full bg-terminal-950 text-terminal-100 flex antialiased">
        <Sidebar cloudflareLogin={String(readRuntimeBindings().runtime) === "cloudflare"} />
        <main className="flex-1 flex flex-col min-w-0 overflow-y-auto pt-14 md:pt-0">
          {children}
        </main>
      </body>
    </html>
  );
}
