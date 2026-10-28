/**
 * Explicit option-structure request mapping for the website.
 *
 * Mapping and validation only. Pricing, payoff economics, capital requirements
 * and risk stay in the canonical backend; nothing here recomputes them.
 * The field names and bounds mirror alphaos_api.research2.StructureRequest.
 */

export type StructureSymbol = "SPY" | "QQQ";
export type StructureLegType = "Call" | "Put";

export interface StructureLegInput {
  type: StructureLegType;
  strike: number;
  qty: number;
  contract?: string;
}

export interface StructureRequestInput {
  symbol: StructureSymbol;
  expiration: string;
  as_of: string;
  spot: number;
  credit: number;
  fees: number;
  legs: StructureLegInput[];
  market_data?: { snapshot_id: string; archive_sha256: string };
}

export interface CompareRequestInput {
  structures: StructureRequestInput[];
  thesis?: string;
}

/** Marker the website bridge adds to a validated structure envelope. */
export const STRUCTURE_SOURCE = "alphaos_research_structure_api";

export const MAX_LEGS = 4;
export const MAX_COMPARE_STRUCTURES = 20;
export const MAX_LEG_QUANTITY = 100;
export const MAX_THESIS_LENGTH = 1000;

const SYMBOLS = new Set<string>(["SPY", "QQQ"]);
const LEG_TYPES = new Set<string>(["Call", "Put"]);
const STRUCTURE_KEYS = new Set(["symbol", "expiration", "as_of", "spot", "credit", "fees", "legs", "market_data"]);
const LEG_KEYS = new Set(["type", "strike", "qty", "contract"]);
const COMPARE_KEYS = new Set(["structures", "thesis"]);

export function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

/** Strict calendar date in YYYY-MM-DD form; no timezone guessing. */
export function isoDate(value: unknown): string | null {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value
    ? value
    : null;
}

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function positiveNumber(value: unknown): number | null {
  const number = finiteNumber(value);
  return number !== null && number > 0 ? number : null;
}

function nonNegativeNumber(value: unknown): number | null {
  const number = finiteNumber(value);
  return number !== null && number >= 0 ? number : null;
}

function wholeNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) ? value : null;
}

/** Validate the exact JSON body the browser sends to /api/research/structure. */
export function parseStructureRequest(value: unknown): StructureRequestInput | null {
  const input = record(value);
  if (!input) return null;
  if (Object.keys(input).some((key) => !STRUCTURE_KEYS.has(key))) return null;

  const symbol = typeof input.symbol === "string" ? input.symbol.toUpperCase() : "";
  if (!SYMBOLS.has(symbol)) return null;

  const expiration = isoDate(input.expiration);
  const asOf = isoDate(input.as_of);
  if (!expiration || !asOf) return null;
  // The backend reports a negative days-to-expiration as invalid_structure.
  if (expiration < asOf) return null;

  const spot = positiveNumber(input.spot);
  const credit = finiteNumber(input.credit);
  const fees = input.fees === undefined ? 0 : nonNegativeNumber(input.fees);
  if (spot === null || credit === null || fees === null) return null;

  if (!Array.isArray(input.legs) || input.legs.length < 1 || input.legs.length > MAX_LEGS) {
    return null;
  }
  const legs: StructureLegInput[] = [];
  let reference: StructureRequestInput["market_data"];
  if (input.market_data !== undefined && input.market_data !== null) {
    const ref = record(input.market_data);
    if (!ref || Object.keys(ref).some(k=>!["snapshot_id","archive_sha256"].includes(k)) ||
        typeof ref.snapshot_id !== "string" || ref.snapshot_id.length < 1 || ref.snapshot_id.length > 128 ||
        typeof ref.archive_sha256 !== "string" || !/^[a-f0-9]{64}$/.test(ref.archive_sha256)) return null;
    reference = { snapshot_id: ref.snapshot_id, archive_sha256: ref.archive_sha256 };
  }
  for (const raw of input.legs) {
    const leg = record(raw);
    if (!leg) return null;
    if (Object.keys(leg).some((key) => !LEG_KEYS.has(key))) return null;
    if (typeof leg.type !== "string" || !LEG_TYPES.has(leg.type)) return null;
    const strike = positiveNumber(leg.strike);
    const qty = wholeNumber(leg.qty);
    if (strike === null || qty === null || qty === 0 || Math.abs(qty) > MAX_LEG_QUANTITY) {
      return null;
    }
    const contract = leg.contract;
    if (reference ? typeof contract !== "string" || contract.length > 32 || !/^[A-Z]{1,6}\s*\d{6}[CP]\d{8}$/.test(contract)
        : contract !== undefined && contract !== null) return null;
    legs.push({ type: leg.type as StructureLegType, strike, qty,
      ...(reference ? { contract: contract as string } : {}) });
  }

  return {
    symbol: symbol as StructureSymbol,
    expiration,
    as_of: asOf,
    spot,
    credit,
    fees,
    legs,
    ...(reference ? { market_data: reference } : {}),
  };
}

