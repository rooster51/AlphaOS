import { COMPARE_PATH, postStructure } from "../../../../../lib/structure-bridge.ts";
import { parseCompareRequest } from "../../../../../lib/structure-contract.ts";
import { compareViewFor } from "../../../../../lib/structure-view.ts";

/**
 * Read-only bridge for comparing explicit structures in supplied order.
 * The backend performs the comparison; this route adds no ranking.
 */
export async function POST(request: Request) {
  let payload: ReturnType<typeof parseCompareRequest>;
  try {
    payload = parseCompareRequest(await request.json());
  } catch {
    payload = null;
  }
  if (!payload) {
    return Response.json(
      { error: "Invalid structure comparison request" },
      { status: 400, headers: { "Cache-Control": "no-store" } },
    );
  }
  // Every echoed structure and researched candidate must match the submitted
  // scenario at the same position.
  return postStructure(COMPARE_PATH, payload, request,
    (envelope) => compareViewFor(envelope, payload) !== null);
}
