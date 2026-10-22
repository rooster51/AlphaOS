"""Count response traversal calls; deliberately excluded from latency runs."""
import sys,json,collections,gc
from pathlib import Path
from datetime import datetime
root=Path(__file__).resolve().parents[2];sys.path[:0]=[str(root),str(root/'tests')]
from tests.performance_archive_fixture import dense_storage,dense_history
from modules.supabase_archive import read_latest_option_snapshot
from alphaos_api.research2 import ArchiveResearchService,MarketRequest
import alphaos_api.app as api
from alphaos_api.buffered_research_json import encode_research_response
out={}
for symbol in ('SPY','QQQ'):
 storage=dense_storage(symbol,production_scale=True)
 service=ArchiveResearchService(read_snapshot=lambda s,a,**kw:read_latest_option_snapshot(storage,s,a,max_age_seconds=300,**kw),history_loader=dense_history,clock=lambda:datetime.fromisoformat('2030-01-03T23:00:00+00:00'))
 raw=service.run(MarketRequest(symbol=symbol,research_mode='historical',expiration='2030-01-18'),json_ready=False);out[symbol]={}
 for variant in ('baseline','candidate'):
  gc.collect();counts=collections.Counter();ids=collections.defaultdict(collections.Counter)
  def profile(frame,event,arg):
   if event=='call' and frame.f_code.co_name=='clean' and frame.f_code.co_filename==api.__file__:
    value=frame.f_locals['item'];kind=type(value).__name__;counts[kind]+=1
    if isinstance(value,(list,dict,tuple)):ids[kind][id(value)]+=1
  sys.setprofile(profile)
  try:
   b=api.encode_json(api.sanitized(raw)) if variant=='baseline' else encode_research_response(raw,sanitize=api.sanitized,encode=api.encode_json)
  finally:sys.setprofile(None)
  out[symbol][variant]=dict(clean_calls=dict(counts),unique_containers={k:len(v) for k,v in ids.items()},repeat_container_calls={k:sum(v.values())-len(v) for k,v in ids.items()},bytes=len(b))
 del raw,b;gc.collect()
Path(sys.argv[1]).write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
