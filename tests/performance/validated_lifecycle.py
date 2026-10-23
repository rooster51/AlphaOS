"""Matched Linux Docker trials of the actual Next server; never production."""
import concurrent.futures,gzip,hashlib,io,ipaddress,json,math,os,subprocess,tarfile,time
from pathlib import Path
from datetime import datetime,timedelta,timezone
import requests
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
REPO=Path.cwd();OUT=REPO/'lifecycle-results';OUT.mkdir(exist_ok=True)
BASELINE=OUT/'baseline_repo';BASELINE.mkdir(exist_ok=True)
with tarfile.open(fileobj=io.BytesIO(subprocess.check_output(['git','archive','76a6a1696d007aeb6aab31fa33c6dad847608688']))) as archive:archive.extractall(BASELINE,filter='data')
import shutil
shutil.copytree(REPO/'tests/performance',BASELINE/'tests/performance',dirs_exist_ok=True)
NETWORK='issue60-validated-json';rows=[];reference={};round_id=int(os.environ.get('TRIAL','0'))
def command(*args,**kw):return subprocess.run(args,check=True,**kw)
def ready(url,verify=True):
 start=time.monotonic()
 while time.monotonic()-start<150:
  try:
   if requests.get(url,verify=verify,timeout=1).status_code==200:return
  except requests.RequestException:pass
  time.sleep(.2)
 raise RuntimeError('Diagnostic startup failed: '+url)
def semantic(x):
 if isinstance(x,dict):return {k:semantic(v) for k,v in x.items()}
 if isinstance(x,list):return [semantic(v) for v in x]
 return int(x) if type(x) is float and x.is_integer() else x
def economics(x):
 if isinstance(x,dict):
  if isinstance(x.get('trade'),dict) and isinstance(x.get('payoff'),dict) and 'capital_at_risk' in x:
   t=x['trade'];legs=t['legs'];credit=t['credit'];fees=t.get('fees',0)
   def pnl(s):return 100*(credit+sum(l['qty']*max(0,s-l['strike'] if l['type'].lower()=='call' else l['strike']-s) for l in legs))-fees
   v=[pnl(s) for s in [0]+[l['strike'] for l in legs]]
   assert math.isclose(max(0,-min(v)),x['max_loss'],abs_tol=1e-6)
   assert x['capital_at_risk']==x['max_loss']
   if sum(l['qty'] for l in legs if l['type'].lower()=='call')==0 and isinstance(x['max_profit'],(int,float)):assert math.isclose(max(v),x['max_profit'],abs_tol=1e-6)
   for b in x.get('breakevens',[]):assert abs(pnl(b))<1e-6
   for g in x['payoff'].get('grid',[]):assert math.isclose(pnl(g['Terminal underlying ($)']),g['Expiration P&L ($)'],abs_tol=1e-6)
   for l in legs:assert l['expiration']==t['expiration'] and l.get('contract') and l.get('quote_timestamp') and not l.get('rejection_reasons')
  for v in x.values():economics(v)
 elif isinstance(x,list):
  for v in x:economics(v)
def call(symbol,tag,direct=False,cold_start=None,extra=None,auth=True):
 start=time.perf_counter();payload=dict(symbol=symbol,research_mode='historical',expiration='2030-01-18');payload.update(extra or {});headers={'X-AlphaOS-Request-ID':hashlib.md5(tag.encode()).hexdigest()}
 if auth:headers['Authorization']='Bearer local-diagnostic-token'
 row=dict(tag=tag,symbol=symbol,direct=direct,payload=payload)
 try:
  r=requests.post('https://127.0.0.1:8768/v1/research/market' if direct else 'http://127.0.0.1:3017/api/research/market',json=payload,headers=headers,verify=str(OUT/'cert.pem') if direct else True,stream=True,timeout=90)
  row.update(status=r.status_code,headers_ms=1000*(time.perf_counter()-start),request_id=r.headers.get('X-AlphaOS-Request-ID'));body=r.content
  row.update(complete_ms=1000*(time.perf_counter()-start),decoded_bytes=len(body))
  if cold_start is not None:row['container_launch_to_body_ms']=1000*(time.perf_counter()-cold_start)
  d=json.loads(body);row['code']=d.get('code',d.get('error',{}).get('code') if isinstance(d.get('error'),dict) else None)
  full=d if direct else d.get('research',{})
  if r.status_code==200:
   assert full['request']['symbol']==symbol and full['research']['expiration']==payload['expiration']
   assert full['read_only'] is True
   assert full['request'].get('width')==payload.get('width')
   if payload.get('available_capital'):
    assert all(c['research']['capital_at_risk']<=payload['available_capital'] for c in full['research']['research_session']['candidates'])
   storage=full['research']['archive']['storage'];assert len(storage['archive_sha256'])==64 and storage['quality_status']=='complete'
   assert b'local-diagnostic-token' not in body and b'fixture-PUBLIC_API_SECRET' not in body
   assert not d.get('verified_for_trading',False)
   economics(full)
   digest=hashlib.sha256(json.dumps(semantic(full),sort_keys=True,separators=(',',':')).encode()).hexdigest()
   row['full_semantic_sha256']=digest
   if payload==dict(symbol=symbol,research_mode='historical',expiration='2030-01-18'):
    if symbol in reference:assert digest==reference[symbol],(tag,'semantic parity failed')
    else:reference[symbol]=digest
   if direct:(OUT/(tag+'.json.gz')).write_bytes(gzip.compress(json.dumps(full).encode(),mtime=0))
   row['validated']=True
 except requests.RequestException as e:row.update(error=type(e).__name__,complete_ms=1000*(time.perf_counter()-start))
 rows.append(row);(OUT/'measurements.json').write_text(json.dumps(rows,indent=2));print(json.dumps(row),flush=True);return row
