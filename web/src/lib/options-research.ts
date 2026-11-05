export type ContractSelection = { contract: string; qty: number };
export type ScenarioSelection = { strategy: string; legs: ContractSelection[] };
export const strategyNames = {
  long_call: "Long call", long_put: "Long put", call_debit_spread: "Bull call debit spread",
  put_debit_spread: "Bear put debit spread", put_credit_spread: "Bull put credit spread",
  call_credit_spread: "Bear call credit spread", iron_condor: "Iron condor", iron_butterfly: "Iron butterfly",
  long_call_butterfly: "Long call butterfly", long_put_butterfly: "Long put butterfly",
  long_straddle: "Long straddle", long_strangle: "Long strangle", custom: "Custom signed legs",
} as const;
export const defaultLimits = {
  max_debit: null as number | null, max_loss: null as number | null, min_credit: 0,
  max_contracts: 20, max_bid_ask_spread: null as number | null, dte_min: 0, dte_max: 3650,
};
export type ResearchRequest = {
  scenarios: ScenarioSelection[]; limits: typeof defaultLimits; entry_fee_per_contract: number;
};
export type ResearchResult = {
  strategy: string; status: string; eligible_for_analysis: boolean; reason: string | null;
  limit_breaches?: string[]; expiration?: string; dte?: number; direction?: string;
  net_cash?: number; entry_premium?: number; entry_fees?: number; total_contracts?: number;
  max_profit?: number | null; max_loss?: number | null; profit_unbounded?: boolean; loss_unbounded?: boolean;
  capital_at_risk?: number | null; return_on_max_risk?: number | null; breakevens?: number[];
  evaluated_at?: string; retrieved_at?: string; oldest_quote_age_seconds?: number;
  liquidity_warnings?: string[]; assumptions?: string[]; capital_treatment?: string;
  greek_exposure?: Record<string, number | null>;
  legs?: { contract: string; qty: number; price: number; bid_timestamp: string; ask_timestamp: string }[];
  payoff?: { terminal_price: number; pnl: number }[];
};

export function validResearchRequest(value: unknown): value is ResearchRequest {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const request = value as ResearchRequest;
  const limits = request.limits;
  return Object.keys(request).sort().join() === "entry_fee_per_contract,limits,scenarios"
    && Number.isFinite(request.entry_fee_per_contract) && request.entry_fee_per_contract >= 0 && request.entry_fee_per_contract <= 100
    && Array.isArray(request.scenarios) && request.scenarios.length > 0 && request.scenarios.length <= 8
    && request.scenarios.every(item => item && Object.keys(item).sort().join() === "legs,strategy"
      && Object.hasOwn(strategyNames, item.strategy) && Array.isArray(item.legs) && item.legs.length > 0 && item.legs.length <= 8
      && item.legs.every(leg => leg && Object.keys(leg).sort().join() === "contract,qty"
        && typeof leg.contract === "string" && leg.contract.length <= 32 && /^[A-Z]+ *\d{6}[CP]\d{8}$/.test(leg.contract)
        && Number.isInteger(leg.qty) && leg.qty !== 0 && Math.abs(leg.qty) <= 20))
    && !!limits && typeof limits === "object" && !Array.isArray(limits)
    && Object.keys(limits).sort().join() === Object.keys(defaultLimits).sort().join()
    && Object.entries(limits).every(([key, number]) => number === null
      ? ["max_debit", "max_loss", "max_bid_ask_spread"].includes(key)
      : typeof number === "number" && Number.isFinite(number) && number >= 0)
    && Number.isInteger(limits.max_contracts) && limits.max_contracts >= 1 && limits.max_contracts <= 160
    && Number.isInteger(limits.dte_min) && Number.isInteger(limits.dte_max)
    && limits.dte_min <= limits.dte_max && limits.dte_max <= 3650;
}

export function stableJSON(value: unknown): string {
  return JSON.stringify(value, (_key, item) => item && typeof item === "object" && !Array.isArray(item)
    ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b))) : item);
}

export function validResearchResults(value: unknown, request: ResearchRequest): boolean {
  if (!Array.isArray(value) || value.length !== request.scenarios.length) return false;
  const finite = (item: unknown) => typeof item === "number" && Number.isFinite(item);
  return value.every((item: ResearchResult, index) => {
    if (!item || item.strategy !== request.scenarios[index].strategy
      || !["available", "unavailable"].includes(item.status)
      || item.eligible_for_analysis !== (item.status === "available")) return false;
    if (item.status === "unavailable" && !item.legs) return typeof item.reason === "string";
    return [item.net_cash, item.entry_premium, item.entry_fees, item.total_contracts,
      item.dte, item.oldest_quote_age_seconds].every(finite)
      && (item.profit_unbounded === true ? item.max_profit === null : finite(item.max_profit))
      && (item.loss_unbounded === true ? item.max_loss === null : finite(item.max_loss))
      && (item.return_on_max_risk === null || finite(item.return_on_max_risk))
      && Array.isArray(item.breakevens) && item.breakevens.every(finite)
      && Array.isArray(item.payoff) && item.payoff.length <= 5000
      && item.payoff.every(point => point && finite(point.terminal_price) && finite(point.pnl))
      && Array.isArray(item.legs) && item.legs.length === request.scenarios[index].legs.length
      && item.legs.every((leg, position) => leg && leg.contract === request.scenarios[index].legs[position].contract
        && leg.qty === request.scenarios[index].legs[position].qty && finite(leg.price)
        && typeof leg.bid_timestamp === "string" && typeof leg.ask_timestamp === "string")
      && Array.isArray(item.liquidity_warnings) && item.liquidity_warnings.every(text => typeof text === "string")
      && Array.isArray(item.assumptions) && item.assumptions.every(text => typeof text === "string")
      && Array.isArray(item.limit_breaches) && item.limit_breaches.every(text => typeof text === "string")
      && typeof item.direction === "string" && typeof item.capital_treatment === "string"
      && typeof item.evaluated_at === "string" && Number.isFinite(Date.parse(item.evaluated_at))
      && typeof item.retrieved_at === "string" && Number.isFinite(Date.parse(item.retrieved_at))
      && !!item.greek_exposure && typeof item.greek_exposure === "object" && !Array.isArray(item.greek_exposure)
      && Object.values(item.greek_exposure).every(value => value === null || finite(value));
  });
}
