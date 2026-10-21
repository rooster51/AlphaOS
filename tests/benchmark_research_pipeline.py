"""Run with python -m tests.benchmark_research_pipeline; synthetic I/O only.

Copy this file and performance_archive_fixture.py into a baseline checkout to
compare the same verified archives through that checkout's actual REST stack.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import json
import logging
import sys
from time import perf_counter, process_time, sleep

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from modules.research_timing import ResearchTimingMiddleware
from modules.supabase_archive import read_latest_option_snapshot
from tests.performance_archive_fixture import dense_storage, dense_history, AS_OF, LATE_AS_OF
from tests.test_research2_api import boundary


class WireCapture:
    def __init__(self, app):
        self.app, self.sizes = app, {}

    async def __call__(self, scope, receive, send):
        request_id = None
        async def measured_send(message):
            nonlocal request_id
            if message['type'] == 'http.response.start':
                request_id = dict(message['headers']).get(b'x-alphaos-request-id', b'').decode()
                self.sizes[request_id] = 0
            elif message['type'] == 'http.response.body' and request_id is not None:
                self.sizes[request_id] += len(message.get('body',b''))
            await send(message)
        await self.app(scope, receive, measured_send)


def peak_rss():
    if sys.platform != 'win32':
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024)
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [('cb',wintypes.DWORD),('faults',wintypes.DWORD)] + [
            (name,ctypes.c_size_t) for name in ('peak','working','quota_peak_paged','quota_paged',
            'quota_peak_nonpaged','quota_nonpaged','pagefile','peak_pagefile')]
    counters= Counters(); counters.cb=ctypes.sizeof(counters)
    process=ctypes.windll.kernel32.GetCurrentProcess
    process.restype=ctypes.c_void_p
    read=ctypes.windll.psapi.GetProcessMemoryInfo
    read.argtypes=[ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD]
    if not read(process(),ctypes.byref(counters),ctypes.sizeof(counters)):
        return None
    return counters.peak


def economics_digest(value):
    # Ignore chart presentation and added budget metadata. For unchanged search
    # domains all economics, quotes, order and safety labels must still match.
    def project(item):
        if isinstance(item,dict):
            if 'position' in item and 'trade' in item and isinstance(item.get('payoff'),dict):
                item = dict(item)
                item.pop('legs',None)
                item.pop('presentation',None)
                item['payoff'] = {k:v for k,v in item['payoff'].items() if k != 'trade'}
                item['evidence'] = {k:v for k,v in item['evidence'].items() if k != 'option_legs'}
            if item.get('reason') == 'exceeds_available_capital' and isinstance(item.get('research'),dict):
                research = dict(item['research'])
                research.pop('legs',None)
                research.pop('presentation',None)
                research['payoff'] = {k:v for k,v in research['payoff'].items() if k != 'trade'}
                research['evidence'] = {k:v for k,v in research['evidence'].items() if k != 'option_legs'}
                item = dict(item,research=research)
            return {key:project(value) for key,value in item.items()
                    if key not in ('grid','extremes','grid_sampling','max_attempts_per_family','max_total_attempts')}
        if isinstance(item,list): return [project(value) for value in item]
        return item
    return hashlib.sha256(json.dumps(project(value),sort_keys=True,
        separators=(',',':'),allow_nan=False).encode()).hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--width',choices=['auto','5'],default='auto')
    parser.add_argument('--expiration',default='2030-01-02')
    parser.add_argument('--late',action='store_true')
    parser.add_argument('--mode',choices=['current','historical'],default='current')
    parser.add_argument('--production-scale',action='store_true')
    parser.add_argument('--concurrency',type=int,choices=[1,2,4],default=4)
    parser.add_argument('--symbol',choices=['SPY','QQQ'],default='SPY',help='Symbol for independent concurrency=1 runs')
    parser.add_argument('--capital',choices=['150','none'],default='150')
    parser.add_argument('--rounds',type=int,default=2)
    parser.add_argument('--io-delay',type=float,default=.02)
    args=parser.parse_args()
    monkey=MonkeyPatch(); fixture=boundary.__wrapped__(monkey)
    client,_,service,_=next(fixture)
    # Match production redaction work without reading or exposing real secrets.
    for key,value in {'PUBLIC_API_SECRET':'fixture-public-secret',
                      'PUBLIC_ACCOUNT_NUMBER':'fixture-account',
                      'SUPABASE_SERVICE_ROLE_KEY':'fixture-storage-secret',
                      'SUPABASE_URL':'https://fixture.invalid'}.items():
        monkey.setenv(key,value)
    storages={symbol:dense_storage(symbol,late=args.late,production_scale=args.production_scale) for symbol in ('SPY','QQQ')}
    def read(symbol,as_of,**kwargs):
        sleep(args.io_delay)
        return read_latest_option_snapshot(storages[symbol],symbol,as_of,max_age_seconds=300,**kwargs)
    def history(symbol):
        sleep(args.io_delay)
        return dense_history(symbol)
    service.read_snapshot=read; service.history_loader=history
    service.clock=lambda:datetime.fromisoformat('2030-01-03T23:00:00+00:00' if args.mode=='historical' else LATE_AS_OF if args.late else AS_OF)
    app=client.app
    try:
        from alphaos_api.research_compression import ResearchCompressionMiddleware
        app=ResearchCompressionMiddleware(app)
    except ImportError:
        pass  # Original main has no response-compression middleware.
    wire=WireCapture(ResearchTimingMiddleware(app))
    client=TestClient(wire,base_url='https://alphaos.onrender.com')
    events={}
    class Capture(logging.Handler):
        def emit(self,record):
            event=json.loads(record.getMessage())
            if event.get('phase')=='end':
                events.setdefault(event['request_id'],{})[event['stage']]=event.get('duration_ms',event.get('elapsed_ms'))
    logger=logging.getLogger('alphaos_api.research.timing')
    handler=Capture(); logger.addHandler(handler); logger.setLevel(logging.WARNING)
    logger.propagate=False
    try:
        for round_index in range(args.rounds):
            def invoke(index):
                symbol=args.symbol if args.concurrency==1 else ('SPY','QQQ')[index%2]
                request_id=f'{round_index*4+index+1:032x}'
                start=perf_counter()
                response=client.post('/v1/research/market',json=dict(symbol=symbol,
                    expiration=args.expiration,available_capital=150 if args.capital=='150' else None,
                    research_mode=args.mode, width=None if args.width=='auto' else 5),headers={
                    'Authorization':'Bearer owner-test-secret','X-AlphaOS-Request-ID':request_id})
                assert response.status_code==200,response.text[:100]
                data=response.json(); session=data['research']['research_session']
                return dict(symbol=symbol,request_id=request_id,wall_ms=round((perf_counter()-start)*1000),
                    generated=session['diagnostics']['generated_count'],accepted=len(session['candidates']),
                    decoded_bytes=len(response.content),wire_bytes=wire.sizes[request_id],
                    economics_sha256=economics_digest(data))
            wall,cpu=perf_counter(),process_time()
            with ThreadPoolExecutor(args.concurrency) as pool:
                rows=list(pool.map(invoke,range(args.concurrency)))
            for row in rows: row['stage_ms']=events.get(row['request_id'],{})
            print(json.dumps(dict(round=round_index,width=args.width,expiration=args.expiration,late=args.late,
                mode=args.mode,concurrency=args.concurrency,fixture_contracts=len(storages['SPY'].payload['options']['valid_contracts']),
                capital=args.capital,
                wall_ms=round((perf_counter()-wall)*1000),cpu_ms=round((process_time()-cpu)*1000),
                peak_rss_bytes=peak_rss(),requests=rows)),flush=True)
    finally:
        logger.removeHandler(handler)
        fixture.close();monkey.undo()


if __name__=='__main__': main()
