"""One completed-history/analog snapshot per scan; descriptive candidate context."""
from copy import deepcopy
import pandas as pd
from modules.market_state_research import load_market_state
from modules.price_structure import price_structure, nearest_levels
from modules.historical_analogs import analog_research
from modules.threshold_survival import threshold_research
from modules.phase6_research import vertical_context
from modules.daily_archive import digest
from modules.options_payoff import validate_trade
from modules.research_session import save_research_session

VERSION='selector-quant-workflow-v1'


def build_scan_research(symbol, spot, horizon, quote_time, retrieved_at, loader=None):
    """Reuse provider adapter/cache. Exactly one dataset load for the scan."""
    dataset=(loader or load_market_state)(symbol,'FIVE_YEARS')
    return context_from_dataset(dataset,spot,horizon,quote_time,retrieved_at)


def context_from_dataset(dataset,spot,horizon,quote_time,retrieved_at):
    bars=dataset['features'][['date','symbol','open','high','low','close']].copy()
    cutoff=pd.Timestamp(dataset['metadata']['audit']['completed_before'])
    if bars.empty or bars.date.max()>=cutoff:
        raise ValueError('Research snapshot includes an uncompleted session.')
    structure=price_structure(bars,completed_before=cutoff,anchor_spot=spot)
    analog=analog_research(dataset['features'],dataset['outcomes'],horizon=horizon,method='tolerance')
    snapshot=dict(version=VERSION,dataset=dataset,structure=structure,analog=analog,horizon=horizon,
        research_date=str(pd.Timestamp(analog['target']['date']).date()),research_close=float(analog['target']['close']),
        current_spot=float(spot),quote_timestamp=quote_time,scan_retrieved_at=retrieved_at)
    snapshot['snapshot_id']=digest(snapshot)
    return snapshot


def candidate_fingerprint(trade):
    try: normalized=validate_trade(trade)
    except ValueError: normalized=trade
    return digest({k:normalized.get(k) for k in ('symbol','spot','credit','shares','fees','expiration','legs')})


def structural_position(strike,zone,side):
    if zone is None: return None
    epsilon=max(abs(strike),abs(zone['level']))*1e-12
    name='SUPPORT' if side=='support' else 'RESISTANCE'
    if strike<zone['zone_low']-epsilon: return 'BELOW '+name
    if strike>zone['zone_high']+epsilon: return 'ABOVE '+name
    return 'INSIDE '+name


def annotate_candidates(rows,snapshot,symbol):
    """Preserve order and original metrics. Reuse one sample and repeated strikes."""
    enriched=[]; threshold_cache={}
    structure=snapshot['structure']; analog=snapshot['analog']; h=snapshot['horizon']
    bridged={**analog,'target':dict(analog['target'])}
    bridged['target']['close']=snapshot['current_spot']
    for original in rows:
        row=dict(original)
        trade={**row,'symbol':symbol,'source':'Public candidate research'}
        try: vertical=vertical_context(trade,structure)
        except ValueError:
            row['research_context']=None; enriched.append(row); continue
        side='support' if vertical['mode']=='put' else 'resistance'
        near=nearest_levels(structure,1)
        near=near[near.side==side] if not near.empty else near
        zone=None if near.empty else near.iloc[0].to_dict()
        key=(vertical['mode'],vertical['short_strike'])
        if key not in threshold_cache:
            threshold_cache[key]=threshold_research(bridged,key[0],h,threshold_price=key[1],allow_opposite=True)['summary']
        context=dict(version=VERSION,snapshot_id=snapshot['snapshot_id'],candidate_fingerprint=candidate_fingerprint(trade),
            research_date=snapshot['research_date'],research_close=snapshot['research_close'],current_spot=snapshot['current_spot'],
            quote_timestamp=snapshot['quote_timestamp'],scan_retrieved_at=snapshot['scan_retrieved_at'],horizon=h,
            analog_config=deepcopy(analog['config']),nearest_zone=zone,short_strike=key[1],
            structural_position=structural_position(key[1],zone,side),strike_distance_pct=key[1]/trade['spot']-1,
            strike_distance_atr=(key[1]-trade['spot'])/structure['atr'],
            distance_from_level=None if zone is None else key[1]-zone['level'],
            threshold_statistics=deepcopy(threshold_cache[key]),provenance=deepcopy(snapshot['dataset']['metadata']))
        row['research_context']=context; enriched.append(row)
    return enriched


def research_columns(row):
    c=row.get('research_context') or {}; s=c.get('threshold_statistics') or {}; zone=c.get('nearest_zone')
    def pct(v): return None if v is None else f'{v:.1%}'
    return {'Short strike':c.get('short_strike'),'Nearest S/R':zone['level'] if zone else None,
        'Structural position':c.get('structural_position'),'Strike distance %':pct(c.get('strike_distance_pct')),
        'Strike distance ATR':c.get('strike_distance_atr'),'Distance from S/R ($)':c.get('distance_from_level'),
        'Historical terminal survival':pct(s.get('survival_frequency')),'Historical touch/breach':pct(s.get('touch_frequency')),
        'Historical finish beyond':pct(s.get('terminal_breach_frequency')),'Research N':s.get('terminal_valid_n'),
        'Touch N':s.get('touch_valid_n')}


def select_candidate(state,result,index):
    candidate=deepcopy(result['rows'][index])
    candidate.update(symbol=result['symbol'],source=result['source'],quote_timestamp=result['quote_time'],
                     scan_retrieved_at=result.get('retrieved_at',result['fetched']))
    state['quant_selected_option']=candidate
    snapshot=result.get('research_snapshot')
    state.pop('quant_selected_research',None)
    if snapshot is not None:
        state['quant_selected_research']=deepcopy(snapshot)
        dataset=snapshot['dataset']
        save_research_session(state,history=dataset['features'][['date','symbol','open','high','low','close']],
            symbol=result['symbol'],period='FIVE_YEARS',metadata=dataset['metadata'])
    return candidate


def valid_saved_snapshot(trade,snapshot):
    """Fail closed for changed trade/context; never silently transplant stale context."""
    c=trade.get('research_context') or {}
    if not c or not snapshot: return False
    try:
        return (c['version']==VERSION and c['snapshot_id']==snapshot['snapshot_id']
            and snapshot['snapshot_id']==digest({k:v for k,v in snapshot.items() if k!='snapshot_id'})
            and c['candidate_fingerprint']==candidate_fingerprint(trade)
            and c['current_spot']==trade['spot']==snapshot['current_spot']
            and c['horizon']==snapshot['horizon'] and c['analog_config']==snapshot['analog']['config']
            and c['research_date']==snapshot['research_date']
            and c['research_close']==snapshot['research_close']
            and trade['symbol']==snapshot['dataset']['metadata']['symbol'])
    except (KeyError,TypeError,ValueError): return False
