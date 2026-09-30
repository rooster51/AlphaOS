"""Exercise the implemented index adapter/engines with existing CI secrets, read-only."""
import os
import json
from datetime import datetime,timezone
from alphaos_api.service import ResearchService
from alphaos_api.phase9 import UnifiedResearch
from alphaos_api.contracts import APIError
from modules.daily_archive import json_value


def main():
    os.environ['PUBLIC_API_SECRET']=os.environ.get('PUBLIC_API_SECRET','').strip()
    service=ResearchService();report={'observed_at':datetime.now(timezone.utc).isoformat(),'symbols':{}}
    for symbol in ('SPX','XSP'):
        out=report['symbols'][symbol]={}
        try:
            q=service.quote(symbol,True);out['quote']=q
            expirations=service.expirations(symbol)['expirations'];today=service.today().isoformat()
            dates=[d for d in expirations if d>=today]
            out['expirations']=dict(count=len(expirations),nearest=dates[0] if dates else None,zero_dte=today in dates)
            if not dates:continue
            chain=service.chain(symbol,dates[0]);out['chain']=dict(symbol=chain['chain']['symbol'],expiry=dates[0],calls=len(chain['chain']['calls']),puts=len(chain['chain']['puts']))
            out['chain']['near_spot']={side:sorted(chain['chain'][side],key=lambda x:abs(x['strike']-q['quote']['last']))[:3] for side in ('calls','puts')}
            result=UnifiedResearch(service).run(symbol,expiration=dates[0],maximum_candidates=2)
            out['workflow']={k:result.get(k) for k in ('status','stages','errors','market_snapshot','market_structure','live_trade_state')}
            out['trades']=[t['trade_snapshot'] for t in result['qualifying_candidates']]
            out['verticals']=[]
            for t in out['trades']:
                kind='put' if t['short_strike']>t['long_strike'] else 'call'
                r=UnifiedResearch(service).vertical(symbol,t['expiration'],kind,t['short_strike'],t['long_strike'])
                out['verticals'].append(dict(symbol=symbol,strategy=r['trade_snapshot']['strategy'],levels=len(r['historical_analog_behavior']['levels']),payoff_N=r['historical_scenario_payoff']['summary']['n']))
        except APIError as exc:out['error']=exc.code
        except Exception as exc:out['error']='unexpected_validation_failure';out['error_class']=type(exc).__name__
    print(json.dumps(json_value(report),indent=2))

if __name__=='__main__':main()
