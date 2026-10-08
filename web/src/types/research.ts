export type DirectionState = "bullish" | "bearish" | "neutral" | "unknown";
export type PremiumState = "rich" | "fair" | "cheap" | "unknown";
export type MovementState = "range_bound" | "directional" | "breakout" | "large_move_expected" | "pin_candidate" | "unknown";
export type TimeState = "standard" | "late_0dte" | "after_hours" | "unknown";
export type VolatilityState = "elevated" | "normal" | "depressed" | "unknown";

export interface OpportunityState {
  direction: DirectionState;
  premium_state: PremiumState;
  movement_state: MovementState;
  time_state: TimeState;
  volatility_state: VolatilityState;
  evidence: Record<string, any>;
  caveats: string[];
  classified_at: string;
}

export interface PriceStructureLevel {
  label: string;
  price: number;
  distance: number;
  distance_pct: number;
  kind: "support" | "resistance" | "mid" | "atr";
}

export interface MarketSnapshot {
  symbol: string;
  current_spot: number;
  as_of: string;
  source: "verified_archive" | "live_public" | "mock_fixture";
  opportunity_state: OpportunityState;
  levels: PriceStructureLevel[];
  atr_14: number;
  expected_move?: number;
  timing?: {
    exchange: string;
    session_open: string;
    session_close: string;
    is_regular_hours: boolean;
    minutes_to_close: number;
  };
}

export type StrategyFamily = 
  | "long_call"
  | "long_put"
  | "pcs"       // Put Credit Spread
  | "ccs"       // Call Credit Spread
  | "cds"       // Call Debit Spread
  | "pds"       // Put Debit Spread
  | "iron_condor"
  | "butterfly"
  | "bwb";      // Broken Wing Butterfly

export interface OptionLeg {
  action: "buy" | "sell";
  option_type: "call" | "put";
  strike: number;
  expiration: string;
  bid: number;
  ask: number;
  mid: number;
  delta?: number;
  iv?: number;
}

export interface ResearchCandidate {
  id: string;
  family: StrategyFamily;
  family_label: string;
  symbol: string;
  expiration: string;
  dte: number;
  legs: OptionLeg[];
  net_cashflow: number; // positive = debit, negative = credit
  max_loss: number;
  max_profit: number | "unlimited";
  breakevens: number[];
  distance_to_breakeven_pct: number[];
  risk_reward_ratio?: number;
  modeled_pop?: number | null; // null for 0DTE or when unavailable
  capital_required: number;
  disclosures: string[];
}

export interface JournalPosition {
  id: string;
  symbol: string;
  family: StrategyFamily;
  status: "open" | "closed" | "expired";
  entry_time: string;
  exit_time?: string;
  entry_spot: number;
  current_spot: number;
  net_entry_cost: number;
  unrealized_pnl: number;
  realized_pnl?: number;
  target_profit: number;
  max_loss_budget: number;
  frozen_opportunity_state: OpportunityState;
  legs: OptionLeg[];
}

export interface RiskGuardrails {
  max_trades_per_day: number;
  max_daily_loss_pct: number;
  cooldown_after_losses: number;
  cooldown_minutes: number;
  min_backtest_win_rate: number;
  default_account_size: number;
  default_risk_pct: number;
}