def pair(tag,**kwargs):
 with concurrent.futures.ThreadPoolExecutor(2) as pool:list(pool.map(lambda s:call(s,tag+'-'+s,**kwargs),('SPY','QQQ')))
def run(variant):
 names=[];label=f'{round_id}-{variant}';launch=time.perf_counter()
 try:
  common=['--network',NETWORK,'--cpus','0.15','--memory','512m','--memory-swap','512m','-v',str(OUT)+':/results','-e','DIAGNOSTIC_REPO=/repo','-e','DIAGNOSTIC_OUTPUT=/results']
  name=label+'-backend';names.append(name)
  command('docker','run','-d','--name',name,'--network-alias','backend',*common,'-v',str(REPO)+':/repo:ro','-p','127.0.0.1:8768:8768','alphaos-profile-python','python','/repo/tests/performance/lifecycle_backend.py','--variant','candidate','--log','/results/'+label+'-backend.jsonl',stdout=subprocess.DEVNULL)
  name=label+'-next';names.append(name)
  command('docker','run','-d','--name',name,*common,'-p','127.0.0.1:3017:3000','-e','ALPHAOS_API_URL=https://backend:8768','-e','ALPHAOS_API_TOKEN=local-diagnostic-token','-e','NODE_EXTRA_CA_CERTS=/results/cert.pem','issue60-next-'+variant,stdout=subprocess.DEVNULL)
  ready('https://127.0.0.1:8768/health',str(OUT/'cert.pem'));ready('http://127.0.0.1:3017/api/health')
  startup=1000*(time.perf_counter()-launch);(OUT/(label+'-startup.json')).write_text(json.dumps(dict(startup_to_ready_ms=startup,infrastructure_provisioning='excluded: images already built; Docker process and app startup included')))
  pair(label+'-cold',cold_start=launch)
  # Drain canceled work before the next sample; test no more than one pair.
  time.sleep(5)
  for n in range(6):
   pair(label+f'-warm-{n}');time.sleep(5)
  for s in ['SPY','QQQ']:call(s,label+'-sequential-'+s)
  pair(label+'-rest',direct=True)
  for s in ['SPY','QQQ']:
   call(s,label+'-150-'+s,extra={'available_capital':150})
   call(s,label+'-manual-'+s,extra={'width':5,'available_capital':150})
   call(s,label+'-long-'+s,extra={'expiration':'2031-01-17'})
  call('SPY',label+'-invalid',extra={'expiration':'2030-02-30'})
  call('SPY',label+'-exact-mismatch',extra={'expiration':'2030-01-19'})
  call('SPY',label+'-unauth',direct=True,auth=False)
 finally:
  for name in names:
   with (OUT/(name+'-console.txt')).open('w') as f:subprocess.run(['docker','logs',name],stdout=f,stderr=f)
   with (OUT/(name+'-inspect.json')).open('w') as f:subprocess.run(['docker','inspect',name],stdout=f)
   for metric in ['cpu.stat','memory.peak','memory.events']:
    with (OUT/(name+'-'+metric+'.txt')).open('w') as f:subprocess.run(['docker','exec',name,'cat','/sys/fs/cgroup/'+metric],stdout=f,stderr=f)
   subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
def main():
 key=rsa.generate_private_key(public_exponent=65537,key_size=2048);name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Local lifecycle fixture')]);now=datetime.now(timezone.utc)
 cert=x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True).add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1')),x509.DNSName('backend')]),critical=False).sign(key,hashes.SHA256())
 (OUT/'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()));(OUT/'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
 dockerfile=REPO/'tests/performance/Dockerfile.next'
 command('docker','build','-f',str(dockerfile),'-t','issue60-next-baseline',str(BASELINE));command('docker','build','-f',str(dockerfile),'-t','issue60-next-candidate',str(REPO))
 command('docker','network','create',NETWORK,stdout=subprocess.DEVNULL)
 try:
  for variant in (['baseline','candidate'] if round_id%2==0 else ['candidate','baseline']):run(variant)
 finally:
  subprocess.run(['docker','network','rm',NETWORK],stdout=subprocess.DEVNULL)
  (OUT/'key.pem').unlink(missing_ok=True);(OUT/'cert.pem').unlink(missing_ok=True)
if __name__=='__main__':main()
