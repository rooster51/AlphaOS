"""Canonical JSON, immutable atomic artifacts, and a rebuildable manifest."""
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from datetime import date, datetime
import numpy as np
import pandas as pd


def json_value(value):
    if isinstance(value,dict):
        return {str(k):json_value(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):
        return [json_value(v) for v in value]
    if isinstance(value,pd.DataFrame):
        return json_value(value.to_dict('records'))
    if isinstance(value,pd.Series):
        return json_value(value.to_dict())
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value,(datetime,date,pd.Timestamp)):
        return value.isoformat()
    if isinstance(value,np.generic):
        return json_value(value.item())
    if isinstance(value,float) and not math.isfinite(value):
        return None
    if isinstance(value,(str,int,float,bool)):
        return value
    raise TypeError('Unsupported snapshot value type.')


def canonical_bytes(value):
    return (json.dumps(json_value(value),sort_keys=True,allow_nan=False,separators=(',',':'))+'\n').encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def archive_path(root, kind, session, symbol=None):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',str(session)):
        raise ValueError('Archive session must be YYYY-MM-DD.')
    date.fromisoformat(str(session))
    root=Path(root)
    if kind=='research':
        return root/'daily_quant'/f'{session}.json'
    if kind=='options' and symbol in ('SPY','QQQ'):
        return root/'options'/str(session)/f'{symbol}.json.gz'
    raise ValueError('Unsupported archive kind/symbol.')


def write_artifact(path, value, force=False):
    """Hard-link commit is atomic and fails if another writer won the path."""
    path=Path(path)
    payload=canonical_bytes(value)
    if path.suffix=='.gz':
        payload=gzip.compress(payload,mtime=0)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.snapshot-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as handle:
            handle.write(payload); handle.flush(); os.fsync(handle.fileno())
        if force and path.exists():
            original=path.read_bytes()
            backup=path.parent/'rebuild_backups'/f'{hashlib.sha256(original).hexdigest()}-{path.name}'
            backup.parent.mkdir(exist_ok=True)
            if not backup.exists():
                with backup.open('xb') as handle:
                    handle.write(original)
            os.replace(tmp,path)
        else:
            os.link(tmp,path)  # FileExistsError means immutable artifact retained.
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_artifact(path):
    path=Path(path)
    data=path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix=='.gz' else data)


def scan_archive(root):
    """Files, never the cached manifest, determine the archive inventory."""
    root=Path(root); research=[]; options=[]; issues=[]
    candidates=[('research',p) for p in sorted((root/'daily_quant').glob('????-??-??.json'))]
    candidates += [('options',p) for p in sorted((root/'options').glob('????-??-??/*.json.gz'))]
    for kind,path in candidates:
        try:
            record=read_artifact(path)
            if not isinstance(record,dict) or not isinstance(record.get('generated_at'),str) or not isinstance(record.get('warnings'),list):
                raise ValueError
            session=record['session_date'] if kind=='research' else record['snapshot_date']
            expected=archive_path(root,kind,session,record.get('symbol'))
            if expected!=path or record['schema_version'] != ('daily-quant-v1' if kind=='research' else 'options-archive-v1'):
                raise ValueError
            if kind=='research':
                if record.get('status') not in ('complete','partial') or not isinstance(record.get('symbols'),dict): raise ValueError
                for symbol,item in record['symbols'].items():
                    if symbol not in ('SPY','QQQ') or not isinstance(item,dict): raise ValueError
                    if item.get('status')=='complete':
                        state=item['market_state']; analog=item['historical_analogs']
                        if not isinstance(state['close'],(int,float)) or not math.isfinite(state['close']) or state['close']<=0: raise ValueError
                        if state['ema_structure'] not in ('bullish','bearish','mixed',None): raise ValueError
                        if not isinstance(analog['final_n'],int) or not isinstance(analog['sample_warning'],str) or not isinstance(analog['outcome_summaries'],list): raise ValueError
                    elif item.get('status') not in ('failed','no_new_session'): raise ValueError
            elif (record.get('status') not in ('complete','partial','empty') or
                  not all(isinstance(record.get(k),list) for k in ('valid_contracts','questionable_contracts','rejected_contracts')) or
                  not isinstance(record.get('rejection_counts'),dict) or not isinstance(record.get('quote_timing'),str)):
                raise ValueError
            entry=dict(date=session,path=path.relative_to(root).as_posix(),config_version=record['config_version'],
                       sha256=hashlib.sha256(path.read_bytes()).hexdigest(),status=record['status'])
            if kind=='options':
                entry.update(symbol=record['symbol'],valid_n=len(record['valid_contracts']),
                    questionable_n=len(record['questionable_contracts']),rejected_n=len(record['rejected_contracts']))
            (research if kind=='research' else options).append(entry)
        except Exception:
            issues.append(dict(path=path.relative_to(root).as_posix(),reason='unreadable_or_inconsistent_artifact'))
    return dict(research=research,options=options,issues=issues)


def rebuild_manifest(root):
    root=Path(root); inventory=scan_archive(root)
    dates=sorted({r['date'] for kind in ('research','options') for r in inventory[kind]})
    manifest=dict(schema_version='archive-manifest-v1',latest_research=inventory['research'][-1] if inventory['research'] else None,
        latest_options={s:next((r for r in reversed(inventory['options']) if r['symbol']==s),None) for s in ('SPY','QQQ')},
        research_sessions=len(inventory['research']),option_snapshots=len(inventory['options']),
        earliest_date=dates[0] if dates else None,latest_date=dates[-1] if dates else None,
        config_versions=sorted({r['config_version'] for kind in ('research','options') for r in inventory[kind]}),**inventory)
    root.mkdir(parents=True,exist_ok=True)
    path=root/'archive_manifest.json'
    fd,tmp=tempfile.mkstemp(prefix='.manifest-',dir=root)
    try:
        with os.fdopen(fd,'wb') as handle:
            handle.write(canonical_bytes(manifest))
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    return manifest
