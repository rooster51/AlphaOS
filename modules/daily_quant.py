"""Point-in-time daily orchestration. Reuses Phase 2–4 calculations unchanged."""
from datetime import datetime, timedelta, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import re
from zoneinfo import ZoneInfo
import pandas as pd

from modules.daily_archive import archive_path, digest, json_value, rebuild_manifest, scan_archive, write_artifact
from modules.daily_sessions import SessionCalendar
from modules.daily_public import DailyPublicProvider
from modules.market_state_research import build_research_dataset
from modules.market_state import VERSION as MARKET_VERSION
from modules.historical_analogs import (analog_research,sensitivity_analysis,sample_warning,
    DEFAULT_TOLERANCES,NUMERIC_FEATURES,VERSION as ANALOG_VERSION)
from modules.threshold_survival import threshold_research,VERSION as THRESHOLD_VERSION
from modules.options_archive import build_options_snapshot

SCHEMA_VERSION='daily-quant-v1'
ROOT=Path(__file__).resolve().parents[1]
WARNINGS=[
    'Descriptive historical frequencies, not forecast probabilities, provider/model POP, or option profitability.',
    'Overlapping analogs are dependent; Wilson intervals are nominal binomial diagnostics.',
    'Provider OHLC adjustment and historical point-in-time revision history remain unverified.',
    'Snapshot captures information retrieved at generated_at, not an archived historical market-close feed.',
    'Research and options are separate artifacts; no quote, candidate, ranking or trade recommendation is joined to research.'
]


def load_config(path=None):
    config=json.loads(Path(path or ROOT/'config/daily_quant.json').read_text(encoding='utf-8'))
    validate_config(config)
    return config


def validate_config(c):
    try:
        if set(c)!={'version','symbols','history','analog','sensitivity','thresholds','options','calendar','earliest_collection_hour_et'}: raise ValueError
        if not re.fullmatch(r'daily-quant-config-v[0-9]+',c['version']): raise ValueError
        if not c['symbols'] or len(set(c['symbols']))!=len(c['symbols']) or not set(c['symbols']).issubset({'SPY','QQQ'}): raise ValueError
        if c['history']!='TEN_YEARS' or c['calendar']!='NYSE' or c['earliest_collection_hour_et']!=17: raise ValueError
        # Freeze the existing default research method, including sensitivity.
        expected=dict(method='tolerance',horizon=3,numerical_features=list(NUMERIC_FEATURES),
                      tolerances=DEFAULT_TOLERANCES,exact_structure=True)
        if c['analog']!=expected or not isinstance(c['sensitivity'],bool): raise ValueError
        t=c['thresholds'];o=c['options']
        if set(t)!={'distances','modes','horizons'} or t['modes']!=['put','call'] or t['horizons']!=[1,2,3,5,10]: raise ValueError
        if t['distances']!=[.005,.01,.015,.02,.025,.03]: raise ValueError
        if set(o)!={'min_dte','max_dte','strike_band'}: raise ValueError
        if type(o['min_dte']) is not int or type(o['max_dte']) is not int or not 0<=o['min_dte']<=o['max_dte']<=365: raise ValueError
        if type(o['strike_band']) not in (int,float) or not 0<o['strike_band']<1: raise ValueError
    except (KeyError,TypeError,ValueError):
        raise ValueError('Invalid daily config; preserve frozen research defaults and valid option-universe settings.') from None


def engine_versions():
    dependencies={}
    for package in ('pandas','numpy','publicdotcom-py','pandas-market-calendars'):
        try: dependencies[package]=importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: dependencies[package]=None
    return dict(market_state=MARKET_VERSION,historical_analogs=ANALOG_VERSION,
                threshold_research=THRESHOLD_VERSION,dependencies=dependencies)


def research_for_symbol(history,symbol,session,config,calendar):
    cutoff=pd.Timestamp(session)+pd.Timedelta(days=1)
    dates=pd.to_datetime(history.date,utc=True,errors='coerce',format='mixed')
    if dates.isna().any(): raise ValueError('Invalid history dates.')
    expected=calendar.sessions(str(dates.min().date()),session)
    dataset=build_research_dataset(history.assign(symbol=symbol),cutoff,
        metadata=dict(source='Public regularMarket ONE_DAY OHLC',requested_period=config['history'],
                      provider_diagnostics=history.attrs.get('provider_diagnostics',{}),
                      completion_policy='Scheduled runner includes session only after NYSE calendar close and 17:00 America/New_York.'),
        expected_sessions=expected)
    if dataset['metadata']['end']!=session:
        return dict(status='no_new_session',reason='latest_completed_session_not_returned')
    features,outcomes=dataset['features'],dataset['outcomes']
    analogs=analog_research(features,outcomes,**config['analog'])
    sensitivity=sensitivity_analysis(features,outcomes,horizon=config['analog']['horizon'],exact_structure=True) if config['sensitivity'] else []
    thresholds=[]
    for mode in config['thresholds']['modes']:
        for magnitude in config['thresholds']['distances']:
            for horizon in config['thresholds']['horizons']:
                result=threshold_research(analogs,mode,horizon,threshold_return=-magnitude if mode=='put' else magnitude)
                thresholds.append(dict(config=result['config'],summary=result['summary'],
                    non_overlapping_summary=result['non_overlapping_summary'],distribution_percentiles=result['distribution_percentiles']))
    return json_value(dict(status='complete',market_state=features.iloc[-1],source_metadata=dataset['metadata'],
        historical_analogs=dict(config=analogs['config'],candidate_n=analogs['audit']['eligible_dates'],final_n=len(analogs['analogs']),
            audit=analogs['audit'],feature_funnel=analogs['funnel'],independent_passes=analogs['independent_passes'],
            sample_warning=sample_warning(len(analogs['analogs'])),notes=analogs['notes'],
            sensitivity=sensitivity,outcome_summaries=analogs['summary'],matched_dates=analogs['analogs'].date.dt.strftime('%Y-%m-%d').tolist()),
        thresholds=thresholds))


