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
from modules.premium_engine import valid_contract
from modules.width_discovery import discover_widths
from modules.research_control import checkpoint
from modules.research_timing import stage as timing_stage
from modules.strategy_compare import compare_strategy_research
from modules.structure_research import _number

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
                details = []
                if not isinstance(row, dict):
                    details.append('malformed_contract')
                else:
                    if row.get('type') != kind: details.append('option_type_mismatch')
                    if not valid_contract(row): details.append('invalid_bid_ask_or_strike')
                    if row.get('expiration', expiration) != expiration: details.append('expiration_mismatch')
                    if row.get('symbol', symbol) != symbol: details.append('symbol_mismatch')
                    if strikes[_number(row.get('strike'))] != 1: details.append('duplicate_strike')
                    if any(isinstance(row.get(k), bool) for k in ('strike', 'bid', 'ask')): details.append('boolean_quote_or_strike')
                excluded.append(dict(pool=pool, input_index=index, reason='invalid_or_ambiguous_contract', details=details))
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
                                  objective=None, candidates=None, width=None, json_ready=True):
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
    if width is not None:
        width = _number(width)
        if width is None or not 0 < width <= 100:
            raise ValueError('Width must be positive and at most 100.')
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
    # A missing market thesis is not proof that quoted structures are invalid.
    # Test both existing debit hypotheses without choosing/inventing direction,
    # premium richness or a route. The same quote/delta/payoff gates still apply.
    unclassified_research = candidates is None and not routing['routes']
    construction_families = allowed | ({'call_debit_spread', 'put_debit_spread'} if unclassified_research else set())
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
    construction_diagnostics = []
    economics_valid_count = 0
    delta_counts = dict(calls=0, puts=0)
    chain_counts = dict(calls=0, puts=0)
    if not context_error:
        clean, contract_exclusions = _clean_chain(chain, symbol, expiration)
        excluded.extend(dict(stage='chain', **x) for x in contract_exclusions)
        chain_counts = {pool: len(clean[pool]) for pool in ('calls', 'puts')}
        delta_counts = {pool: sum(1 for row in clean[pool] if row.get('delta') is not None
            and (0 < row['delta'] <= 1 if pool == 'calls' else -1 <= row['delta'] < 0))
            for pool in ('calls', 'puts')}
        if candidates is not None:
            raw = deepcopy(candidates)
        else:
            types = [kind for family, kind in (('long_call', 'Call'), ('long_put', 'Put')) if family in construction_families]
            if types:
                discovery = discover_long_options(clean, spot, as_of=research_date,
                    expected_move=expected_move, option_types=types)
                for item in discovery['candidates']:
                    trade = item['research']['trade']
                    observation = next(r for r in clean['calls' if item['option_type'] == 'call' else 'puts'] if r['strike'] == item['strike'])
                    trade['legs'][0].update(observation)
                    trade['pricing_assumption'] = 'Natural ask; not a verified fill'
                    raw.append(trade)
                for kind in types:
                    count = sum(item['option_type'] == kind.lower() for item in discovery['candidates'])
                    construction_diagnostics.append(dict(strategy_family='long_call' if kind == 'Call' else 'long_put',
                        generated_count=count, reason=None if count else 'no_quoted_long_option_within_existing_distance_filter'))
            with timing_stage('width_enumeration'):
                discovered, reports = discover_widths(clean, spot,
                    construction_families - {'long_call', 'long_put'}, width=width)
            raw.extend(discovered)
            construction_diagnostics.extend(reports)
        with timing_stage('candidate_payoff'):
            for index, candidate in enumerate(raw):
                checkpoint()
                try:
                    if not isinstance(candidate, dict) or candidate.get('expiration') != expiration:
                        raise ValueError('Candidate expiration mismatch.')
                    result = research_position(candidate, symbol=symbol, spot=spot,
                                               as_of=research_date, expected_move=expected_move, payoff_detail='landmarks')
                except (ValueError, TypeError, KeyError, OverflowError):
                    excluded.append(dict(stage='research', input_index=index, reason='invalid_or_insufficient_candidate'))
                    continue
                family = result['strategy_family']
                economics_valid_count += 1
                if family not in construction_families:
                    excluded.append(dict(stage='routing', input_index=index, reason='family_not_routed', strategy_family=family))
                    continue
                risk = _number(result['capital_at_risk'])
                if risk is None or risk < 0:
                    excluded.append(dict(stage='eligibility', input_index=index, reason='unknown_max_risk'))
                    continue
                if available_capital is not None and risk > available_capital:
                    excluded.append(dict(stage='eligibility', input_index=index, reason='exceeds_available_capital',
                        required_capital=risk, available_capital=available_capital, research=result,
                        **(dict(generation_basis='unclassified_quote_research', classification_supported=False) if unclassified_research else {})))
                    continue
                entry = dict(input_index=index, strategy_family=family, research=result)
                if unclassified_research:
                    entry.update(generation_basis='unclassified_quote_research', classification_supported=False)
                researched.append(entry)
    present = {x['strategy_family'] for x in researched}
    unavailable = [dict(route=r, reason=context_error or ('unsupported_or_requires_known_direction' if not fs else 'no_eligible_candidate'),
                        supported_families=fs) for r, fs in route_families.items() if not present.intersection(fs)]
    blocking = []
    if context_error:
        blocking.append(context_error)
    if not routing['routes'] and not unclassified_research:
        blocking.append('no_evidence_supported_routes')
        if market.get('classification_evidence', {}).get('unavailable'):
            blocking.append('completed_history_unavailable_or_invalid')
    reason_counts = dict(Counter(x['reason'] for x in excluded))
    zero_reason = None
    if not researched:
        if context_error:
            zero_reason = context_error
        elif not construction_families and routing['routes'] and candidates is None:
            zero_reason = 'no_supported_constructor_route'
        elif any(row.get('search_truncated') for row in construction_diagnostics):
            zero_reason = 'bounded_search_incomplete'
        elif not raw:
            zero_reason = 'no_constructible_structure'
        elif not economics_valid_count:
            zero_reason = 'no_valid_structure_economics'
        elif reason_counts.get('exceeds_available_capital') == economics_valid_count:
            zero_reason = 'all_structures_exceed_capital'
        else:
            zero_reason = 'all_structures_excluded'
        if zero_reason not in blocking:
            blocking.append(zero_reason)
    diagnostics = dict(width_selection=dict(mode='auto' if width is None else 'manual', requested_width=width,
        search_complete=not any(row.get('search_truncated') for row in construction_diagnostics)),
        generated_count=len(raw), accepted_count=len(researched),
        candidate_rejection_count=sum(x['stage'] != 'chain' for x in excluded),
        contract_rejection_count=sum(x['stage'] == 'chain' for x in excluded),
        capital_rejection_count=reason_counts.get('exceeds_available_capital', 0),
        rejection_counts=reason_counts, blocking_reasons=blocking,
        route_count=len(routing['routes']), clean_contract_counts=chain_counts,
        construction=construction_diagnostics,
        zero_candidate_reason=zero_reason,
        construction_families=sorted(construction_families),
        generation_basis='unclassified_quote_research' if unclassified_research else 'evidence_routed',
        classification_limitations=['no_evidence_supported_routes'] if not routing['routes'] else [],
        expiration_selection=dict(selected=expiration,
            available=market.get('archive_observation', {}).get('requested_expirations', [])),
        counts_scope='this snapshot and routed constructors; not all theoretically possible structures')
    archive = market.get('archive_diagnostics')
    diagnostics['pipeline'] = [
        dict(stage='archive_selection', status='completed' if archive else 'not_supplied',
             input_count=archive.get('total_contract_count') if archive else None,
             output_count=archive.get('selected_expiration_count') if archive else None,
             input_unit='contracts', output_unit='contracts',
             reason_counts={'different_expiration': archive['other_expiration_count'],
                            'malformed_contract': archive['malformed_contract_count']} if archive else {}),
        dict(stage='archive_quality', status='completed' if archive else 'not_supplied',
             input_count=archive.get('selected_expiration_count') if archive else None,
             output_count=archive.get('normalized_contract_count') if archive else None,
             input_unit='contracts', output_unit='contracts',
             reason_counts=archive['rejection_counts'] if archive else {}),
        dict(stage='chain_validation', status='not_attempted' if context_error else 'completed',
             input_count=sum(len(chain.get(pool) or []) for pool in ('calls','puts') if isinstance(chain.get(pool, []), list)),
             output_count=sum(chain_counts.values()), input_unit='contracts', output_unit='contracts',
             reason_counts=dict(Counter(reason for item in excluded if item['stage'] == 'chain'
                 for reason in item.get('details', [item['reason']])))),
        dict(stage='classification', status='completed', input_count=len(ALLOWED),
             output_count=state['evidence_sufficiency']['known_dimensions'], input_unit='dimensions', output_unit='known_dimensions',
             reason_counts={f'{key}_unknown': 1 for key in state['evidence_sufficiency']['unknown_dimensions']}),
        dict(stage='routing', status='completed', input_count=len(routing['routes']), output_count=len(allowed),
             input_unit='matched_routes', output_unit='supported_families',
             reason_counts={'no_evidence_supported_routes': 1} if not routing['routes'] else
                 {'no_supported_constructor_route': len(routing['routes'])} if not allowed else {},
             quote_research_families=sorted(construction_families - allowed)),
        dict(stage='construction', status='not_attempted' if context_error or (candidates is None and not construction_diagnostics) else 'completed',
             input_count=len(construction_diagnostics) if candidates is None else len(candidates), output_count=len(raw),
             input_unit='constructor_families' if candidates is None else 'supplied_structures', output_unit='structures',
             reason_counts=dict(Counter(row['reason'] for row in construction_diagnostics if row['reason']))),
        dict(stage='economics', status='not_attempted' if not raw else 'completed',
             input_count=len(raw), output_count=economics_valid_count, input_unit='structures', output_unit='structures',
             reason_counts=dict(Counter(x['reason'] for x in excluded if x['stage'] == 'research'))),
        dict(stage='candidate_routing', status='not_attempted' if not economics_valid_count else 'completed',
             input_count=economics_valid_count,
             output_count=economics_valid_count - sum(x['stage'] == 'routing' for x in excluded),
             input_unit='structures', output_unit='structures',
             reason_counts=dict(Counter(x['reason'] for x in excluded if x['stage'] == 'routing'))),
        dict(stage='capital_eligibility', status='not_attempted' if not economics_valid_count else 'completed',
             input_count=economics_valid_count - sum(x['stage'] == 'routing' for x in excluded),
             output_count=len(researched), input_unit='structures', output_unit='structures',
             reason_counts=dict(Counter(x['reason'] for x in excluded if x['stage'] == 'eligibility'))),
    ]
    with timing_stage('candidate_comparison'):
        comparison = compare_strategy_research([x['research'] for x in researched], thesis=state)
    result = dict(version='opportunity-session-v1', symbol=symbol, as_of=str(as_of),
        expiration=expiration, market=market, opportunity_state=state, strategy_routes=routing,
        candidates=researched, comparison=comparison, excluded=excluded, diagnostics=diagnostics,
        unavailable_routes=unavailable, status='complete' if researched else 'no_candidate',
        context_error=context_error, objective=objective, available_capital=available_capital,
        candidate_order='supplied order, or deterministic observed-strike enumeration; not a ranking',
        caveats=['Classifications must come from supplied AlphaOS research; raw metrics are not silently classified.',
                 'Missing evidence stays unknown. No provider requests or freshness guarantees are made.',
                 'Capital uses expiration max loss only; it is not broker margin or buying power.',
                 'One expiration and standard 100-share contracts only; fills are assumptions.',
                 'Symmetric long butterflies require supplied candidates; automatic butterfly construction uses existing iron butterflies.',
                 'No ranking or recommendation. Unsupported routes remain unavailable.'] +
                 (['No evidence-supported market route matched. Both existing debit hypotheses were tested using observed quotes/deltas only; any resulting structures are unclassified research, not market opportunities.'] if unclassified_research else []) + construction_errors)
    return _serializable(result) if json_ready else result
