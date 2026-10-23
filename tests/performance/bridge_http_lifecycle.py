"""Actual isolated Next HTTPS-upstream/HTTP-downstream probe validation; no market data."""
import concurrent.futures, gzip, hashlib, http.client, ipaddress, json, os, subprocess, time
from datetime import datetime,timedelta,timezone
from pathlib import Path
import requests
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT=Path.cwd();OUT=Path(os.environ.get('HTTP_FIXTURE_OUTPUT',ROOT/'bridge-http-results'));OUT.mkdir(exist_ok=True)
TRIAL=int(os.environ.get('TRIAL','0'));KEY='CONTROL_ONLY_CREDENTIAL_CANARY';rows=[];aborts=[];launch=[]
def command(*args,**kw):return subprocess.run(args,check=True,**kw)
def cert():
 key=rsa.generate_private_key(public_exponent=65537,key_size=2048);name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'origin')]);now=datetime.now(timezone.utc)
 certificate=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=2)).add_extension(x509.SubjectAlternativeName([x509.DNSName('origin'),x509.DNSName('localhost'),x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),critical=False).sign(key,hashes.SHA256()))
 (OUT/'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.TraditionalOpenSSL,serialization.NoEncryption()));(OUT/'cert.pem').write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
def ready(url,verify=True):
 started=time.perf_counter()
 while time.perf_counter()-started<120:
  try:
   if requests.get(url,timeout=1,verify=verify).status_code==200:return
  except requests.RequestException:pass
  time.sleep(.2)
 raise RuntimeError('controlled server startup failed')
def call(mode,symbol,scenario,kind):
 start=time.perf_counter()
 with requests.post(os.environ.get('HTTP_WEB_URL','http://127.0.0.1:3000')+'/api/research/market',json={'symbol':symbol,'objective':scenario},headers={'Accept-Encoding':'gzip'},stream=True,timeout=40) as r:
  headers=(time.perf_counter()-start)*1000;wire=r.raw.read(decode_content=False);complete=(time.perf_counter()-start)*1000
  body=gzip.decompress(wire) if r.headers.get('Content-Encoding')=='gzip' else wire
  assert KEY.encode() not in body
  row=dict(mode=mode,kind=kind,scenario=scenario,symbol=symbol,status=r.status_code,request_id=r.headers.get('X-AlphaOS-Request-ID'),headers_ms=headers,complete_ms=complete,wire_bytes=len(wire),decoded_bytes=len(body),sha256=hashlib.sha256(body).hexdigest(),code=json.loads(body).get('code'),cache=r.headers.get('Cache-Control'))
  rows.append(row);return row
def pair(mode,scenario,kind):
 with concurrent.futures.ThreadPoolExecutor(2) as pool:return list(pool.map(lambda s:call(mode,s,scenario,kind),['SPY','QQQ']))
def client_abort(mode):
 conn=http.client.HTTPConnection(os.environ.get('HTTP_WEB_HOST','127.0.0.1'),3000,timeout=5);start=time.perf_counter();conn.request('POST','/api/research/market',body=json.dumps({'symbol':'SPY','objective':'client_abort'}),headers={'Content-Type':'application/json'});time.sleep(.5);conn.close();aborts.append(dict(mode=mode,client_closed_ms=(time.perf_counter()-start)*1000));time.sleep(2)
def snapshot(container,path):
 (OUT/path).write_bytes(subprocess.check_output(['docker','logs',container],stderr=subprocess.STDOUT))
def inspect_usage(container,mode):
 for name in ['cpu.max','cpu.stat','memory.max','memory.peak','memory.events']:
  (OUT/f'{mode}-{name}.txt').write_bytes(subprocess.check_output(['docker','exec',container,'cat','/sys/fs/cgroup/'+name]))
def validate():
 origin=[json.loads(line) for line in (OUT/'origin.jsonl').read_text().splitlines()]
 cases={};timings=[];privacy=True
 allowed={'event','version','request_id','status','fetch_started_ms','headers_received_ms','body_consumption_end_ms','validated_ms','body_json_completed','body_decompression_decode_parse_ms','upstream_declared_content_length_bytes','elapsed_ms','deadline_elapsed_ms','deadline_budget_exceeded','timeout_signal_aborted','timeout_observed_ms','client_aborted'}
 for mode in ['disabled','enabled']:
  logs=[]
  for line in (OUT/f'{mode}-next.log').read_text().splitlines():
   try:d=json.loads(line)
   except ValueError:continue
   if d.get('event') in ['research_bridge','research_bridge_probe']:logs.append(d)
  assert KEY not in (OUT/f'{mode}-next.log').read_text();assert 'BODY_CANARY' not in (OUT/f'{mode}-next.log').read_text()
  for r in [x for x in rows if x['mode']==mode]:
   base=next(x for x in logs if x.get('event')=='research_bridge' and x.get('request_id')==r['request_id']);assert base.get('timeout_ms')==12000
   matching=[x for x in origin if x.get('request_id')==r['request_id']];assert matching,'correlation missing'
   probes=[x for x in logs if x.get('event')=='research_bridge_probe' and x.get('request_id')==r['request_id']]
   assert len(probes)==(1 if mode=='enabled' else 0)
   if probes:
    p=probes[0];assert set(p)<=allowed;assert p['status']==r['status'];assert p['elapsed_ms']>=p.get('headers_received_ms',0)
    present=[p[k] for k in ['fetch_started_ms','headers_received_ms','body_consumption_end_ms','validated_ms','elapsed_ms'] if k in p];assert present==sorted(present)
    if r['status']==200:assert p['body_consumption_end_ms']<=p['validated_ms'];assert p['body_json_completed']
    # Native timer expiry and separately sampled performance.now() are not the
    # same clock boundary (sub-ms origin/rounding). Do not conflate these facts.
    if r['scenario'] in ['timeout_body','timeout_headers']:assert p['timeout_signal_aborted'] and p['timeout_observed_ms'] is not None
    timings.append(p)
   if r['scenario'] in ['complete','delayed','gzip','unicode']:assert r['status']==200 and base['backend_correlated']
   if r['scenario'] in ['partial','interrupted','malformed']:assert (r['status'],r['code'])==(502,'response_schema_mismatch')
   if r['scenario'].startswith('timeout'):assert (r['status'],r['code'])==(502,'backend_timeout')
   key=(r['scenario'],r['symbol']);fingerprint=(r['status'],r['sha256'],r['decoded_bytes'],r['code'],r['cache']);cases.setdefault(key,set()).add(fingerprint)
  abort_requests=[x for x in origin if x.get('event')=='origin_request' and x.get('scenario')=='client_abort']
  mode_abort=abort_requests[0 if mode==('disabled' if TRIAL%2==0 else 'enabled') else 1]
  peer=[x for x in origin if x.get('event')=='origin_close' and x.get('request_id')==mode_abort['request_id']]
  aborts[[x['mode'] for x in aborts].index(mode)]['upstream_close']=peer
  # Compare cancellation classifications without pretending a disconnected client received a response.
  abort_logs=[x for x in logs if x.get('event')=='research_bridge' and x.get('request_id')==mode_abort['request_id']]
  aborts[[x['mode'] for x in aborts].index(mode)]['bridge_abort_logs']=abort_logs
  assert peer and not peer[0]['finished'] and peer[0]['elapsed_ms']<2500,'upstream cancellation missing'
  assert abort_logs and abort_logs[0]['status']==499,'bridge cancellation missing'
  for entry in logs:
   if entry.get('event')=='research_bridge_probe':assert set(entry)<=allowed
 assert all(len(v)==1 for v in cases.values()),'response bytes/status/error parity failed'
 cancellation=[[(r['status'],r.get('stage')) for r in x['bridge_abort_logs']] for x in aborts];assert cancellation[0]==cancellation[1],'client cancellation parity failed'
 result=dict(trial=TRIAL,response_parity=True,correlation=True,timing_order=True,privacy=True,aborts=aborts,probe_timings=timings,rows=rows,launch=launch)
 (OUT/'report.json').write_text(json.dumps(result,indent=2));print(json.dumps(dict(trial=TRIAL,requests=len(rows),response_parity=True,privacy=True)))

def run_client(mode):
 before=time.perf_counter();ready('http://next:3000/api/health');launch.append(dict(mode=mode,startup_to_health_ms=(time.perf_counter()-float(os.environ.get('HTTP_NEXT_LAUNCHED_MONO',before)))*1000))
 pair(mode,'complete','first_request')
 for scenario in ['delayed','gzip','unicode','malformed','partial','interrupted','timeout_headers','timeout_body']:pair(mode,scenario,'behavior')
 client_abort(mode)
 for n in range(3):
  for symbol in ['SPY','QQQ']:call(mode,symbol,'complete','warm_sequential')
 for n in range(6):pair(mode,'complete','warm_concurrent')
 (OUT/f'client-{mode}.json').write_text(json.dumps(dict(rows=rows,aborts=aborts,launch=launch)))

if os.environ.get('HTTP_FIXTURE_CHECK_ORIGIN'):
 ready('https://origin:8768/health',str(OUT/'cert.pem'))
elif os.environ.get('HTTP_FIXTURE_CLIENT_MODE'):
 run_client(os.environ['HTTP_FIXTURE_CLIENT_MODE'])
else:
 cert();command('docker','build','-f','tests/performance/Dockerfile.bridge-http','-t','alphaos-bridge-http','.')
 command('docker','build','-f','tests/performance/Dockerfile.bridge-http-client','-t','alphaos-bridge-http-client','.')
 command('docker','network','create','--internal','bridge-probe-http')
 command('docker','run','-d','--name','origin','--network','bridge-probe-http','--cpus','.15','--memory','512m','--memory-swap','512m','-v',f'{OUT}:/out','-v',f'{ROOT}/tests/performance/bridge-http-origin.mjs:/origin.mjs:ro','node:24.21.0-bookworm-slim','node','/origin.mjs')
 try:
  command('docker','run','--rm','--network','bridge-probe-http','-v',f'{ROOT}:/repo:ro','-v',f'{OUT}:/out:ro','-e','HTTP_FIXTURE_OUTPUT=/out','-e','HTTP_FIXTURE_CHECK_ORIGIN=1','alphaos-bridge-http-client','python','tests/performance/bridge_http_lifecycle.py')
  for mode in (['disabled','enabled'] if TRIAL%2==0 else ['enabled','disabled']):
   before=time.perf_counter()
   command('docker','run','-d','--name','next','--network','bridge-probe-http','--cpus','.15','--memory','512m','--memory-swap','512m','-v',f'{OUT}/cert.pem:/cert.pem:ro','-e','NODE_EXTRA_CA_CERTS=/cert.pem','-e','ALPHAOS_API_URL=https://origin:8768','-e',f'ALPHAOS_API_TOKEN={KEY}','-e',f'ALPHAOS_BRIDGE_TIMING_PROBE={1 if mode=="enabled" else 0}','alphaos-bridge-http')
   try:
    command('docker','run','--rm','--network','bridge-probe-http','-v',f'{ROOT}:/repo:ro','-v',f'{OUT}:/out','-e','HTTP_FIXTURE_OUTPUT=/out','-e',f'HTTP_FIXTURE_CLIENT_MODE={mode}','-e',f'HTTP_NEXT_LAUNCHED_MONO={before}','-e','HTTP_WEB_URL=http://next:3000','-e','HTTP_WEB_HOST=next','alphaos-bridge-http-client','python','tests/performance/bridge_http_lifecycle.py')
    result=json.loads((OUT/f'client-{mode}.json').read_text());rows.extend(result['rows']);aborts.extend(result['aborts']);launch.extend(result['launch'])
   finally:
    snapshot('next',f'{mode}-next.log');inspect_usage('next',mode);command('docker','rm','-f','next')
  validate()
 finally:
  snapshot('origin','origin-console.log');command('docker','rm','-f','origin');command('docker','network','rm','bridge-probe-http')
  (OUT/'measurements.json').write_text(json.dumps(dict(rows=rows,aborts=aborts,launch=launch),indent=2))
