/** Dashboard presentation policy; research and archive verification stay in the backend. */
type Symbol = "SPY" | "QQQ";
type Mode = "current" | "historical";
type Failure = { code: string; requestId?: string };
export type DashboardObservation = {
  mode: Mode; spot: number; observedAt: string; sessionDate: string;
  provider: string; ageSeconds: number; expiration: string; validUntil: number | null;
};
export type DashboardResult = {
  observation: DashboardObservation | null;
  currentFailure?: Failure;
  historicalFailure?: Failure;
};

const messages: Record<string, string> = {
  archive_stale: "Current market evidence is stale. Live market evidence is unavailable.",
  archive_missing: "No verified archive is available for this symbol.",
  archive_unavailable: "Archive evidence could not be verified.",
  archive_research_unavailable: "This archive cannot support the requested research.",
  archive_expiration_unavailable: "The archive does not support the requested expiration.",
  backend_endpoint_unavailable: "This backend deployment does not support archive research.",
  backend_rejected_request: "The backend does not support this research request.",
  backend_authentication_required: "Backend authentication is required. Server credentials were not accepted.",
  backend_authentication_rejected: "Backend authentication was rejected.",
  backend_unreachable: "The research backend could not be reached.",
  backend_timeout: "The research backend request timed out.",
  backend_service_unavailable: "The research backend service is unavailable.",
  backend_not_configured: "The website research backend is not configured.",
  invalid_backend_configuration: "The website research backend configuration is invalid.",
  backend_api_not_configured: "The research API is not configured on the backend.",
  backend_internal_error: "The backend could not complete research. No evidence was accepted.",
  backend_rate_limited: "The backend is rate limiting research. Wait briefly and refresh.",
  archive_not_configured: "The backend archive is not configured.",
  response_schema_mismatch: "Research evidence failed dashboard validation.",
  historical_session_incomplete: "The latest archive session has not completed. Historical fallback is unavailable.",
};
export function dashboardMessage(code: string): string {
  return messages[code] ?? "Verified research is unavailable. No substitute evidence was displayed.";
}
function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown> : {};
}
function timestamp(value: unknown): number {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value)
    ? Date.parse(value) : NaN;
}
function correlation(value: string | null): string | undefined {
  return value && /^[a-f0-9]{32}$/.test(value) ? value : undefined;
}

function observation(value: unknown, symbol: Symbol, mode: Mode, now: number): DashboardObservation | string {
  const outer = record(value), envelope = record(outer.research), request = record(envelope.request);
  const research = record(envelope.research), archive = record(research.archive);
  const storage = record(archive.storage), observed = record(archive.observation), freshness = record(archive.freshness);
  const session = record(research.research_session), market = record(session.market);
  const state = record(session.opportunity_state), evidence = record(state.evidence);
  const time = record(record(evidence.time_state).observations), bounds = record(time.session);
  const at = timestamp(observed.observed_at), requested = timestamp(freshness.as_of);
  const open = timestamp(bounds.open), close = timestamp(bounds.close);
  const date = archive.session_date;
  const age = freshness.age_seconds, spot = market.spot;
  if (outer.source !== "alphaos_research_api" || outer.verified_for_trading !== false ||
      envelope.schema_version !== "alphaos-interface-v2" || envelope.read_only !== true ||
      request.symbol !== symbol || request.research_mode !== mode || research.symbol !== symbol ||
      research.research_mode !== mode || research.read_only !== true || session.symbol !== symbol ||
      market.symbol !== symbol || (session.status !== "complete" && session.status !== "no_candidate") ||
      !Array.isArray(session.candidates) || !Array.isArray(session.unavailable_routes) ||
      !Array.isArray(envelope.caveats) || typeof record(envelope.provenance).source !== "string" ||
      typeof spot !== "number" || !Number.isFinite(spot) || spot <= 0 ||
      !Number.isFinite(at) || !Number.isFinite(requested) || at > requested || at > now ||
      timestamp(research.as_of) !== at || timestamp(session.as_of) !== at ||
      timestamp(storage.observed_at) !== at || timestamp(time.observed_at) !== at ||
      !Number.isFinite(open) || !Number.isFinite(close) || !(open <= at && at < close) ||
      typeof date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(date) ||
      new Date(at).toLocaleDateString("en-CA", {timeZone:"America/New_York"}) !== date ||
      storage.session_date !== date || storage.symbol !== symbol || storage.provider !== archive.provider ||
      observed.provider !== archive.provider || typeof archive.provider !== "string" || !archive.provider ||
      !["complete", "partial"].includes(String(storage.quality_status)) ||
      storage.quality_status !== observed.options_status ||
      typeof storage.archive_sha256 !== "string" || !/^[a-f0-9]{64}$/.test(storage.archive_sha256) ||
      typeof storage.archive_path !== "string" || !storage.archive_path ||
      typeof age !== "number" || !Number.isFinite(age) || age < 0 ||
      typeof research.expiration !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(research.expiration)) {
    return "response_schema_mismatch";
  }
  let validUntil: number | null = null;
  if (mode === "historical") {
    if (freshness.max_age_seconds !== null) return "response_schema_mismatch";
    if (close > now || close > requested) return "historical_session_incomplete";
  } else {
    const limit = freshness.max_age_seconds;
    if (typeof limit !== "number" || !Number.isFinite(limit) || limit < 0 || limit > 600 ||
        age > limit || (now - at) / 1000 > limit) return "response_schema_mismatch";
    validUntil = Math.min(at + limit * 1000, requested + (limit - age) * 1000);
    if (validUntil < now) return "response_schema_mismatch";
  }
  return {mode, spot, observedAt: observed.observed_at as string, sessionDate: date,
    provider: archive.provider, ageSeconds: age, expiration: research.expiration, validUntil};
}

/** Only explicit stale-current failures may initiate a separately labeled historical request. */
export async function loadDashboardResearch(symbol: Symbol, request: typeof fetch = fetch,
    now: () => number = Date.now): Promise<DashboardResult> {
  async function read(mode: Mode): Promise<{data?: DashboardObservation; failure?: Failure}> {
    let requestId: string | undefined;
    try {
      const response = await request("/api/research/market", {
        method:"POST", headers:{"Content-Type":"application/json"}, cache:"no-store",
        body:JSON.stringify({symbol, research_mode:mode}), signal:AbortSignal.timeout(14000),
      });
      requestId = correlation(response.headers.get("X-AlphaOS-Request-ID"));
      const body: unknown = await response.json();
      if (!response.ok) {
        const code = record(body).code;
        return {failure:{code: typeof code === "string" && Object.hasOwn(messages, code)
          ? code : "research_unavailable", requestId}};
      }
      const parsed = observation(body, symbol, mode, now());
      return typeof parsed === "string" ? {failure:{code:parsed, requestId}} : {data:parsed};
    } catch (error) {
      const code = error instanceof DOMException && ["TimeoutError", "AbortError"].includes(error.name)
        ? "backend_timeout" : error instanceof TypeError ? "backend_unreachable" : "response_schema_mismatch";
      return {failure:{code, requestId}};
    }
  }
  const current = await read("current");
  if (current.data) return {observation:current.data};
  if (current.failure?.code !== "archive_stale") return {observation:null, currentFailure:current.failure};
  const historical = await read("historical");
  return {observation:historical.data ?? null, currentFailure:current.failure, historicalFailure:historical.failure};
}
