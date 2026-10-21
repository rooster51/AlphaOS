/** Explicit observation-only contract. Never reinterpret it as candidate research. */
const record = (v: unknown): Record<string, unknown> => v !== null && typeof v === "object" && !Array.isArray(v) ? v as Record<string, unknown> : {};
const time = (v: unknown) => typeof v === "string" && /^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(v) ? Date.parse(v) : NaN;

export function validArchiveObservation(value: unknown, symbol: string, mode = "current", expiration?: string): boolean {
  const v=record(value), request=record(v.request), archive=record(v.archive);
  const storage=record(archive.storage), observed=record(archive.observation), fresh=record(archive.freshness), session=record(v.session);
  const at=time(v.as_of), asked=time(v.requested_as_of), open=time(session.open), close=time(session.close);
  const age=fresh.age_seconds, maximum=fresh.max_age_seconds;
  const date=archive.session_date;
  return v.schema_version === "alphaos-observation-v1" && v.read_only === true &&
    v.verified_for_trading === false && v.research_performed === false && v.evidence_scope === "archive_observation_only" &&
    !("research_session" in v) && !("candidates" in v) &&
    v.symbol === symbol && request.symbol === symbol && v.research_mode === mode && request.research_mode === mode &&
    typeof v.expiration === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v.expiration) &&
    (expiration === undefined || (v.expiration === expiration && request.expiration === expiration)) &&
    typeof v.spot === "number" && Number.isFinite(v.spot) && v.spot > 0 &&
    Number.isFinite(at) && Number.isFinite(asked) && at <= asked && open <= at && at < close &&
    time(observed.observed_at) === at && time(storage.observed_at) === at && time(fresh.as_of) === asked &&
    typeof date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(date) && storage.session_date === date &&
    new Date(at).toLocaleDateString("en-CA",{timeZone:"America/New_York"}) === date && storage.symbol === symbol &&
    typeof archive.provider === "string" && !!archive.provider && storage.provider === archive.provider && observed.provider === archive.provider &&
    ["complete","partial"].includes(String(storage.quality_status)) && storage.quality_status === observed.options_status &&
    typeof storage.archive_sha256 === "string" && /^[a-f0-9]{64}$/.test(storage.archive_sha256) &&
    typeof storage.archive_path === "string" && !!storage.archive_path &&
    typeof age === "number" && Number.isFinite(age) && age >= 0 && Math.abs(age-(asked-at)/1000) < .001 &&
    (mode === "historical" ? maximum === null : typeof maximum === "number" && Number.isFinite(maximum) && maximum >= 0 && maximum <= 600 && age <= maximum) &&
    Array.isArray(v.caveats);
}
