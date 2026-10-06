"""Provider-free orchestration of existing AlphaOS research components.

market_research contains spot, optional expected_move, and an opportunity_state
mapping of already-classified dimensions. Other market evidence is retained as
context, never converted to a classification by invented thresholds.
"""
from collections import Counter
from copy import deepcopy
from datetime import date, datetime
from math import isfinite

from modules.long_option_discovery import discover_long_options
from modules.opportunity_router import ALLOWED, opportunity_state, route_strategies
from modules.position_research import research_position
from modules.premium_engine import generate, valid_contract
from modules.strategy_compare import compare_strategy_research
from modules.structure_research import _number, discover_debit_spreads

PREMIUM = {'Bull put spread': 'put_credit_spread', 'Bear call spread': 'call_credit_spread',
           'Iron condor': 'iron_condor', 'Iron butterfly': 'butterfly',
           'Put broken-wing butterfly': 'bullish_bwb', 'Call broken-wing butterfly': 'bearish_bwb'}
SUPPORTED = set(PREMIUM.values()) | {'long_call', 'long_put', 'call_debit_spread', 'put_debit_spread'}


def _families(route, direction):
    if route in SUPPORTED:
        return [route]
    if route == 'bwb':
        return ['bullish_bwb', 'bearish_bwb']
    if route == 'credit_structure':
        return ['put_credit_spread', 'call_credit_spread']
    if direction not in ('bullish', 'bearish'):
        return []
    long = 'long_call' if direction == 'bullish' else 'long_put'
    debit = 'call_debit_spread' if direction == 'bullish' else 'put_debit_spread'
    credit = 'put_credit_spread' if direction == 'bullish' else 'call_credit_spread'
    return {'long_option': [long], 'long_premium': [long, debit],
            'directional_debit_spread': [debit], 'vertical': [debit, credit],
            'directional_bwb': ['bullish_bwb' if direction == 'bullish' else 'bearish_bwb']}.get(route, [])


def _clean_chain(chain, symbol, expiration):
    clean = dict(symbol=symbol, expiration=expiration, calls=[], puts=[])
    excluded = []
    for pool, kind in (('calls', 'Call'), ('puts', 'Put')):
        rows = chain.get(pool) or []
        if not isinstance(rows, list):
            excluded.append(dict(pool=pool, reason='invalid_chain_pool'))
            continue
        strikes = Counter(_number(r.get('strike')) for r in rows if isinstance(r, dict))
        for index, row in enumerate(rows):
            if (not isinstance(row, dict) or row.get('type') != kind or not valid_contract(row)
                    or row.get('expiration', expiration) != expiration
                    or row.get('symbol', symbol) != symbol
                    or strikes[_number(row.get('strike'))] != 1
                    or any(isinstance(row.get(k), bool) for k in ('strike', 'bid', 'ask'))):
                excluded.append(dict(pool=pool, input_index=index, reason='invalid_or_ambiguous_contract'))
                continue
            normalized = deepcopy(row)
            for key in ('strike', 'bid', 'ask', 'mid', 'delta', 'gamma', 'theta', 'vega', 'rho', 'iv', 'volume', 'open_interest'):
                normalized[key] = _number(row.get(key))
            normalized['expiration'] = expiration
            clean[pool].append(normalized)
    return clean, excluded


def _serializable(value):
    # Shared payoff uses infinity for unlimited call profit. Preserve that meaning
    # in a JSON-safe payload; missing/nonfinite observations remain unavailable.
    if isinstance(value, float) and not isfinite(value):
        return 'unlimited' if value == float('inf') else None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _serializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serializable(v) for v in value]
    return value


