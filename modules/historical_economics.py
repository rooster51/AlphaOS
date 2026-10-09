"""Descriptive expiration scenarios over existing position/payoff engines.

Internal contract, not a quote source, analog selector, or trade recommendation.
Scenario evidence must come from a trusted adapter; public API wiring is deferred.
"""
from dataclasses import asdict, dataclass
from datetime import date, datetime
import hashlib
import json
from math import isfinite

import numpy as np

from modules.position_research import research_position
from modules.premium_engine import analyze, payoff
from modules.option_scenario_ev import _summary as summarize_payoffs

VERSION = 'historical-economics-v1'
HOLDING_PERIODS = ('intraday', 'swing', 'monthly', 'leaps')
METRICS = ('expected_value_dollars', 'ev_over_max_risk', 'positive_payoff_frequency',
           'profit_factor', 'median_payoff', 'p10_payoff', 'p90_payoff',
           'average_winning_payoff', 'average_losing_payoff')


def _number(value, *, minimum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError('Finite numeric value required.')
    if minimum is not None and value < minimum:
        raise ValueError('Value below permitted minimum.')
    return float(value)


def _time(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('Timezone-aware evidence timestamps required.')
    return result


@dataclass(frozen=True)
class HistoricalScenario:
    observation_id: str
    terminal_return: float  # fraction of anchor spot, not percentage points
    completed_at: str      # outcome maturity, not analog entry date


@dataclass(frozen=True)
class ScenarioEvidence:
    symbol: str
    expiration: str
    anchor_spot: float
    observed_at: str       # source observation, never the deterministic archive slot
    as_of: str             # research request/cutoff
    max_age_seconds: float # supplied existing policy; this module never extends it
    horizon_sessions: int
    expiration_sessions: int  # authoritative remaining sessions from adapter
    source: str
    selection_method: str
    scenarios: tuple[HistoricalScenario, ...]
    history_as_of: str | None = None  # independently validated history cutoff, not quote time

    def __post_init__(self):
        object.__setattr__(self, 'scenarios', tuple(self.scenarios))
        if not self.symbol or not self.source or not self.selection_method:
            raise ValueError('Explicit evidence identity and selection method required.')
        date.fromisoformat(self.expiration)
        if _number(self.anchor_spot, minimum=0) == 0:
            raise ValueError('Positive anchor spot required.')
        _number(self.max_age_seconds, minimum=0)
        _time(self.observed_at); _time(self.as_of)
        if self.history_as_of is not None:
            _time(self.history_as_of)
        for value in (self.horizon_sessions, self.expiration_sessions):
            if type(value) is not int or value < 0:
                raise ValueError('Nonnegative whole session horizons required.')
        ids = set()
        for scenario in self.scenarios:
            if not scenario.observation_id or scenario.observation_id in ids:
                raise ValueError('Unique nonempty observation IDs required.')
            ids.add(scenario.observation_id)
            _number(scenario.terminal_return, minimum=-1)
            _time(scenario.completed_at)

    @property
    def fingerprint(self):
        # Canonical order makes equivalent evidence comparable across callers.
        data = asdict(self)
        data['scenarios'] = sorted(data['scenarios'], key=lambda x: x['observation_id'])
        return hashlib.sha256(json.dumps(data, sort_keys=True, allow_nan=False).encode()).hexdigest()


def evaluate_historical_economics(candidate, *, as_of, evidence=None,
        holding_period='swing', valuation='expiration', multiplier=100,
        slippage_dollars=0, available_capital=None, minimum_samples=30):
    """Evaluate one explicit structure against one shared underlying sample.

    Signed package premium includes all signed leg quantities, per underlying
    share. Fees and slippage are explicit TOTAL package dollar costs, charged
    once. Caller must aggregate any per-contract costs before invoking.
    The sample minimum is a descriptive coverage policy, not proof of robustness.
    """
    if holding_period not in HOLDING_PERIODS or valuation not in ('expiration', 'early_exit'):
        raise ValueError('Explicit supported holding/valuation contract required.')
    if type(multiplier) is not int or multiplier <= 0:
        raise ValueError('Positive whole contract multiplier required.')
    if type(minimum_samples) is not int or minimum_samples < 2:
        raise ValueError('At least two observations required by coverage policy.')
    slip = _number(slippage_dollars, minimum=0)
    capital = None if available_capital is None else _number(available_capital, minimum=0)
    # Reuse existing supported-family and cashflow validation; no second payoff model.
    for key in ('spot', 'credit', 'fees'):
        _number(candidate[key], minimum=0 if key in ('spot', 'fees') else None)
    if candidate.get('shares', 0) != 0:
        raise ValueError('Option-only structures required.')
    for leg in candidate['legs']:
        _number(leg['qty']); _number(leg['strike'], minimum=0)
        if leg.get('multiplier', multiplier) != multiplier:
            raise ValueError('Mixed contract multipliers unsupported.')
    if candidate.get('multiplier', multiplier) != multiplier:
        raise ValueError('Conflicting contract multiplier.')
    # Existing position researchers assume 100; normalize dollar costs for their validation.
    normalized = dict(candidate, fees=(candidate['fees'] + slip) * 100 / multiplier)
    position = research_position(normalized, symbol=candidate['symbol'],
        spot=candidate['spot'], as_of=as_of)
    trade = position['trade']
    stats = analyze(trade['legs'], trade['credit'], trade['spot'], 0, None,
                    fees=normalized['fees'])
    scale = multiplier / 100
    risk = stats['max_loss'] * scale
    profit = stats['max_profit'] * scale
    roots = stats['breakevens']
    result = dict(version=VERSION, structure_identity=position['position'],
        holding_period=holding_period, valuation=valuation,
        deterministic_expiration=dict(max_profit=profit if isfinite(profit) else None,
            max_profit_unlimited=not isfinite(profit), max_loss=risk, breakevens=roots,
            required_moves=[dict(dollars=b-trade['spot'], fraction=b/trade['spot']-1) for b in roots]),
        capital_requirement=dict(expiration_max_loss=risk, broker_buying_power=None),
        capital_eligibility=dict(status='not_assessed' if capital is None else
            ('ineligible' if risk > capital else 'within_expiration_loss_budget'),
            available_capital=capital, basis='expiration max loss, not broker buying power'),
        assumptions=dict(multiplier=multiplier, premium='signed package per-share cashflow',
            fees_dollars=candidate['fees'], slippage_dollars=slip,
            cost_basis='total package costs once, not per leg or per scenario period',
            weighting='equal observations', quantiles='linear interpolation', minimum_samples=minimum_samples),
        historical_economics={key: None for key in METRICS},
        sample_size=0, scenario_payoffs=[], evidence=None,
        robustness=dict(status='unavailable', reason='Distinct validated analog subsets not supplied.'),
        touch_breach=dict(status='unavailable', reason='Terminal returns do not establish path behavior.'),
        execution_evidence=dict(status='unavailable', reason='Executable quotes/liquidity not validated by this evaluator.'),
        early_exit=dict(status='unavailable', reason='Historical option marks or validated repricing inputs required.'),
        eligibility='ECONOMICS_INCOMPLETE', eligible_for_consideration=False,
        missing_evidence=[], research_only_reasons=['No execution validation or independent robustness validation.'])
    # Identity echoes actual units, not normalized legacy-engine dollar costs.
    result['structure_identity']['fees'] = candidate['fees']
    result['structure_identity']['multiplier'] = multiplier
    missing = result['missing_evidence']
    if valuation == 'early_exit':
        missing.append('early_exit_repricing_unavailable')
    elif holding_period == 'intraday':
        missing.append('intraday_expiration_alignment_unavailable')
    if evidence is None:
        missing.append('historical_scenarios_unavailable')
    else:
        now, observed = _time(evidence.as_of), _time(evidence.observed_at)
        age = (now-observed).total_seconds()
        result['evidence'] = dict(fingerprint=evidence.fingerprint, source=evidence.source,
            selection_method=evidence.selection_method, observed_at=evidence.observed_at,
            as_of=evidence.as_of, age_seconds=age, max_age_seconds=evidence.max_age_seconds,
            horizon_sessions=evidence.horizon_sessions, expiration_sessions=evidence.expiration_sessions,
            quote_age_seconds=None, quote_age_reason='No quote timestamps validated.')
        if (evidence.symbol != trade['symbol'] or evidence.expiration != trade['expiration']
                or evidence.anchor_spot != trade['spot']):
            missing.append('scenario_context_mismatch')
        if date.fromisoformat(as_of) != now.date():
            missing.append('research_cutoff_date_mismatch')
        if not 0 <= age <= evidence.max_age_seconds:
            missing.append('stale_or_future_evidence')
        if evidence.horizon_sessions <= 0 or evidence.horizon_sessions != evidence.expiration_sessions:
            missing.append('expiration_horizon_mismatch')
        history_cutoff = _time(evidence.history_as_of) if evidence.history_as_of else observed
        if history_cutoff > now:
            missing.append('future_history_cutoff')
        if any(_time(s.completed_at) > history_cutoff for s in evidence.scenarios):
            missing.append('unmatured_historical_outcome')
        result['sample_size'] = len(evidence.scenarios)
        if result['sample_size'] < minimum_samples:
            missing.append('insufficient_analog_history')
        if not missing:
            ordered = sorted(evidence.scenarios, key=lambda s: s.observation_id)
            values = np.array([payoff(trade['legs'], trade['credit'],
                trade['spot']*(1+s.terminal_return), fees=normalized['fees'])*scale for s in ordered])
            if not np.isfinite(values).all():
                raise ValueError('Scenario payoff overflow.')
            # Same summary math and near-zero tolerance as existing vertical economics.
            summary = summarize_payoffs(values, risk)
            mapping = dict(expected_value_dollars='expected_payoff', ev_over_max_risk='expected_payoff_on_max_risk',
                positive_payoff_frequency='positive_frequency', profit_factor='profit_factor',
                median_payoff='median_payoff', p10_payoff='p10_payoff', p90_payoff='p90_payoff',
                average_winning_payoff='average_winner', average_losing_payoff='average_loser')
            result['historical_economics'] = {key: summary[source] if summary[source] is None or
                isfinite(summary[source]) else None for key,source in mapping.items()}
            result['metric_notes'] = dict(profit_factor='defined' if summary['average_loser'] is not None else 'undefined_no_losses',
                positive_payoff_frequency='Descriptive historical frequency, not calibrated POP.',
                capital_efficiency='EV/max expiration risk only; not broker margin efficiency.')
            result['scenario_payoffs'] = [dict(observation_id=s.observation_id, payoff_dollars=float(v))
                                           for s,v in zip(ordered, values)]
            result['eligibility'] = 'EXECUTION_EVIDENCE_INCOMPLETE'
    result['historical_evidence_status'] = 'unavailable' if missing else 'descriptive_only'
    result['economics_coverage'] = 'deterministic_only' if missing else 'historical_expiration'
    if capital is not None and risk > capital:
        result['eligibility'] = 'CAPITAL_INELIGIBLE'
        result['research_only_reasons'].append('exceeds_available_capital')
    return result
