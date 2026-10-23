"""Local-only instrumented fixture server. Never deploy this harness."""
import argparse,sys,os,json,time,gc,threading,hashlib,gzip,logging,tracemalloc,ast
from pathlib import Path
from contextvars import ContextVar
from datetime import datetime
REPO=Path(os.environ['DIAGNOSTIC_REPO']);ROOT=Path(os.environ['DIAGNOSTIC_OUTPUT'])
sys.path[:0]=[str(REPO),str(REPO/'tests')]
parser=argparse.ArgumentParser();parser.add_argument('--cores',type=float,default=0);parser.add_argument('--log',required=True);parser.add_argument('--allocations',action='store_true');parser.add_argument('--variant',choices=['baseline','candidate'],default='candidate');args=parser.parse_args()
import uvicorn
from modules.research_timing import _trace
from modules.supabase_archive import read_latest_option_snapshot
from tests.performance_archive_fixture import dense_storage,dense_history
from alphaos_api.research2 import ArchiveResearchService
import alphaos_api.app as api
from starlette.middleware.gzip import GZipResponder
from tests.benchmark_research_pipeline import peak_rss
def limits(cores):
    return dict(kind='Linux Docker cgroup',cpu_max=Path('/sys/fs/cgroup/cpu.max').read_text().strip(),
        memory_max=Path('/sys/fs/cgroup/memory.max').read_text().strip(),
        cpu_stat=Path('/sys/fs/cgroup/cpu.stat').read_text(),platform=sys.platform)
def peak_commit():return int(Path('/sys/fs/cgroup/memory.peak').read_text())
sink=open(args.log,'w',encoding='utf-8',buffering=1);lock=threading.RLock()
request=ContextVar('local_profile_request',default=None)
operations=ContextVar('local_profile_operations',default=None)
def emit(**data):
    with lock:sink.write(json.dumps(dict(time=time.perf_counter(),request_id=request.get(),**data))+'\n')
gc_starts={}
def gc_event(phase,info):
    generation=info['generation']
    if phase=='start':gc_starts[generation]=(time.perf_counter(),time.thread_time())
    else:
        w,c=gc_starts.pop(generation,(time.perf_counter(),time.thread_time()))
        emit(kind='gc',generation=generation,wall_ms=(time.perf_counter()-w)*1000,cpu_ms=(time.thread_time()-c)*1000,collected=info['collected'])
gc.callbacks.append(gc_event)
os.environ['ALPHAOS_API_TOKEN']='local-diagnostic-token'
for key in ('PUBLIC_API_SECRET','PUBLIC_ACCOUNT_NUMBER','SUPABASE_SERVICE_ROLE_KEY','SUPABASE_URL'):os.environ[key]='fixture-'+key
storages={s:dense_storage(s,production_scale=True) for s in ('SPY','QQQ')}
for s in storages.values():
    s.raw=gzip.compress(json.dumps(s.payload).encode(),mtime=0);s.row['archive_sha256']=hashlib.sha256(s.raw).hexdigest()
def measured(name,fn):
    def wrapped(*a,**kw):
        wall=time.perf_counter();cpu=time.thread_time()
        try:return fn(*a,**kw)
        finally:
            elapsed=(time.perf_counter()-wall)*1000;spent=(time.thread_time()-cpu)*1000
            stats=operations.get()
            if stats is None:emit(kind='operation',stage=name,wall_ms=elapsed,cpu_ms=spent)
            else:
                row=stats.setdefault(name,dict(wall_ms=0,cpu_ms=0,calls=0));row['wall_ms']+=elapsed;row['cpu_ms']+=spent;row['calls']+=1
    return wrapped
api.sanitized=measured('sanitization_redaction',api.sanitized)
api.encode_json=measured('json_encoding',api.encode_json)
GZipResponder._compress_body=measured('compression',GZipResponder._compress_body)
def read(symbol,as_of,**kw):
    time.sleep(.02)
    return read_latest_option_snapshot(storages[symbol],symbol,as_of,max_age_seconds=300,**kw)
def history(symbol):
    from modules.research_timing import stage
    with stage('history_dependency_import'):
        import public_api_sdk
    with stage('history_provider_stub'):
        time.sleep(.02)
        return dense_history(symbol)
api.app.state.archive_research=ArchiveResearchService(read_snapshot=read,history_loader=history,clock=lambda:datetime.fromisoformat('2030-01-03T23:00:00+00:00'))
starts={}
class Timing(logging.Handler):
    def emit(self,record):
        try:d=json.loads(record.getMessage())
        except ValueError:return
        key=(d.get('request_id'),d.get('stage'));cpu=time.thread_time()
        if d.get('phase')=='start':starts[key]=cpu
        elif d.get('phase')=='end':
            emit(kind='pipeline',stage=d.get('stage'),wall_ms=d.get('duration_ms'),cpu_ms=(cpu-starts.pop(key,cpu))*1000,elapsed_ms=d.get('elapsed_ms'),outcome=d.get('outcome'))
logger=logging.getLogger('alphaos_api.research.timing');logger.handlers=[Timing()];logger.propagate=False;logger.setLevel(logging.WARNING)
class Profile:
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or scope['path']=='/health':return await self.app(scope,receive,send)
        token=request.set(dict(scope['headers']).get(b'x-alphaos-request-id',b'').decode())
        operation_token=operations.set({})
        wall=time.perf_counter();cpu=time.process_time();wire=0;send_ms=0;headers_ms=None;status=None
        async def tracked(message):
            nonlocal wire,send_ms,headers_ms,status
            if message['type']=='http.response.start':headers_ms=(time.perf_counter()-wall)*1000;status=message['status']
            if message['type']=='http.response.body':wire+=len(message.get('body',b''))
            start=time.perf_counter();await send(message);send_ms+=(time.perf_counter()-start)*1000
        try:await self.app(scope,receive,tracked)
        finally:
            data=dict(kind='request_end',status=status,headers_ms=headers_ms,complete_ms=(time.perf_counter()-wall)*1000,process_cpu_ms=(time.process_time()-cpu)*1000,wire_bytes=wire,asgi_send_ms=send_ms,peak_rss_bytes=peak_rss(),cgroup_peak_memory_bytes=peak_commit(),cpu_stat=Path('/sys/fs/cgroup/cpu.stat').read_text(),memory_events=Path('/sys/fs/cgroup/memory.events').read_text())
            if args.allocations:
                data['gc_tracked_objects']=len(gc.get_objects())
                data['traced_current_bytes'],data['traced_peak_bytes']=tracemalloc.get_traced_memory()
                data['top_allocations']=[str(s) for s in tracemalloc.take_snapshot().statistics('lineno')[:8]]
            for name,totals in operations.get().items():emit(kind='operation',stage=name,**totals)
            emit(**data);operations.reset(operation_token);request.reset(token)
config=limits(args.cores)
from importlib.metadata import version
emit(kind='configuration',variant=args.variant,limits=config,imports_before_cap=False,provider_authentication='stubbed, not measured',history_http='20ms synthetic stub',platform=sys.platform,python=sys.version,cpu_model=next((line for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')),''),packages={name:version(name) for name in ['numpy','pandas','fastapi','orjson','starlette','publicdotcom-py']})
if args.allocations:tracemalloc.start(1)
uvicorn.run(Profile(api.app),host='0.0.0.0',port=8768,ssl_keyfile=str(ROOT/'key.pem'),ssl_certfile=str(ROOT/'cert.pem'),log_level='error')