def research_market_opportunities(symbol, market_research, chain, *, as_of,
                                  expiration=None, available_capital=None,
                                  objective=None, candidates=None, width=5):
    """Research one expiration; supplied candidates replace automatic discovery.

    No provider calls, journal writes, rankings, or recommendations. Capital is a
    max-loss eligibility ceiling, not buying power or an attractiveness measure.
    """
    symbol = str(symbol).strip().upper()
    if not symbol or not isinstance(market_research, dict) or not isinstance(chain, dict):
        raise ValueError('Symbol and normalized market/chain mappings required.')
    research_date = date.fromisoformat(str(as_of)[:10])
    if candidates is not None and not isinstance(candidates, list):
        raise ValueError('Supplied candidates must be a list.')
    if available_capital is not None:
        available_capital = _number(available_capital)
        if available_capital is None or available_capital < 0:
            raise ValueError('Capital must be a nonnegative finite dollar amount.')
    width = _number(width)
    if width is None or width <= 0:
        raise ValueError('Width must be positive.')
    market = deepcopy(market_research)
    raw_state = market.get('opportunity_state') or {}
    if not isinstance(raw_state, dict):
        raw_state = {}
    dimensions = {k: raw_state.get(k) if raw_state.get(k) in allowed else 'unknown'
                  for k, allowed in ALLOWED.items()}
    state = opportunity_state(**dimensions, evidence=raw_state.get('evidence'),
                              caveats=raw_state.get('caveats'))
    if raw_state.get('classifier_version'):
        state['classifier_version'] = raw_state['classifier_version']
    routing = route_strategies(state)
    route_families = {r: _families(r, state['direction']) for r in routing['routes']}
    allowed = {f for families in route_families.values() for f in families}
    spot = _number(market.get('spot'))
    expected_move = _number(market.get('expected_move'))
    if expected_move is not None and expected_move < 0:
        expected_move = None
    market.update(symbol=symbol, as_of=str(as_of), spot=spot, expected_move=expected_move)
    expiration = expiration or chain.get('expiration')
    context_error = None
    try:
        expiry = date.fromisoformat(str(expiration))
        if expiry < research_date:
            context_error = 'expired_chain'
    except ValueError:
        context_error = 'missing_or_invalid_expiration'
    if spot is None or spot <= 0:
        context_error = 'missing_or_invalid_spot'
    if (chain.get('symbol') != symbol or chain.get('expiration') != expiration
            or market_research.get('symbol', symbol) != symbol):
        context_error = 'market_chain_context_mismatch'
    excluded, researched, raw, construction_errors = [], [], [], []
    if not context_error:
        clean, contract_exclusions = _clean_chain(chain, symbol, expiration)
        excluded.extend(dict(stage='chain', **x) for x in contract_exclusions)
        if candidates is not None:
            raw = deepcopy(candidates)
        else:
            types = [kind for family, kind in (('long_call', 'Call'), ('long_put', 'Put')) if family in allowed]
            if types:
                discovery = discover_long_options(clean, spot, as_of=research_date,
                    expected_move=expected_move, option_types=types)
                for item in discovery['candidates']:
                    trade = item['research']['trade']
                    observation = next(r for r in clean['calls' if item['option_type'] == 'call' else 'puts'] if r['strike'] == item['strike'])
                    trade['legs'][0].update(observation)
                    trade['pricing_assumption'] = 'Natural ask; not a verified fill'
                    raw.append(trade)
            directions = [d for f, d in (('call_debit_spread', 'bullish'), ('put_debit_spread', 'bearish')) if f in allowed]
            if directions:
                try:
                    raw.extend(r['trade'] for r in discover_debit_spreads(clean, spot,
                        directions=directions, width=width, as_of=research_date,
                        expected_move=expected_move)['candidates'])
                except ValueError:
                    construction_errors.append('Debit constructor returned insufficient economics.')
            if allowed & set(PREMIUM.values()):
                # IV is deliberately absent: constructor quotes/legs do not
                # require a volatility model, and no probability is imported.
                # Same-day expiry uses zero time; payoff construction remains
                # valid while modeled POP intentionally stays unavailable.
                for trade in generate(clean, spot, max(0, (expiry-research_date).days)/365,
                                      None, width=width, as_of=research_date,
                                      min_net_credit=0):
                    if PREMIUM.get(trade['strategy']) in allowed:
                        raw.append(dict(trade, symbol=symbol, source='Public normalized chain',
                                        pricing_assumption='Natural bid/ask; existing $0.65 per-contract fee; no AlphaOS 2.0 minimum net-credit floor'))
        for index, candidate in enumerate(raw):
            try:
                if not isinstance(candidate, dict) or candidate.get('expiration') != expiration:
                    raise ValueError('Candidate expiration mismatch.')
                result = research_position(candidate, symbol=symbol, spot=spot,
                                           as_of=research_date, expected_move=expected_move)
            except (ValueError, TypeError, KeyError, OverflowError):
                excluded.append(dict(stage='research', input_index=index, reason='invalid_or_insufficient_candidate'))
                continue
            family = result['strategy_family']
            if family not in allowed:
                excluded.append(dict(stage='routing', input_index=index, reason='family_not_routed', strategy_family=family))
                continue
            risk = _number(result['capital_at_risk'])
            if risk is None or risk < 0:
                excluded.append(dict(stage='eligibility', input_index=index, reason='unknown_max_risk'))
                continue
            if available_capital is not None and risk > available_capital:
                excluded.append(dict(stage='eligibility', input_index=index, reason='exceeds_available_capital',
                    required_capital=risk, available_capital=available_capital, research=result))
                continue
            researched.append(dict(input_index=index, strategy_family=family, research=result))
    present = {x['strategy_family'] for x in researched}
    unavailable = [dict(route=r, reason=context_error or ('unsupported_or_requires_known_direction' if not fs else 'no_eligible_candidate'),
                        supported_families=fs) for r, fs in route_families.items() if not present.intersection(fs)]
    comparison = compare_strategy_research([x['research'] for x in researched], thesis=state)
    return _serializable(dict(version='opportunity-session-v1', symbol=symbol, as_of=str(as_of),
        expiration=expiration, market=market, opportunity_state=state, strategy_routes=routing,
        candidates=researched, comparison=comparison, excluded=excluded,
        unavailable_routes=unavailable, status='complete' if researched else 'no_candidate',
        context_error=context_error, objective=objective, available_capital=available_capital,
        candidate_order='supplied order, or existing long/debit/premium generator order; not a ranking',
        caveats=['Classifications must come from supplied AlphaOS research; raw metrics are not silently classified.',
                 'Missing evidence stays unknown. No provider requests or freshness guarantees are made.',
                 'Capital uses expiration max loss only; it is not broker margin or buying power.',
                 'One expiration and standard 100-share contracts only; fills are assumptions.',
                 'Symmetric long butterflies require supplied candidates; automatic butterfly construction uses existing iron butterflies.',
                 'No ranking or recommendation. Unsupported routes remain unavailable.'] + construction_errors))
