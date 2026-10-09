"use client";

export default function ResearchUnavailable({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="p-8 max-w-3xl mx-auto space-y-4">
      <h1 className="font-mono text-xl font-bold">Research temporarily unavailable</h1>
      <p className="text-terminal-300 text-sm">
        AlphaOS could not verify the requested market evidence. No substitute
        prices, signals, or example trades have been presented as live data.
      </p>
      <button
        type="button"
        onClick={() => reset()}
        className="rounded border border-terminal-600 px-4 py-2 text-sm"
      >
        Retry research
      </button>
    </main>
  );
}
