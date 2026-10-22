"""Diagnostic-only construction/traversal counts. Never a latency benchmark."""
import sys,json,cProfile,pstats,collections,time,gc,hashlib
from pathlib import Path
from datetime import datetime
sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
from tests.performance_archive_fixture import dense_storage,dense_history
from modules.supabase_archive import read_latest_option_snapshot
from alphaos_api.research2 import ArchiveResearchService,MarketRequest
import alphaos_api.app as api

out={}
for symbol in ('SPY','QQQ'):
 storage=dense_storage(symbol,production_scale=True)
 service=ArchiveResearchService(read_snapshot=lambda s,a,**kw:read_latest_option_snapshot(storage,s,a,max_age_seconds=300,**kw),history_loader=dense_history,clock=lambda:datetime.fromisoformat('2030-01-03T23:00:00+00:00'))
 profile=cProfile.Profile();profile.enable()
 raw=service.run(MarketRequest(symbol=symbol,research_mode='historical',expiration='2030-01-18'),json_ready=False)
 profile.disable()
 stats=[]
 for (file,line,name),(primitive,total,own,cumulative,callers) in pstats.Stats(profile).stats.items():
  if any(word in file for word in ('position_research','structure_research','options_payoff','premium_engine','strategy_compare','copy.py','opportunity_session')):stats.append(dict(file=Path(file).name,line=line,function=name,calls=total,primitive_calls=primitive,own_s=own,cumulative_s=cumulative))
 # Match actual sanitizer recursion: shared lists are visited only once; dicts are not memoized.
 dict_visits=collections.Counter();list_visits=collections.Counter();seen_lists=set();keep={};scalar=collections.Counter()
 def walk(x):
  if isinstance(x,dict):
   dict_visits[id(x)]+=1;keep[id(x)]=x
   for v in x.values():walk(v)
  elif isinstance(x,(tuple,list)):
   list_visits[id(x)]+=1
   if id(x) in seen_lists:return
   seen_lists.add(id(x))
   for v in x:walk(v)
  else:scalar[type(x).__name__]+=1
 walk(raw)
 duplicate_types=collections.Counter()
 for i,n in dict_visits.items():
  if n>1:duplicate_types[','.join(sorted(str(k) for k in keep[i])[:8])]+=n-1
 session=raw['research']['research_session']
 out[symbol]=dict(candidates=len(session['candidates']),excluded=len(session['excluded']),functions=sorted(stats,key=lambda x:x['cumulative_s'],reverse=True),dict_visits=sum(dict_visits.values()),unique_dicts=len(dict_visits),repeat_dict_visits=sum(dict_visits.values())-len(dict_visits),list_visits=sum(list_visits.values()),unique_lists=len(list_visits),scalar_visits=scalar,duplicate_dict_shapes=duplicate_types.most_common(15))
 gc_events=[];starts={}
 def cb(phase,info):
  if phase=='start':starts[info['generation']]=time.process_time()
  else:gc_events.append(dict(generation=info['generation'],cpu_ms=(time.process_time()-starts[info['generation']])*1000,collected=info['collected']))
 gc.callbacks.append(cb);start=time.process_time();encoded=api.encode_json(api.sanitized(raw));out[symbol]['sanitizer_and_encoding_cpu_ms']=(time.process_time()-start)*1000;gc.callbacks.remove(cb)
 out[symbol]['gc_during_sanitization']=gc_events;out[symbol]['bytes']=len(encoded);out[symbol]['sha256']=hashlib.sha256(encoded).hexdigest()
 del raw,keep,encoded;gc.collect()
Path(sys.argv[1]).write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({s:{k:v for k,v in d.items() if k not in ('functions','gc_during_sanitization')} for s,d in out.items()},indent=2))

