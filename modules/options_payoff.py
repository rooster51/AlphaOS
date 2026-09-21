"""Deterministic expiration analysis. No pricing or probability model."""
from math import ceil, isfinite

from modules.premium_engine import analyze, payoff


def validate_trade(trade):
    """Normalize a saved scanner/manual position without trusting cached metrics."""
    try:
        result = dict(trade)
        for key in ('spot', 'credit', 'shares', 'fees'):
            result[key] = float(trade[key])
        result['stock_basis'] = float(trade.get('stock_basis', result['spot']))
        if not all(isfinite(result[k]) for k in ('spot','credit','shares','fees','stock_basis')):
            raise ValueError
        if result['spot'] <= 0 or result['fees'] < 0 or result['stock_basis'] < 0:
            raise ValueError
        if result['shares'] != int(result['shares']):
            raise ValueError
        legs = []
        for leg in trade['legs']:
            leg = dict(leg)
            leg['strike'], leg['qty'] = float(leg['strike']), float(leg['qty'])
            if (leg['type'] not in ('Put','Call') or not isfinite(leg['strike'])
                    or leg['strike'] <= 0 or not isfinite(leg['qty'])
                    or leg['qty'] == 0 or leg['qty'] != int(leg['qty'])):
                raise ValueError
            if leg.get('expiration', trade.get('expiration')) != trade.get('expiration'):
                raise ValueError
            legs.append(leg)
        if not 1 <= len(legs) <= 100:
            raise ValueError
        result['legs'] = legs
        for key in ('symbol','strategy','expiration','source'):
            result[key] = str(result.get(key) or 'Unavailable')
        return result
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ValueError('Trade is incomplete or invalid. Supply positive spot/strikes, finite premiums, whole signed quantities, nonnegative fees, and same-expiration option legs.') from None


def adaptive_grid(spot, strikes, breakevens, max_regular_points=401):
    """Bound regular sampling while retaining every exact payoff landmark.

    At ETF scale use at most $0.50 steps; tighten for narrow strike spacing.
    Widen only when the overall range would exceed the regular-point budget.
    Each adjacent landmark also gets a midpoint, preserving tiny local regions.
    """
    anchors = sorted(set([spot, *strikes, *breakevens]))
    distinct_strikes = sorted(set(strikes))
    gaps = [b-a for a,b in zip(distinct_strikes, distinct_strikes[1:])]
    step = min(.5, spot / 1000, min(gaps) / 4 if gaps else .5)
    span = anchors[-1] - anchors[0]
    padding = max(4 * step, span * .15)
    lower, upper = max(0., anchors[0] - padding), anchors[-1] + padding
    step = max(step, (upper - lower) / (max_regular_points - 1))
    count = min(max_regular_points - 1, ceil((upper - lower) / step))
    regular = [lower + i * (upper - lower) / count for i in range(count + 1)]
    midpoints = [(a+b)/2 for a,b in zip(anchors, anchors[1:])]
    return sorted(set(regular + anchors + midpoints))


def trade_analysis(trade, units=1):
    trade = validate_trade(trade)
    if not isinstance(units, (int, float)) or not isfinite(units) or units < 1 or units != int(units):
        raise ValueError('Strategy units must be a positive whole number.')
    spot, legs = trade['spot'], trade['legs']
    # Preserve manual stock basis while expressing roots in current spot coordinates.
    adjusted_credit = trade['credit'] + trade['shares'] * (spot - trade['stock_basis']) / 100
    stats = analyze(legs, adjusted_credit, spot, 0, None, trade['shares'], trade['fees'])
    profit, risk = stats['max_profit'] * units, stats['max_loss'] * units
    strikes = sorted(set(l['strike'] for l in legs))
    roots = stats['breakevens']
    def scenario(price):
        pnl = payoff(legs, trade['credit'], price, trade['shares'], trade['stock_basis'], trade['fees']) * units
        labels = []
        if price == spot:
            labels.append('Spot')
        if price in strikes:
            labels.append('Strike')
        if price in roots:
            labels.append('Breakeven')
        return {'Terminal underlying ($)': price, 'Move from spot (%)': (price/spot-1)*100,
                'Expiration P&L ($)': pnl,
                'Return on max risk (%)': pnl/risk*100 if isfinite(risk) and risk > 0 else None,
                'Landmark': ' · '.join(labels)}
    # Width is deliberately limited to a plain equal-quantity two-leg vertical.
    width = credit_width = None
    if (not trade['shares'] and len(legs) == 2 and legs[0]['type'] == legs[1]['type']
            and legs[0]['qty'] == -legs[1]['qty'] and len(strikes) == 2):
        width = strikes[1] - strikes[0]
        if trade['credit'] > 0:
            credit_width = trade['credit'] / (abs(legs[0]['qty']) * width)
    return dict(trade=trade, units=units, max_profit=profit, max_loss=risk,
                return_on_risk=profit/risk if isfinite(profit) and isfinite(risk) and risk > 0 and profit >= 0 else None,
                option_premium=trade['credit']*100*units, fees=trade['fees']*units,
                net_cash=(trade['credit']*100-trade['fees'])*units,
                width=width, credit_width=credit_width, breakevens=roots, strikes=strikes,
                grid=[scenario(p) for p in adaptive_grid(spot,strikes,roots)],
                extremes=[scenario(spot*(1+s)) for s in (-.5,-.3,-.2,-.1,-.05,0,.05,.1,.2,.3,.5)])
