/**
 * Browser-side calls to the website's structure bridge.
 *
 * Only same-origin route handlers are called, so no token or backend URL ever
 * reaches the browser. Failures stay explicit codes; nothing is substituted.
 */
import {
  STRUCTURE_SOURCE,
  record,
  type CompareRequestInput,
  type StructureRequestInput,
} from "./structure-contract.ts";
import {
  observationSeed,
  structureViewFor,
  compareViewFor,
  type CompareView,
  type ObservationSeed,
  type StructureView,
} from "./structure-view.ts";

/** Above the server's own upstream budget so its classified error wins. */
const CLIENT_TIMEOUT_MS = 30_000;

type Failure = { ok: false; code: string };

async function callRoute(
  path: string,
  payload: unknown,
  request: typeof fetch,
  timeoutMs: number,
): Promise<{ ok: true; response: Response } | Failure> {
  let response: Response;
  try {
    response = await request(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (error) {
    if (error instanceof DOMException && (error.name === "TimeoutError" || error.name === "AbortError")) {
      return { ok: false, code: "backend_timeout" };
    }
    if (error instanceof TypeError) return { ok: false, code: "backend_unreachable" };
    return { ok: false, code: "response_schema_mismatch" };
  }
  if (!response.ok) {
    let code = "research_unavailable";
    try {
      const body = record(await response.json());
      const candidate = body?.code;
      if (typeof candidate === "string" && /^[a-z][a-z0-9_]{0,63}$/.test(candidate)) {
        code = candidate;
      }
    } catch {
      code = response.status === 400 ? "invalid_structure_request" : "research_unavailable";
    }
    return { ok: false, code };
  }
  return { ok: true, response };
}

async function readEnvelope(
  response: Response,
): Promise<{ ok: true; envelope: Record<string, unknown> } | Failure> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return { ok: false, code: "response_schema_mismatch" };
  }
  const outer = record(body);
  if (outer?.verified_for_trading !== false || outer.source !== STRUCTURE_SOURCE) {
    return { ok: false, code: "response_schema_mismatch" };
  }
  return { ok: true, envelope: outer };
}

export type StructureOutcome = { ok: true; view: StructureView } | Failure;

export async function requestStructure(
  payload: StructureRequestInput,
  request: typeof fetch = fetch,
): Promise<StructureOutcome> {
  const called = await callRoute("/api/research/structure", payload, request, CLIENT_TIMEOUT_MS);
  if (!called.ok) return called;
  const outer = await readEnvelope(called.response);
  if (!outer.ok) return outer;
  const view = structureViewFor(outer.envelope.research, payload);
  return view ? { ok: true, view } : { ok: false, code: "response_schema_mismatch" };
}

export type CompareOutcome = { ok: true; view: CompareView } | Failure;

export async function requestComparison(
  payload: CompareRequestInput,
  request: typeof fetch = fetch,
): Promise<CompareOutcome> {
  const called = await callRoute("/api/research/structures/compare", payload, request, CLIENT_TIMEOUT_MS);
  if (!called.ok) return called;
  const outer = await readEnvelope(called.response);
  if (!outer.ok) return outer;
  const view = compareViewFor(outer.envelope.research, payload);
  return view ? { ok: true, view } : { ok: false, code: "response_schema_mismatch" };
}

export type ObservationOutcome = { ok: true; seed: ObservationSeed } | Failure;

/** Reuses the existing observation-only bridge; performs no structure research. */
export async function requestObservation(
  symbol: "SPY" | "QQQ",
  request: typeof fetch = fetch,
): Promise<ObservationOutcome> {
  const called = await callRoute(
    "/api/research/market",
    { symbol, view: "observation" },
    request,
    CLIENT_TIMEOUT_MS,
  );
  if (!called.ok) return called;
  let body: unknown;
  try {
    body = await called.response.json();
  } catch {
    return { ok: false, code: "response_schema_mismatch" };
  }
  const seed = observationSeed(body, symbol);
  return seed ? { ok: true, seed } : { ok: false, code: "response_schema_mismatch" };
}
