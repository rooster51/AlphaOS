"""Phase 9 presentation over authoritative Phase 6 evidence; no second quant engine."""
from copy import deepcopy
from modules.threshold_survival import threshold_research
from modules.level_behavior import level_behavior
from modules.daily_archive import json_value

VERSION = 'alphaos-unified-trade-v1'
SCENARIO_CAVEAT = ('Historical Scenario EV is descriptive evidence across selected historical analogs. '
                   'It is not a forecast of future profit or guaranteed expectancy.')


def build_unified_trade(research, live_state=None, *, candidate_id=None, include_advanced=False):
    r = research
    trade, context = r['trade'], r['evidence']['context']
    economics = r['evidence']['economics']
    horizon = r['provenance']['horizon']
    spot = trade['spot']
    state = deepcopy(live_state or dict(current_spot=None,quote_as_of=None,retrieved_at=None,
        market_state='unknown',data_status='unknown',usable_for_live_research=False,
        usable_for_execution_analysis=False,source='Explicit scenario input; not verified live'))
    levels = [('short_strike',context['short_strike']),('breakeven',context['breakeven']),('long_strike',context['long_strike'])]
    distances = {name:dict(price=price,dollars=price-spot,fraction=price/spot-1) for name,price in levels}
    snapshot = dict(symbol=trade['symbol'],strategy=context['strategy'],expiration=trade['expiration'],
        short_strike=context['short_strike'],long_strike=context['long_strike'],
        width=abs(context['short_strike']-context['long_strike']),credit=context['credit'],
        pricing_method=trade.get('source'),legs=trade['legs'],
        max_profit=context['max_profit'],max_loss=context['max_loss'],return_on_risk=context['return_on_risk'],
        breakeven=context['breakeven'],scenario_spot=spot,distances_from_scenario_spot=distances,
        units='One strategy structure; option credit dollars/share, payoff dollars; distances signed (level minus spot).',
        live_trade_state=state,research_state=dict(research_session=r['provenance']['research_date'],
            research_close=context['research_close'],observed_session_horizon=horizon),candidate_id=candidate_id)
    structure_levels = r['levels'].to_dict('records')
    ladder = [dict(label=name,price=price) for name,price in levels]+[dict(label='scenario_spot',price=spot)]
    ladder += [dict(label=level['side'],price=level['level']) for level in structure_levels]
    # Price ordering is a visual layout, never a candidate ranking.
    ladder.sort(key=lambda item:item['price'],reverse=True)
    structure = dict(levels=structure_levels,price_ladder=ladder,
        short_minus_nearest_structural_level=context['strike_minus_nearest_level'],
        nearest_relevant_level=context['nearest_structural_level'],
        relevant_side='support' if context['mode']=='put' else 'resistance',
        interpretation='Signed distance describes location relative to identified historical structure, not protection or a guaranteed barrier.')
    bridged = {**r['primary'],'target':dict(r['primary']['target'])}
    bridged['target']['close'] = spot
    behaviors = []
    raw_thresholds = {}
    for name,price in levels:
        threshold = r['evidence']['threshold'] if name=='short_strike' else threshold_research(
            bridged,context['mode'],horizon,threshold_price=price,allow_opposite=True)
        excursion = level_behavior(r['primary'],horizon=horizon,anchor_spot=spot,level=price,
            side=structure['relevant_side'])
        behaviors.append(dict(level=name,price=price,distance=distances[name],horizon=horizon,
            statistics=threshold['summary'],non_overlapping_statistics=threshold['non_overlapping_summary'],
            excursions=excursion['summary'],config=threshold['config']))
        if include_advanced:raw_thresholds[name]=threshold
    observations = economics['observations']
    pnl = observations['gross_expiration_pnl']
    full = int(((pnl-context['max_profit']).abs()<=1e-8).sum())
    loss = int(((pnl+context['max_loss']).abs()<=1e-8).sum())
    n = len(pnl)
    payoff = dict(summary=economics['net_summary'],profit_factor_unbounded=economics['net_summary']['profit_factor']==float('inf'),before_additional_friction=economics['gross_summary'],
        non_overlapping_summary=economics['non_overlapping_net_summary'],friction=economics['friction'],
        outcome_counts=dict(n=n,full_profit=full,max_loss=loss,partial=n-full-loss,
            basis='Existing gross payoff after saved entry fees, before additional modeled friction; partial means between payoff endpoints, not necessarily profitable.'),
        config=economics['config'],caveat=SCENARIO_CAVEAT)
    advanced = dict(included=include_advanced,metadata=r['provenance'],engine_version=r['version'],
        analog_config=r['primary']['config'],payoff_config=economics['config'],
        detail_instruction='Request include_advanced=true for full analog, threshold, payoff, distribution and robustness evidence.')
    if include_advanced:
        advanced.update(analog_table=r['primary']['analogs'],forward_distributions=r['distributions'],
            raw_threshold_details=raw_thresholds,payoff_observations=observations,
            robustness=r['robustness'],structure_details=r['level_details'])
    return json_value(dict(schema_version=VERSION,trade_snapshot=snapshot,market_structure=structure,
        historical_analog_behavior=dict(levels=behaviors,interpretation='Historical frequencies, not future probabilities. Terminal and touch denominators can differ; recovery is terminal survival after a touch, not an intraday path.',horizon=horizon),
        historical_scenario_payoff=payoff,advanced_research=advanced,
        caveats=[SCENARIO_CAVEAT,'Observed-session horizon is not calendar DTE or expiration-matched profitability.',
            'No ranking, recommendation or automatic winner selection.','Underlying quote sanity does not verify option fills or real-time entitlement.']))
