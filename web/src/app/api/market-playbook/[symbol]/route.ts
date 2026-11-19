import { readRuntimeBindings } from "#alphaos-runtime";
import { parsePlaybook } from "../../../../lib/market-playbook.ts";
import { getServerConfig } from "../../../../lib/server-config.ts";
import { sessionRole } from "../../../../lib/website-auth.ts";

const headers = {
  "Cache-Control": "private, no-store",
  Vary: "Cookie",
  "X-Content-Type-Options": "nosniff",
  "X-Robots-Tag": "noindex, nofollow",
};

function failure(status: number, code: string) {
  return Response.json({ code }, { status, headers });
}

export async function POST(request: Request, context: { params: Promise<{ symbol: string }> }) {
  const { bindings } = readRuntimeBindings();
  const role = await sessionRole(request, {
    ALPHAOS_PASSWORD_HASH: bindings.ALPHAOS_PASSWORD_HASH,
    ALPHAOS_SESSION_KEY: bindings.ALPHAOS_SESSION_KEY,
  });
  if (!role) return failure(401, "authentication_required");
  if (role !== "owner") return failure(403, "owner_only");
  if (request.headers.get("origin") !== new URL(request.url).origin
    || request.headers.get("sec-fetch-site") === "cross-site"
    || request.headers.get("X-AlphaOS-Playbook") !== "observe") return failure(403, "csrf_rejected");
  if (process.env.ALPHAOS_MARKET_PLAYBOOK_ENABLED !== "true") return failure(503, "feature_disabled");
  const { symbol } = await context.params;
  if (symbol !== "SPY" && symbol !== "QQQ") return failure(400, "invalid_symbol");
  const { base, token, diagnostics } = getServerConfig();
  if (!base || !token || diagnostics.configuration !== "ready") {
    return failure(503, "backend_not_configured");
  }

  try {
    const response = await fetch(new URL(`/v1/market-playbook/${symbol}`, base), {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "X-AlphaOS-Data-Use": "owner_private_display",
        Accept: "application/json",
      },
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(12_000)]),
    });
    if (response.status === 403) return failure(403, "data_use_denied");
    if (!response.ok) return failure(503, "playbook_unavailable");
    const value = parsePlaybook(await response.json(), symbol);
    return value ? Response.json(value, { headers }) : failure(502, "invalid_playbook");
  } catch {
    return failure(503, "playbook_unavailable");
  }
}
