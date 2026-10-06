"""Small shared representation for existing same-expiration option research."""
from copy import deepcopy

from modules.long_option_research import research_long_option
from modules.options_payoff import validate_trade
from modules.structure_research import research_structure

OBSERVATIONS = ('contract', 'bid', 'ask', 'mid', 'delta', 'gamma', 'theta',
                'vega', 'rho', 'iv', 'volume', 'open_interest', 'bid_timestamp',
                'ask_timestamp', 'last_timestamp', 'quote_timestamp', 'observation_timestamp',
                'observed_at', 'archive_quality', 'quality_warnings', 'missing_fields')


def research_position(candidate, *, symbol, spot, as_of, expected_move=None):
    """Reuse existing researchers; native cashflow includes signed quantities."""
    if not isinstance(candidate, dict):
        raise ValueError('Candidate must be a mapping.')
    candidate = deepcopy(candidate)
    legs = candidate.get('legs')
    if not isinstance(legs, list) or not legs:
        raise ValueError('Option legs required.')
    if candidate.get('symbol', symbol) != symbol or candidate.get('spot', spot) != spot:
        raise ValueError('Candidate context mismatch.')
    if len(legs) == 1:
        trade = validate_trade(dict(candidate, symbol=symbol, spot=spot,
                                    shares=candidate.get('shares', 0), fees=candidate.get('fees', 0)))
        leg = trade['legs'][0]
        if trade['shares'] or leg['qty'] <= 0 or trade['credit'] >= 0:
            raise ValueError('Only long outright options supported.')
        result = research_long_option(symbol, trade['expiration'], leg['type'],
            leg['strike'], -trade['credit']/leg['qty'], spot, contracts=leg['qty'],
            fees=trade['fees'], as_of=as_of, expected_move=expected_move, source=trade['source'])
        result['trade']['legs'] = trade['legs']
        result.update(underlying=symbol, strategy_family=result['trade']['strategy_family'],
                      direction='bullish' if leg['type'] == 'Call' else 'bearish',
                      max_loss=result['capital_at_risk'])
        result['evidence'] = {'pricing_assumption': candidate.get('pricing_assumption', 'Supplied cashflow; not a verified fill')}
    else:
        result = research_structure(candidate, symbol=symbol, spot=spot,
                                    as_of=as_of, expected_move=expected_move)
    normalized = []
    for leg in result['trade']['legs']:
        normalized.append(dict(type=leg['type'], strike=leg['strike'],
            expiration=result['trade']['expiration'], qty=leg['qty'],
            quantity=abs(leg['qty']), action='Buy' if leg['qty'] > 0 else 'Sell',
            **{key: leg.get(key) for key in OBSERVATIONS}))
    result['position'] = dict(symbol=symbol, expiration=result['trade']['expiration'],
        strategy_family=result['strategy_family'], legs=normalized,
        credit=result['trade']['credit'], fees=result['trade']['fees'])
    result.setdefault('evidence', {})['option_legs'] = normalized
    return result
