/** Presentation only: preserve backend economics and exclusions; never price or rank. */
export type RecordValue = Record<string, unknown>;
export function record(value: unknown): RecordValue {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as RecordValue : {};
}
export function buyingPower(value: string): number | null {
  if (!/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(value.trim())) return null;
  const amount = Number(value);
  return Number.isFinite(amount) && amount > 0 ? amount : null;
}
export function archiveExpirations(session: RecordValue, archive?: RecordValue): string[] {
  const entries = record(archive?.expiration_coverage).entries;
  if (Array.isArray(entries)) return [...new Set(entries.filter(entry =>
    record(entry).status === "archived_observations" && record(entry).eligible_date === true)
    .map(entry => record(entry).expiration).filter((expiry): expiry is string =>
      typeof expiry === "string" && /^\d{4}-\d{2}-\d{2}$/.test(expiry)))].sort();
  const available = record(record(session.diagnostics).expiration_selection).available;
  const observation = record(record(session.market).archive_observation);
  const failures = Array.isArray(observation.expiration_failures) ? observation.expiration_failures : [];
  const failed = new Set(failures.map(item => record(item).expiration));
  return Array.isArray(available) ? [...new Set(available.filter((x): x is string =>
    typeof x === "string" && !failed.has(x) && /^\d{4}-\d{2}-\d{2}$/.test(x)))].sort() : [];
}
export function candidateViews(session: RecordValue) {
  const accepted = Array.isArray(session.candidates) ? session.candidates : [];
  const excluded = Array.isArray(session.excluded) ? session.excluded : [];
  return [...accepted.map(entry => ({ entry: record(entry), excluded: false })),
    ...excluded.filter(entry => Object.keys(record(record(entry).research)).length > 0)
      .map(entry => ({ entry: record(entry), excluded: true }))].map(({entry, excluded}) => {
    const research = record(entry.research);
    const trade = record(research.trade);
    const position = record(research.position);
    const risk = research.capital_at_risk;
    const knownRisk = typeof risk === "number" && Number.isFinite(risk) && risk >= 0;
    return { ...entry,
      capital_status: entry.reason === "exceeds_available_capital" ? "Capital-ineligible"
        : excluded ? "Excluded" : knownRisk && typeof session.available_capital === "number"
          ? "Capital-eligible (backend max-loss filter)" : "Capital eligibility unavailable",
      research: { ...research,
        strategy_family: research.strategy_family ?? entry.strategy_family ?? trade.strategy_family,
        expiration: research.expiration ?? position.expiration ?? trade.expiration,
        legs: position.legs ?? research.legs ?? trade.legs,
        // Long options expose premium_per_share; do not reconstruct package prices.
        entry_debit: research.entry_debit ?? research.premium_per_share,
      },
    };
  });
}
