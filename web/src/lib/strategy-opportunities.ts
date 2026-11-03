import { candidateViews, record } from "./market-candidates.ts";

type CandidateView = ReturnType<typeof candidateViews>[number];

export type OpportunityStatus = "eligible" | "unaffordable" | "unavailable";

export interface OpportunityAssessment {
  candidate: CandidateView;
  status: OpportunityStatus;
  reasons: string[];
}

export interface StrategyEvidenceContext {
  symbol: "SPY" | "QQQ";
  mode: "current" | "historical";
  requestedCapital: number;
  session: Record<string, unknown>;
  archive: Record<string, unknown>;
  researchAsOf: string;
}

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function timestamp(value: unknown): number | null {
  if (typeof value !== "string" || !value.trim()) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function archiveVerificationReason(
  archive: Record<string, unknown>,
  symbol: "SPY" | "QQQ",
  researchAsOf: string,
  mode: "current" | "historical",
): string | null {
  if (mode !== "current") return "Historical archive research is not a current opportunity.";

  const observation = record(archive.observation);
  const storage = record(archive.storage);
  const freshness = record(archive.freshness);
  const observedAt = timestamp(observation.observed_at);
  const storedAt = timestamp(storage.observed_at);
  const requestedAt = timestamp(freshness.as_of);
  const responseAt = timestamp(researchAsOf);
  const age = finiteNumber(freshness.age_seconds);
  const maximumAge = finiteNumber(freshness.max_age_seconds);

  if (observation.options_status !== "complete" || storage.quality_status !== "complete") {
    return "Complete option-archive quality is unavailable.";
  }
  if (storage.symbol !== symbol || observation.provider !== storage.provider) {
    return "Archive identity could not be verified.";
  }
  if (typeof storage.archive_sha256 !== "string" || !/^[a-f\d]{64}$/i.test(storage.archive_sha256)) {
    return "Verified archive checksum is unavailable.";
  }
  if (observedAt === null || storedAt !== observedAt || responseAt !== observedAt || requestedAt === null) {
    return "Archive observation timestamps do not agree.";
  }
  if (
    age === null ||
    maximumAge === null ||
    age < 0 ||
    maximumAge <= 0 ||
    age > maximumAge ||
    requestedAt < observedAt ||
    Math.abs(requestedAt - observedAt - age * 1000) > 1000
  ) {
    return "Archive freshness is missing, stale, or inconsistent.";
  }

  return null;
}

function verifiedLegs(
  legs: unknown,
  expiration: unknown,
  archive: Record<string, unknown>,
): string[] {
  if (!Array.isArray(legs) || legs.length === 0) return ["Exact option legs are unavailable."];

  const observation = record(archive.observation);
  const freshness = record(archive.freshness);
  const collectedAt =
    timestamp(observation.collection_finished_at) ?? timestamp(observation.observed_at);
  const requestedAt = timestamp(freshness.as_of);
  const maximumAge = finiteNumber(freshness.max_age_seconds);
  if (collectedAt === null || requestedAt === null || maximumAge === null) {
    return ["Verified option-quote timing is unavailable."];
  }

  const reasons = new Set<string>();
  for (const rawLeg of legs) {
    const leg = record(rawLeg);
    const bid = finiteNumber(leg.bid);
    const ask = finiteNumber(leg.ask);
    const strike = finiteNumber(leg.strike);
    const quantity = finiteNumber(leg.quantity);
    const signedQuantity = finiteNumber(leg.qty);
    const bidAt = timestamp(leg.bid_timestamp);
    const askAt = timestamp(leg.ask_timestamp);
    const action = typeof leg.action === "string" ? leg.action.toLowerCase() : "";
    const type = typeof leg.type === "string" ? leg.type.toLowerCase() : "";

    if (typeof leg.contract !== "string" || !leg.contract.trim()) {
      reasons.add("Exact contract identifiers are missing.");
    }
    if (
      strike === null ||
      strike <= 0 ||
      !["call", "put"].includes(type) ||
      leg.expiration !== expiration
    ) {
      reasons.add("A leg has a missing or mismatched type, strike, or expiration.");
    }
    if (
      quantity === null ||
      quantity <= 0 ||
      !Number.isInteger(quantity) ||
      signedQuantity === null ||
      Math.abs(signedQuantity) !== quantity ||
      (action !== "buy" && action !== "sell") ||
      (action === "buy" && signedQuantity <= 0) ||
      (action === "sell" && signedQuantity >= 0)
    ) {
      reasons.add("A leg has an incomplete or inconsistent action and quantity.");
    }
    if (bid === null || ask === null || bid < 0 || ask <= 0 || ask < bid) {
      reasons.add("A leg is missing a valid, uncrossed bid and ask.");
    }
    const warnings = leg.quality_warnings;
    if (
      leg.archive_quality !== "valid_contracts" ||
      (warnings !== undefined &&
        warnings !== null &&
        (!Array.isArray(warnings) || warnings.length > 0))
    ) {
      reasons.add("A leg does not have verified archive quote quality.");
    }
    if (
      bidAt === null ||
      askAt === null ||
      bidAt > collectedAt ||
      askAt > collectedAt ||
      requestedAt - bidAt > maximumAge * 1000 ||
      requestedAt - askAt > maximumAge * 1000 ||
      bidAt > requestedAt ||
      askAt > requestedAt
    ) {
      reasons.add("A leg is missing fresh, timestamped bid/ask evidence.");
    }
  }

  return [...reasons];
}

function capitalRequirementReason(
  candidate: CandidateView,
  context: StrategyEvidenceContext,
): string | null {
  const entry = candidate as Record<string, unknown>;
  const research = record(entry.research);
  const economics = record(research.historical_economics);
  const eligibility = record(economics.capital_eligibility);
  const risk = finiteNumber(research.capital_at_risk);
  const maxLoss = finiteNumber(research.max_loss);
  const sessionCapital = finiteNumber(context.session.available_capital);
  const eligibleCapital = finiteNumber(eligibility.available_capital);

  if (
    sessionCapital !== context.requestedCapital ||
    eligibleCapital !== context.requestedCapital ||
    risk === null ||
    maxLoss === null ||
    risk < 0 ||
    maxLoss < 0 ||
    risk !== maxLoss ||
    risk > context.requestedCapital ||
    eligibility.status !== "within_expiration_loss_budget"
  ) {
    return "Backend max-loss eligibility does not match the requested budget.";
  }

  if (entry.classification_supported === false) {
    return "The strategy is not supported by the market classification.";
  }

  return null;
}

function positiveEconomicsReason(candidate: CandidateView): string | null {
  const research = record((candidate as Record<string, unknown>).research);
  const profit = research.max_profit;
  if (!(profit === "unlimited" || (finiteNumber(profit) !== null && finiteNumber(profit)! >= 0))) {
    return "Maximum-profit economics are unavailable.";
  }

  const debit = finiteNumber(research.entry_debit);
  const credit = finiteNumber(research.entry_credit);
  if ((debit === null && credit === null) || (debit !== null && debit < 0) || (credit !== null && credit < 0)) {
    return "Backend entry debit/credit is unavailable.";
  }

  return null;
}

export function assessStrategyCandidates(
  session: Record<string, unknown>,
  archive: Record<string, unknown>,
  symbol: "SPY" | "QQQ",
  requestedCapital: number,
  mode: "current" | "historical",
  researchAsOf: string,
): OpportunityAssessment[] {
  const archiveReason = archiveVerificationReason(archive, symbol, researchAsOf, mode);
  const views = candidateViews(session);

  return views.map((candidate) => {
    const entry = candidate as Record<string, unknown>;
    const research = record(entry.research);
    const reasons: string[] = [];

    if (archiveReason) reasons.push(archiveReason);

    if (entry.source_bucket === "excluded") {
      if (archiveReason) {
        return { candidate, status: "unavailable", reasons };
      }

      const requiredCapital = finiteNumber(entry.required_capital);
      const availableCapital = finiteNumber(entry.available_capital);
      const maxLoss = finiteNumber(research.max_loss);
      const legs = verifiedLegs(candidate.research.legs, research.expiration, archive);
      if (
        entry.reason === "exceeds_available_capital" &&
        requiredCapital !== null &&
        requiredCapital > requestedCapital &&
        availableCapital === requestedCapital &&
        maxLoss === requiredCapital &&
        legs.length === 0
      ) {
        return {
          candidate,
          status: "unaffordable",
          reasons: ["Backend-reported maximum loss exceeds the requested budget."],
        };
      }

      reasons.push("The backend did not return this as a capital-eligible candidate.");
      reasons.push(...legs);
      return { candidate, status: "unavailable", reasons };
    }

    const budgetReason = capitalRequirementReason(candidate, {
      symbol,
      mode,
      requestedCapital,
      session,
      archive,
      researchAsOf,
    });
    if (budgetReason) reasons.push(budgetReason);
    reasons.push(...verifiedLegs(candidate.research.legs, research.expiration, archive));
    const economicsReason = positiveEconomicsReason(candidate);
    if (economicsReason) reasons.push(economicsReason);

    return {
      candidate,
      status: reasons.length === 0 ? "eligible" : "unavailable",
      reasons,
    };
  });
}
