import { STRUCTURE_PATH, postStructure } from "../../../../lib/structure-bridge.ts";
import { parseStructureRequest } from "../../../../lib/structure-contract.ts";
import { structureView } from "../../../../lib/structure-view.ts";

/**
 * Read-only bridge for one explicit option structure.
 * Prices and risk stay in the backend; the browser sends the scenario only.
 */
export async function POST(request: Request) {
  let payload: ReturnType<typeof parseStructureRequest>;
  try {
    payload = parseStructureRequest(await request.json());
  } catch {
    payload = null;
  }
  if (!payload) {
    return Response.json(
      { error: "Invalid structure request" },
      { status: 400, headers: { "Cache-Control": "no-store" } },
    );
  }
  return postStructure(STRUCTURE_PATH, payload, request, (envelope) => structureView(envelope) !== null);
}
