"""Read-only Public index capability audit. Only allowlisted market evidence leaves the runner."""
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo


def quote_summary(raw):
    fields=('outcome','last','lastTimestamp','bid','ask','previousClose','volume')
    return [dict(symbol=q.get('instrument',{}).get('symbol'),**{k:q.get(k) for k in fields}) for q in raw.get('quotes',[])]


def history_summary(raw):
    bars=raw.get('regularMarket',{}).get('bars',[])
    return dict(symbol=raw.get('symbol'),period=raw.get('period'),count=len(bars),leading_fill=bool(raw.get('leadingFill')),
        first=bars[0].get('timestamp') if bars else None,last=bars[-1].get('timestamp') if bars else None,
        sample=[{k:b.get(k) for k in ('timestamp','open','high','low','close','volume')} for b in bars[-2:]])


def chain_summary(raw):
    result=dict(base_symbol=raw.get('baseSymbol'))
    for side in ('calls','puts'):
        rows=raw.get(side,[])
        def safe(q):
            d=q.get('optionDetails') or {}
            return dict(contract=q.get('instrument',{}).get('symbol'),strike=d.get('strikePrice'),bid=q.get('bid'),ask=q.get('ask'),
                bid_timestamp=q.get('bidTimestamp'),ask_timestamp=q.get('askTimestamp'),greeks=d.get('greeks'),mid=d.get('midPrice'))
        result[side]=dict(count=len(rows),sample=[safe(q) for q in rows[max(0,len(rows)//2-2):len(rows)//2+3]])
        strikes=sorted({float(q['optionDetails']['strikePrice']) for q in rows if (q.get('optionDetails') or {}).get('strikePrice') is not None})
        result[side]['spacing']=sorted({round(b-a,5) for a,b in zip(strikes,strikes[1:])})[:20]
    return result


def main():
    from public_api_sdk import PublicApiClient,ApiKeyAuthConfig
    from modules.public_session import _select_account
    report=dict(observed_at=datetime.now(ZoneInfo('UTC')).isoformat(),symbols={})
    if not os.environ.get('PUBLIC_API_SECRET'):
        print(json.dumps(dict(error='missing_public_secret')));return
    stage='authentication'
    try:
        client=PublicApiClient(ApiKeyAuthConfig(api_secret_key=os.environ['PUBLIC_API_SECRET'].strip(),validity_minutes=15))
        accounts=client.get_accounts().accounts
        stage='account_selection'
        account=_select_account(accounts,os.environ.get('PUBLIC_ACCOUNT_NUMBER') or None).account_id
    except Exception as exc:
        status=getattr(exc,'status_code',None)
        print(json.dumps(dict(error='public_access_failed',stage=stage,http_status=status if isinstance(status,int) else None)));return
    def request(label,fn,summarize):
        try:
            raw=fn();return dict(request=label,status=200,result=summarize(raw)),raw
        except Exception as exc:
            status=getattr(exc,'status_code',None)
            return dict(request=label,status=status if isinstance(status,int) else None,error='provider_request_failed'),None
    today=datetime.now(ZoneInfo('America/New_York')).date().isoformat()
    for symbol in ('SPX','XSP'):
        out=report['symbols'][symbol]=[]
        entry,_=request('quote INDEX '+symbol,lambda:client.api_client.post(f'/userapigateway/marketdata/{account}/quotes',json_data={'instruments':[dict(symbol=symbol,type='INDEX')]}),quote_summary);out.append(entry)
        entry,_=request('history INDEX '+symbol+' FIVE_YEARS ONE_DAY',lambda:client.api_client.get(f'/userapigateway/historicdata/INDEX/{symbol}/FIVE_YEARS/ONE_DAY'),history_summary);out.append(entry)
        for kind in ('UNDERLYING_SECURITY_FOR_INDEX_OPTION','INDEX'):
            entry,raw=request('expirations '+kind+' '+symbol,lambda:client.api_client.post(f'/userapigateway/marketdata/{account}/option-expirations',json_data={'instrument':dict(symbol=symbol,type=kind)}),lambda r:dict(base_symbol=r.get('baseSymbol'),expirations=r.get('expirations'),zero_dte=today in r.get('expirations',[])))
            out.append(entry)
            if not raw or not raw.get('expirations'):continue
            dates=sorted(x for x in raw['expirations'] if x>=today)
            for expiry in dates[:3]:
                entry,_=request('chain '+kind+' '+symbol+' '+expiry,lambda:client.api_client.post(f'/userapigateway/marketdata/{account}/option-chain',json_data={'instrument':dict(symbol=symbol,type=kind),'expirationDate':expiry}),chain_summary);out.append(entry)
            break
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
