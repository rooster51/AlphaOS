"""Drive isolated local Docker profiles on an existing Linux CI runner.

No production network access, secrets, image publication or application changes.
"""
import concurrent.futures
from datetime import datetime,timedelta,timezone
import hashlib
import gzip
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import time

import requests
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa

REPO=Path.cwd();OUT=REPO/'lifecycle-results';OUT.mkdir(exist_ok=True)
NETWORK='alphaos-issue60-profile'
rows=[];reference={};captured=set()
def semantic(value):
    # Existing Next JSON parsing/stringification spells integral doubles as
    # integers. Compare all parsed values, not their Python/JS number spelling.
    if isinstance(value,dict):return {k:semantic(v) for k,v in value.items()}
    if isinstance(value,list):return [semantic(v) for v in value]
    if type(value) is float and value.is_integer():return int(value)
    return value
def command(*args,**kw):return subprocess.run(args,check=True,**kw)
def ready(url,verify=True):
    start=time.monotonic()
    while time.monotonic()-start<100:
        try:
            if requests.get(url,verify=verify,timeout=1).status_code==200:return
        except requests.RequestException:pass
        time.sleep(.2)
    raise RuntimeError('Diagnostic server did not start: '+url)
def call(symbol,tag,direct=False):
    start=time.perf_counter()
    try:
        r=requests.post('https://127.0.0.1:8768/v1/research/market' if direct else 'http://127.0.0.1:3017/api/research/market',
            json=dict(symbol=symbol,research_mode='historical',expiration='2030-01-18'),
            headers={'Authorization':'Bearer local-diagnostic-token','X-AlphaOS-Request-ID':hashlib.md5(tag.encode()).hexdigest()},
            verify=str(OUT/'cert.pem') if direct else True,stream=True,timeout=150)
        headers=(time.perf_counter()-start)*1000;body=r.content;complete=(time.perf_counter()-start)*1000
        parse=time.perf_counter();data=r.json();parse_ms=(time.perf_counter()-parse)*1000
        full=data if direct else data.get('research',{})
        digest=hashlib.sha256(json.dumps(semantic(full),sort_keys=True,separators=(',',':')).encode()).hexdigest() if r.status_code==200 else None
        if digest:
            capture=tag.split('-')[0]+'-'+symbol
            if capture not in captured:
                (OUT/('sample-'+capture+'.json.gz')).write_bytes(gzip.compress(json.dumps(full).encode(),mtime=0))
                captured.add(capture)
            if symbol in reference:assert digest==reference[symbol],(tag,'full response parity failed')
            else:reference[symbol]=digest
        row=dict(tag=tag,symbol=symbol,direct=direct,status=r.status_code,code=data.get('code'),request_id=r.headers.get('X-AlphaOS-Request-ID'),headers_ms=headers,complete_ms=complete,client_parse_ms=parse_ms,decoded_bytes=len(body),full_response_sha256=digest)
    except requests.RequestException as e:
        row=dict(tag=tag,symbol=symbol,direct=direct,error=type(e).__name__,complete_ms=(time.perf_counter()-start)*1000)
    rows.append(row);print(json.dumps(row),flush=True);(OUT/'measurements.json').write_text(json.dumps(rows,indent=2))
def pair(tag,direct=False):
    start=time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(2) as pool:list(pool.map(lambda s:call(s,tag+'-'+s,direct),('SPY','QQQ')))
    print(json.dumps(dict(batch=tag,wall_ms=(time.perf_counter()-start)*1000)),flush=True)
def run(label,limited,first,variant,alloc=False):
    names=[]
    try:
        common=['--network',NETWORK,'--memory','512m','--memory-swap','512m',
            '-v',str(REPO)+':/repo:ro','-v',str(OUT)+':/results','-e','DIAGNOSTIC_REPO=/repo','-e','DIAGNOSTIC_OUTPUT=/results']
        if limited:common+=['--cpus','0.15']
        name=label+'-backend';names.append(name)
        args=['docker','run','-d','--name',name,'--network-alias','backend',*common,'-p','127.0.0.1:8768:8768','alphaos-profile-python',
            'python','/repo/tests/performance/lifecycle_backend.py','--log','/results/'+label+'-backend.jsonl','--variant',variant]
        if alloc:args+=['--allocations']
        command(*args,stdout=subprocess.DEVNULL)
        ready('https://127.0.0.1:8768/health',str(OUT/'cert.pem'))
        if alloc:
            pair(label+'-allocations',direct=True);return
        name=label+'-bridge';names.append(name)
        command('docker','run','-d','--name',name,*common,'-p','127.0.0.1:3017:3017',
            '-e','ALPHAOS_API_URL=https://backend:8768','-e','ALPHAOS_API_TOKEN=local-diagnostic-token',
            '-e','LOCAL_PROFILE_LOG=/results/'+label+'-bridge.jsonl','-e','NODE_EXTRA_CA_CERTS=/results/cert.pem',
            'node:24.21.0-bookworm-slim','node','--experimental-strip-types','/repo/tests/performance/lifecycle_bridge.mjs',stdout=subprocess.DEVNULL)
        ready('http://127.0.0.1:3017/health')
        if first=='pair':pair(label+'-first-pair')
        else:call(first,label+'-first-'+first)
        for i in range(2):
            for s in ('SPY','QQQ'):call(s,f'{label}-sequential-{i}-{s}')
            pair(f'{label}-concurrent-{i}')
        pair(label+'-direct',direct=True)
    finally:
        for name in names:
            with (OUT/(name+'-console.txt')).open('w') as f:subprocess.run(['docker','logs',name],stdout=f,stderr=f)
            with (OUT/(name+'-inspect.json')).open('w') as f:subprocess.run(['docker','inspect',name],stdout=f)
            subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--detail',action='store_true');parser.add_argument('--case',choices=['SPY','QQQ','pair']);args=parser.parse_args()
    (OUT/'baseline_app.py').write_bytes(subprocess.check_output(['git','show','ff0a42efe74f964733cd2f0ea79e7456a1e862c8:alphaos_api/app.py']))
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048);name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'AlphaOS local fixture')]);now=datetime.now(timezone.utc)
    cert=x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True).add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1')),x509.DNSName('backend')]),critical=False).sign(key,hashes.SHA256())
    (OUT/'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()));(OUT/'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    command('docker','network','create',NETWORK,stdout=subprocess.DEVNULL)
    try:
        for limited in (False,True):
            for first in ([args.case] if args.case else ('pair',) if args.detail else ('SPY','QQQ','pair')):
                i=('SPY','QQQ','pair').index(first)
                for variant in (('baseline','candidate') if i%2==0 else ('candidate','baseline')):
                    run(variant+'-'+('limited' if limited else 'control')+str(i),limited,first,variant)
        for variant in ('baseline','candidate'):run(variant+'-allocations'+(args.case or ''),False,'pair',variant,alloc=True)
    finally:
        subprocess.run(['docker','network','rm',NETWORK],stdout=subprocess.DEVNULL)
        (OUT/'key.pem').unlink(missing_ok=True);(OUT/'cert.pem').unlink(missing_ok=True)
if __name__=='__main__':main()
