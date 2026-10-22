"""Intrusive retention/allocations profile; excluded from latency benchmarks."""
import argparse,ast,collections,gc,hashlib,json,sys,time,tracemalloc,weakref
from pathlib import Path
from datetime import datetime
root=Path(__file__).resolve().parents[2];sys.path[:0]=[str(root),str(root/'tests')]
from tests.performance_archive_fixture import dense_storage,dense_history
from modules.supabase_archive import read_latest_option_snapshot
from alphaos_api.research2 import ArchiveResearchService,MarketRequest
import alphaos_api.app as api
from alphaos_api.buffered_research_json import encode_research_response

class SourceList(list):pass

def run(variant,symbol):
 storage=dense_storage(symbol,production_scale=True)
 service=ArchiveResearchService(read_snapshot=lambda s,a,**kw:read_latest_option_snapshot(storage,s,a,max_age_seconds=300,**kw),history_loader=dense_history,clock=lambda:datetime.fromisoformat('2030-01-03T23:00:00+00:00'))
 events=[];starts={}
 def callback(phase,info):
  if phase=='start':starts[info['generation']]=(time.perf_counter(),time.process_time())
  else:
   w,c=starts.pop(info['generation']);events.append(dict(generation=info['generation'],wall_ms=(time.perf_counter()-w)*1000,cpu_ms=(time.process_time()-c)*1000,collected=info['collected']))
 def sample():
  objects=gc.get_objects();counts=collections.Counter(type(o).__name__ for o in objects);del objects
  current,peak=tracemalloc.get_traced_memory()
  return dict(tracked_objects=sum(counts.values()),tracked_types=counts.most_common(10),traced_current_bytes=current,traced_peak_bytes=peak)
 gc.collect();gc.callbacks.append(callback);tracemalloc.start(1);report=dict(variant=variant,symbol=symbol,phases={})
 report['phases']['start']=sample()
 raw=service.run(MarketRequest(symbol=symbol,research_mode='historical',expiration='2030-01-18'),json_ready=False)
 raw['research']['research_session']['candidates']=SourceList(raw['research']['research_session']['candidates'])
 source=weakref.ref(raw['research']['research_session']['candidates'])
 report['phases']['research_built']=sample()
 # Deliberately disable GC only in this intrusive diagnostic to distinguish
 # reference retention from automatic collection timing. Never used in serving.
 enabled=gc.isenabled();gc.disable()
 try:
  w=time.perf_counter();c=time.process_time()
  body=api.encode_json(api.sanitized(raw)) if variant=='baseline' else encode_research_response(raw,sanitize=api.sanitized,encode=api.encode_json)
  report['diagnostic_encode_wall_ms']=(time.perf_counter()-w)*1000;report['diagnostic_encode_cpu_ms']=(time.process_time()-c)*1000
  report.update(bytes=len(body),sha256=hashlib.sha256(body).hexdigest())
  report['phases']['body_encoded']=sample()
  report['top_retained_allocations']=[str(s) for s in tracemalloc.take_snapshot().statistics('lineno')[:12]]
  del raw
  report['source_retained_after_releasing_response_input']=source() is not None
  report['phases']['input_released']=sample()
  del body
  report['phases']['body_released_before_gc']=sample()
  report['forced_gc_collected']=gc.collect()
  report['phases']['after_forced_gc']=sample()
 finally:
  if enabled:gc.enable()
  gc.callbacks.remove(callback);tracemalloc.stop()
 report['gc_events']=events
 return report
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--variant',choices=['baseline','candidate'],required=True);p.add_argument('--symbol',choices=['SPY','QQQ'],required=True);p.add_argument('--output',required=True);a=p.parse_args();Path(a.output).write_text(json.dumps(run(a.variant,a.symbol),indent=2)+'\n')