/** Validate the exact JSON body the browser sends to the comparison route. */
export function parseCompareRequest(value: unknown): CompareRequestInput | null {
  const input = record(value);
  if (!input) return null;
  if (Object.keys(input).some((key) => !COMPARE_KEYS.has(key))) return null;
  if (!Array.isArray(input.structures) ||
      input.structures.length < 1 ||
      input.structures.length > MAX_COMPARE_STRUCTURES) {
    return null;
  }
  const structures: StructureRequestInput[] = [];
  for (const raw of input.structures) {
    const parsed = parseStructureRequest(raw);
    if (!parsed) return null;
    structures.push(parsed);
  }
  if (input.thesis !== undefined) {
    if (typeof input.thesis !== "string" || input.thesis.length > MAX_THESIS_LENGTH) return null;
    return input.thesis.trim()
      ? { structures, thesis: input.thesis }
      : { structures };
  }
  return { structures };
}

export interface LegDraft {
  contract?: string;
  type: string;
  action: "Buy" | "Sell";
  strike: string;
  quantity: string;
}

export interface StructureForm {
  symbol: string;
  expiration: string;
  asOf: string;
  spot: string;
  /** A debit is submitted as a negative signed package cashflow. */
  side: "debit" | "credit";
  packagePrice: string;
  fees: string;
  legs: LegDraft[];
}

export type BuildResult =
  | { ok: true; value: StructureRequestInput }
  | { ok: false; errors: string[] };

/**
 * Map typed form text to the backend request contract.
 *
 * The API takes one signed package cashflow per share for the whole package,
 * plus signed leg quantities; it does not accept per-leg entry prices. Fees are
 * total package dollars, matching the backend contract.
 */
export function buildStructureRequest(form: StructureForm): BuildResult {
  const errors: string[] = [];
  const symbol = String(form.symbol ?? "").trim().toUpperCase();
  if (!SYMBOLS.has(symbol)) {
    errors.push("Symbol must be SPY or QQQ.");
  }
  const expiration = isoDate(String(form.expiration ?? "").trim());
  const asOf = isoDate(String(form.asOf ?? "").trim());
  if (!expiration) errors.push("Expiration must be a valid YYYY-MM-DD date.");
  if (!asOf) errors.push("Research date must be a valid YYYY-MM-DD date.");
  if (expiration && asOf && expiration < asOf) {
    errors.push("Expiration must not precede the research date.");
  }
  const spot = positiveNumber(Number(String(form.spot ?? "").trim()));
  if (spot === null) errors.push("Spot must be a positive number.");
  // An explicitly entered zero is a real cashflow (a zero-cost package stays
  // zero); blank text is missing input, not zero, so it is still rejected.
  const priceText = String(form.packagePrice ?? "").trim();
  const price = priceText === "" ? null : nonNegativeNumber(Number(priceText));
  if (price === null) {
    errors.push("Package price per share must be zero or a positive number.");
  }
  const feesText = String(form.fees ?? "").trim();
  const fees = feesText === "" ? 0 : nonNegativeNumber(Number(feesText));
  if (fees === null) errors.push("Fees must be a nonnegative dollar amount.");

  if (!Array.isArray(form.legs) || form.legs.length < 1 || form.legs.length > MAX_LEGS) {
    errors.push(`Enter between 1 and ${MAX_LEGS} option legs.`);
  }
  const legs: StructureLegInput[] = [];
  (Array.isArray(form.legs) ? form.legs : []).forEach((leg, index) => {
    const label = `Leg ${index + 1}`;
    const type = String(leg.type ?? "").trim();
    if (!LEG_TYPES.has(type)) {
      errors.push(`${label}: type must be Call or Put.`);
    }
    const strike = positiveNumber(Number(String(leg.strike ?? "").trim()));
    if (strike === null) errors.push(`${label}: strike must be a positive number.`);
    const quantity = wholeNumber(Number(String(leg.quantity ?? "").trim()));
    if (quantity === null || quantity < 1 || quantity > MAX_LEG_QUANTITY) {
      errors.push(`${label}: quantity must be a whole number from 1 to ${MAX_LEG_QUANTITY}.`);
    }
    if (leg.action !== "Buy" && leg.action !== "Sell") {
      errors.push(`${label}: action must be Buy or Sell.`);
    }
    if (LEG_TYPES.has(type) && strike !== null && quantity !== null &&
        quantity >= 1 && quantity <= MAX_LEG_QUANTITY) {
      legs.push({
        type: type as StructureLegType,
        strike,
        qty: leg.action === "Sell" ? -quantity : quantity,
      });
    }
  });

  if (errors.length) return { ok: false, errors };
  const signed = form.side === "credit" ? (price as number) : -(price as number);
  return {
    ok: true,
    value: {
      symbol: symbol as StructureSymbol,
      expiration: expiration as string,
      as_of: asOf as string,
      spot: spot as number,
      // A zero-cost debit normalizes from -0 to 0 so the wire value is exact.
      credit: signed === 0 ? 0 : signed,
      fees: fees as number,
      legs,
    },
  };
}

/** Human label for saved scenarios; presentation text only. */
export function structureLabel(request: StructureRequestInput): string {
  const legs = request.legs
    .map((leg) => `${leg.type} ${leg.strike} ${leg.qty > 0 ? "Buy" : "Sell"} ${Math.abs(leg.qty)}`)
    .join(" · ");
  const cashflow = request.credit < 0
    ? `debit ${Math.abs(request.credit)}`
    : request.credit > 0
      ? `credit ${request.credit}`
      : "zero cost";
  return `${request.symbol} ${request.expiration} · ${legs} · ${cashflow}`;
}
