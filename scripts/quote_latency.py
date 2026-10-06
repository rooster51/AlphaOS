"""Read-only internal diagnostic. Run with python -m scripts.quote_latency --help."""
import argparse
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
from modules.quote_latency import observation, write_artifacts


def sample(fetch, symbols, duration, interval, directory, *, monotonic=time.monotonic, sleep=time.sleep, clock=lambda:datetime.now(timezone.utc)):
    rows = []
    start = monotonic()
    count = int(duration // interval)+1
    try:
        for index in range(count):
            delay = start+index*interval-monotonic()
            if delay>0:
                sleep(delay)
            for symbol in symbols:
                try:
                    row = observation(symbol,fetch(symbol),clock())
                except Exception:
                    row = dict(symbol=symbol,observed_at=clock().isoformat(),request_ok=False,
                        error='quote_retrieval_failed',cache_hit=None)
                rows.append(row)
            write_artifacts(rows,directory)
    finally:
        if rows:
            write_artifacts(rows,directory)
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--symbols',nargs='+',default=['QQQ','SPY'])
    parser.add_argument('--duration-minutes',type=float,default=30)
    parser.add_argument('--interval-seconds',type=float,default=60)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--api-url',help='Existing AlphaOS REST origin. Without this, retrieve directly from configured Public account.')
    parser.add_argument('--token-env-file',type=Path,help='Optional local ALPHAOS_API_TOKEN env file, used only in REST mode.')
    args = parser.parse_args(argv)
    if not (0<args.duration_minutes<=120 and 10<=args.interval_seconds<=3600):
        parser.error('Duration must be >0 and <=120 minutes; interval 10-3600 seconds.')
    symbols = list(dict.fromkeys(s.upper() for s in args.symbols))
    if len(symbols)>20 or any(not re.fullmatch('[A-Z]{1,6}',s) for s in symbols):
        parser.error('Supply up to 20 plain equity symbols.')
    directory = args.output or Path('diagnostics/quote-latency')/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    logging.disable(logging.CRITICAL)
    client = None
    try:
        if args.api_url:
            parsed = urlsplit(args.api_url)
            if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment:
                raise ValueError('Invalid origin')
            token = os.environ.get('ALPHAOS_API_TOKEN')
            if not token and args.token_env_file:
                for line in args.token_env_file.read_text(encoding='utf-8-sig').splitlines():
                    if line.strip().startswith('ALPHAOS_API_TOKEN='):
                        token = line.strip().split('=',1)[1].strip().strip('\"\'')
            if not token:
                raise ValueError('Missing owner token')
            import httpx
            client = httpx.Client(base_url=args.api_url.rstrip('/'),headers={'Authorization':'Bearer '+token},timeout=45,follow_redirects=False)
            def fetch(symbol):
                response = client.get('/v1/quote/'+symbol)
                response.raise_for_status()
                return response.json()['evidence']
        else:
            if args.token_env_file:
                raise ValueError('Token file requires REST mode')
            from alphaos_api.config import load_secret_files
            from modules.public_provider import get_public_quotes
            from modules.quote_freshness import freshness
            load_secret_files()
            def fetch(symbol):
                rows = get_public_quotes((symbol,))
                matches = [q for q in rows if q.get('symbol')==symbol]
                if len(matches)!=1:
                    raise ValueError('Missing quote')
                q = matches[0]
                return dict(quote=q,retrieved_at=q['retrieved_at'],freshness=freshness(q),
                    cache=dict(hit=False,mode='direct_provider_no_AlphaOS_cache'))
        rows = sample(fetch,symbols,args.duration_minutes*60,args.interval_seconds,directory)
        print('Saved observations.csv and summary.json in '+str(directory.resolve()))
        return 0 if all(r['request_ok'] for r in rows) else 1
    except KeyboardInterrupt:
        print('Interrupted; collected market observations were saved.')
        return 130
    except Exception:
        print('Diagnostic failed. Check configuration, credentials, network and output directory. No provider error details are printed.')
        return 1
    finally:
        if client:
            client.close()


if __name__=='__main__':
    raise SystemExit(main())