def run_daily_quant(root=None,config=None,now=None,provider_factory=None,calendar=None,force=False,code_revision=None):
    config=config or load_config();validate_config(config)
    now=now or datetime.now(timezone.utc)
    calendar=calendar or SessionCalendar()
    if force and os.environ.get('GITHUB_ACTIONS')=='true':
        raise ValueError('Force rebuild is developer-only and disabled in GitHub Actions.')
    if code_revision is not None and not re.fullmatch(r'[0-9a-fA-F]{40}',code_revision):
        raise ValueError('Code revision must be a full commit SHA.')
    session,reason=calendar.eligible_session(now,config['earliest_collection_hour_et'])
    report=dict(status='skipped',reason=reason,session_date=session,research=None,options={},errors=[])
    if session is None: return report
    root=Path(root or ROOT/'data')
    research_path=archive_path(root,'research',session)
    option_paths={s:archive_path(root,'options',session,s) for s in config['symbols']}
    root.mkdir(parents=True,exist_ok=True)
    lock=root/'.daily-quant.lock'
    try:
        fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:
        return dict(report,status='failed',reason='another_run_or_stale_lock',errors=['archive_locked'])
    os.close(fd)
    try:
        active_paths={p.relative_to(root).as_posix() for p in (research_path,*option_paths.values())}
        if not force and any(issue['path'] in active_paths for issue in scan_archive(root)['issues']):
            return dict(report,status='failed',reason='existing_artifact_invalid',errors=['inspect_existing_artifact_before_retry'])
        needs_research=force or not research_path.exists()
        needs_options={s:p for s,p in option_paths.items() if force or not p.exists()}
        if not needs_research and not needs_options:
            rebuild_manifest(root)
            return dict(report,reason='no_new_session_existing_immutable_artifacts')
        try:
            provider=(provider_factory or DailyPublicProvider.from_environment)()
        except Exception:
            return dict(report,status='failed',reason='provider_unavailable',errors=['provider_configuration_or_authentication_failed'])
        config_hash=digest(config)
        if needs_research:
            symbols={}
            for symbol in config['symbols']:
                try:
                    history=provider.history(symbol,config['history'],now.astimezone(ZoneInfo('America/New_York')).date())
                    symbols[symbol]=research_for_symbol(history,symbol,session,config,calendar)
                except Exception:
                    symbols[symbol]=dict(status='failed',reason='history_or_research_failed')
                if symbols[symbol]['status']=='failed': report['errors'].append(symbol+'_research_failed')
            successful=sum(r['status']=='complete' for r in symbols.values())
            if all(r['status']=='no_new_session' for r in symbols.values()):
                return dict(report,status='skipped',reason='latest_completed_session_not_returned')
            if successful:
                report['errors'] += [s+'_research_latest_session_unavailable' for s,r in symbols.items() if r['status']=='no_new_session']
            if successful:
                payload=dict(schema_version=SCHEMA_VERSION,session_date=session,generated_at=provider.now().isoformat(),
                    config_version=config['version'],config_sha256=config_hash,config=config,engine_versions=engine_versions(),
                    code_revision=code_revision,provider=provider.name,status='complete' if successful==len(symbols) else 'partial',
                    warnings=WARNINGS+(['One or more symbols failed or lacked the latest session; this immutable research snapshot is partial.'] if successful!=len(symbols) else []),
                    rebuild=bool(force),symbols=symbols)
                write_artifact(research_path,payload,force)
                report['research']=dict(status=payload['status'],path=research_path.relative_to(root).as_posix())
            else:
                report['research']=dict(status='failed' if report['errors'] else 'no_new_session')
        else:
            report['research']=dict(status='skipped_existing')
        for symbol,path in option_paths.items():
            if symbol not in needs_options:
                report['options'][symbol]=dict(status='skipped_existing');continue
            try:
                archive=build_options_snapshot(provider,symbol,session,config['options'],config['version'],config_hash,code_revision)
                archive['rebuild']=bool(force)
                write_artifact(path,archive,force)
                report['options'][symbol]=dict(status=archive['status'],path=path.relative_to(root).as_posix())
                if archive['status']=='partial': report['errors'].append(symbol+'_options_partial')
            except Exception:
                report['options'][symbol]=dict(status='failed',reason='options_retrieval_or_validation_failed')
                report['errors'].append(symbol+'_options_failed')
        rebuild_manifest(root)
        report.update(status='partial' if report['errors'] else 'complete',reason='daily_collection_finished')
        return report
    finally:
        lock.unlink()
