"""Bounded, quote-only geometry enumeration for the existing research families.

No provider access, capital pruning, volatility model or strategy routing here.
The caller validates the chain and computes shared payoff economics afterwards.
"""
from collections import Counter
from itertools import combinations
from math import isclose


MAX_WIDTH = 100.0
MAX_CONTRACTS_PER_SIDE = 80
MAX_ATTEMPTS_PER_FAMILY = 1024


def discover_widths(chain, spot, families, *, width=None,
                    max_width=MAX_WIDTH,
                    max_contracts_per_side=MAX_CONTRACTS_PER_SIDE,
                    max_attempts=MAX_ATTEMPTS_PER_FAMILY):
    """Manual width is exact; BWB outer wing is twice the manual inner wing.

    Bounds are constructor policy, independent of account capital. Each family
    gets its own budget; overflow is visible rather than called unaffordable.
    """
    if min(max_contracts_per_side, max_attempts) < 1 or max_width <= 0:
        raise ValueError('Positive enumeration bounds required.')
    pools = {kind: sorted(chain[key], key=lambda r: r['strike'])
             for kind, key in (('Call', 'calls'), ('Put', 'puts'))}
    pools_truncated = any(len(rows) > max_contracts_per_side for rows in pools.values())
    pools = {kind: sorted(sorted(rows, key=lambda r: (abs(r['strike'] - spot), r['strike']))[:max_contracts_per_side], key=lambda r: r['strike']) for kind, rows in pools.items()}
    results, reports = [], []
    def matches(value):
        return 0 < value <= max_width and (width is None or isclose(value, width, abs_tol=1e-8))
    def short(row):
        return row['bid'] > 0 and abs(row['strike'] / spot - 1) <= .05 + 1e-10
    def legs(*items):
        return [dict(row, qty=qty) for row, qty in items]
    def geometries(family):
        if family.endswith('debit_spread'):
            kind = 'Call' if family == 'call_debit_spread' else 'Put'
            rows = [r for r in pools[kind] if r.get('delta') is not None
                    and (0 < r['delta'] <= 1 if kind == 'Call' else -1 <= r['delta'] < 0)]
            for low, high in combinations(rows, 2):
                if matches(high['strike'] - low['strike']):
                    yield legs((low, 1 if kind == 'Call' else -1), (high, -1 if kind == 'Call' else 1))
        elif family in ('put_credit_spread', 'call_credit_spread'):
            kind = 'Put' if family == 'put_credit_spread' else 'Call'
            for low, high in combinations(pools[kind], 2):
                body, wing = (high, low) if kind == 'Put' else (low, high)
                if matches(high['strike'] - low['strike']) and short(body) and (body['strike'] < spot if kind == 'Put' else body['strike'] > spot):
                    yield legs((body, -1), (wing, 1))
        elif family in ('bullish_bwb', 'bearish_bwb'):
            kind = 'Put' if family == 'bullish_bwb' else 'Call'
            for low, body, high in combinations(pools[kind], 3):
                inner = high['strike'] - body['strike'] if kind == 'Put' else body['strike'] - low['strike']
                outer = body['strike'] - low['strike'] if kind == 'Put' else high['strike'] - body['strike']
                if matches(inner) and inner < outer <= max_width and (width is None or isclose(outer, 2 * width, abs_tol=1e-8)) and short(body) and (body['strike'] < spot if kind == 'Put' else body['strike'] > spot):
                    yield legs((low, 1), (body, -2), (high, 1))
        elif family in ('iron_condor', 'butterfly'):
            # Iron butterflies retain the existing nearest common ATM body and
            # symmetric wings. Condors may use unequal observed wing widths.
            common = set(r['strike'] for r in pools['Put']) & set(r['strike'] for r in pools['Call'])
            atm = min(common, key=lambda k: (abs(k - spot), k)) if common else None
            put_pairs = [(a, b) for a, b in combinations(pools['Put'], 2)
                         if matches(b['strike'] - a['strike']) and short(b)
                         and (b['strike'] < spot if family == 'iron_condor' else b['strike'] == atm)]
            call_pairs = [(a, b) for a, b in combinations(pools['Call'], 2)
                          if matches(b['strike'] - a['strike']) and short(a)
                          and (a['strike'] > spot if family == 'iron_condor' else a['strike'] == atm)]
            for pl, ps in put_pairs:
                for cs, cl in call_pairs:
                    if family == 'butterfly' and not isclose(ps['strike'] - pl['strike'], cl['strike'] - cs['strike'], abs_tol=1e-8):
                        continue
                    yield legs((ps, -1), (pl, 1), (cs, -1), (cl, 1))
    for family in sorted(families):
        rejected = Counter()
        attempted = generated = 0
        truncated = pools_truncated
        for item in geometries(family):
            if attempted == max_attempts:
                truncated = True
                break
            attempted += 1
            debit = family.endswith('debit_spread')
            if not debit and any(r['bid'] <= 0 for r in item if r['qty'] < 0):
                rejected['nonpositive_short_bid'] += 1
                continue
            credit = -sum(r['qty'] * ((r['bid'] + r['ask']) / 2 if debit else r['ask'] if r['qty'] > 0 else r['bid']) for r in item)
            credit = -round(-credit, 2) if debit else credit
            fees = 0 if debit else .65 * sum(abs(r['qty']) for r in item)
            if debit and credit >= 0:
                rejected['nonpositive_debit'] += 1
                continue
            if not debit and credit * 100 <= fees:
                rejected['credit_does_not_cover_fees'] += 1
                continue
            results.append(dict(strategy=family, symbol=chain['symbol'], expiration=chain['expiration'],
                spot=spot, legs=item, shares=0, credit=credit, fees=fees,
                source='Public normalized chain', pricing_assumption=
                'Observed bid/ask midpoint debit, rounded to cents; no fee; not an executable fill' if debit else
                'Natural bid/ask; existing $0.65 per-contract fee; no minimum net-credit floor'))
            generated += 1
        reason = None
        if not generated:
            kind = 'Call' if family == 'call_debit_spread' else 'Put'
            delta_count = sum(r.get('delta') is not None and
                (0 < r['delta'] <= 1 if kind == 'Call' else -1 <= r['delta'] < 0)
                for r in pools[kind])
            relevant = pools[kind] if family.endswith('debit_spread') else pools['Call'] + pools['Put']
            if not relevant:
                reason = 'missing_valid_quotes'
            elif family.endswith('debit_spread') and delta_count < 2:
                reason = 'insufficient_observed_delta_contracts'
            elif rejected:
                reason = next(iter(rejected))
            elif width is not None:
                reason = 'no_structure_at_exact_requested_width'
            else:
                reason = 'insufficient_observed_strikes_deltas_or_quotes'
        reports.append(dict(strategy_family=family, attempted_count=attempted, generated_count=generated,
            rejection_counts=dict(rejected), requested_width=width,
            search_truncated=truncated, max_attempts=max_attempts,
            max_width=max_width, max_contracts_per_side=max_contracts_per_side,
            delta_eligible_contract_count=sum(r.get('delta') is not None and (0 < r['delta'] <= 1 if r['type'] == 'Call' else -1 <= r['delta'] < 0) for r in pools['Call' if family == 'call_debit_spread' else 'Put']) if family.endswith('debit_spread') else None,
            reason=reason))
    return results, reports
