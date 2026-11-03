/** Explicit observation-only contract. Never reinterpret it as candidate research. */
const record = (v: unknown): Record<string, unknown> => v !== null && typeof v === "object" && !Array.isArray(v) ? v as Record<string, unknown> : {};
const time = (v: unknown) => typeof v === "string" && /^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(v) ? Date.parse(v) : NaN;

export type ObservationValidationCategory =
  | "observation_schema_mismatch"
  | "timestamp_freshness_mismatch"
  | "archive_metadata_quality_mismatch";
export type ObservationValidation = {
  valid: boolean;
  categories: ObservationValidationCategory[];
  fields: string[];
};

export function validateArchiveObservation(value: unknown, symbol: string, mode = "current", expiration?: string): ObservationValidation {
  const v=record(value), request=record(v.request), archive=record(v.archive);
  const storage=record(archive.storage), observed=record(archive.observation), fresh=record(archive.freshness), session=record(v.session);
  const diagnostics=record(archive.diagnostics), bucketCounts=record(diagnostics.bucket_counts);
  const at=time(v.as_of), asked=time(v.requested_as_of), open=time(session.open), close=time(session.close);
  const age=fresh.age_seconds, maximum=fresh.max_age_seconds, date=archive.session_date;
  const emptyArchive=storage.quality_status === "empty" && storage.contract_count === 0 &&
    diagnostics.total_contract_count === 0 &&
    ["valid_contracts","questionable_contracts","rejected_contracts"].every(key=>bucketCounts[key] === 0);
  const recognizedQuality=["complete","partial"].includes(String(storage.quality_status)) || emptyArchive;
  const failures: {category: ObservationValidationCategory; field: string}[] = [];
  const check = (category: ObservationValidationCategory, field: string, valid: boolean) => {
    if (!valid) failures.push({category, field});
  };

  const schema = "observation_schema_mismatch";
  check(schema,"schema_version",v.schema_version === "alphaos-observation-v1");
  check(schema,"read_only",v.read_only === true);
  check(schema,"verified_for_trading",v.verified_for_trading === false);
  check(schema,"research_performed",v.research_performed === false);
  check(schema,"evidence_scope",v.evidence_scope === "archive_observation_only");
  check(schema,"research_session",!("research_session" in v));
  check(schema,"candidates",!("candidates" in v));
  check(schema,"symbol",v.symbol === symbol && request.symbol === symbol);
  check(schema,"research_mode",v.research_mode === mode && request.research_mode === mode);
  check(schema,"expiration",typeof v.expiration === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v.expiration) &&
    (expiration === undefined || (v.expiration === expiration && request.expiration === expiration)));
  check(schema,"spot",typeof v.spot === "number" && Number.isFinite(v.spot) && v.spot > 0);
  check(schema,"caveats",Array.isArray(v.caveats));

  const freshness = "timestamp_freshness_mismatch";
  check(freshness,"as_of",Number.isFinite(at));
  check(freshness,"requested_as_of",Number.isFinite(asked));
  check(freshness,"as_of_order",at <= asked);
  check(freshness,"session.open",Number.isFinite(open) && open <= at);
  check(freshness,"session.close",Number.isFinite(close) && at < close);
  check(freshness,"archive.observation.observed_at",time(observed.observed_at) === at);
  check(freshness,"archive.storage.observed_at",time(storage.observed_at) === at);
  check(freshness,"archive.freshness.as_of",time(fresh.as_of) === asked);
  check(freshness,"archive.freshness.age_seconds",typeof age === "number" && Number.isFinite(age) &&
    age >= 0 && Math.abs(age-(asked-at)/1000) < .001);
  check(freshness,"archive.freshness.max_age_seconds",mode === "historical"
    ? maximum === null
    : typeof maximum === "number" && Number.isFinite(maximum) && maximum >= 0 && maximum <= 600 &&
      typeof age === "number" && Number.isFinite(age) && age <= maximum);

  const metadata = "archive_metadata_quality_mismatch";
  check(metadata,"archive.session_date",typeof date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(date) &&
    storage.session_date === date && new Date(at).toLocaleDateString("en-CA",{timeZone:"America/New_York"}) === date);
  check(metadata,"archive.storage.symbol",storage.symbol === symbol);
  check(metadata,"archive.provider",typeof archive.provider === "string" && !!archive.provider &&
    storage.provider === archive.provider && observed.provider === archive.provider);
  check(metadata,"archive.storage.quality_status",recognizedQuality);
  check(metadata,"archive.observation.options_status",storage.quality_status === observed.options_status);
  if (storage.quality_status === "empty") {
    check(metadata,"archive.storage.contract_count",storage.contract_count === 0);
    check(metadata,"archive.diagnostics.total_contract_count",diagnostics.total_contract_count === 0);
    for (const key of ["valid_contracts","questionable_contracts","rejected_contracts"]) {
      check(metadata,`archive.diagnostics.bucket_counts.${key}`,bucketCounts[key] === 0);
    }
  }
  check(metadata,"archive.storage.archive_sha256",typeof storage.archive_sha256 === "string" && /^[a-f0-9]{64}$/.test(storage.archive_sha256));
  check(metadata,"archive.storage.archive_path",typeof storage.archive_path === "string" && !!storage.archive_path);

  return {
    valid: failures.length === 0,
    categories: [...new Set(failures.map(failure=>failure.category))],
    fields: [...new Set(failures.map(failure=>failure.field))],
  };
}

export function validArchiveObservation(value: unknown, symbol: string, mode = "current", expiration?: string): boolean {
  return validateArchiveObservation(value,symbol,mode,expiration).valid;
}
