import copy
from datetime import datetime, timezone
import gzip
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import numpy as np
import pandas as pd

from modules.daily_archive import archive_path,write_artifact,read_artifact,rebuild_manifest,scan_archive,canonical_bytes,digest
from modules.daily_quant import load_config,run_daily_quant,research_for_symbol,validate_config
from modules.daily_public import DailyPublicProvider,ProviderUnavailable
from modules.daily_sessions import SessionCalendar
from modules.options_archive import normalize_contract,build_options_snapshot

NOW=datetime(2026,9,22,22,23,tzinfo=timezone.utc)
DAY='2026-09-22'


def quote(symbol='SPY',side='C',strike=100,expiration=DAY,**overrides):
    item=dict(instrument=dict(symbol=f'{symbol}{expiration[2:].replace("-","")}{side}{int(strike*1000):08d}',type='OPTION'),
        outcome='SUCCESS',bid=1.,ask=1.2,last=1.1,volume=10,openInterest=300,
        bidTimestamp='2026-09-22T20:00:00Z',askTimestamp='2026-09-22T20:00:00Z',lastTimestamp='2026-09-22T19:55:00Z',
        optionDetails=dict(strikePrice=strike,midPrice=1.1,greeks=dict(delta=.3,gamma=.01,theta=-.1,vega=.2,rho=.01,impliedVolatility=.25)))
    item.update(overrides);return item


class FixtureCalendar:
    def eligible_session(self,now,earliest_hour=17): return DAY,'completed_session'
    def sessions(self,start,end): return pd.bdate_range(start,end)


class FixtureProvider:
    name='Public'
    def now(self): return NOW
    def history(self,symbol,period,as_of):
        days=pd.bdate_range(end=DAY,periods=280)
        prices=100+np.sin(np.arange(len(days))/7)*2
        return pd.DataFrame(dict(date=days,open=prices,high=prices+1,low=prices-1,close=prices,volume=1000))
    def underlying(self,symbol): return dict(instrument=dict(symbol=symbol,type='EQUITY'),last=100.,outcome='SUCCESS',lastTimestamp='2026-09-22T20:00:00Z')
    def expirations(self,symbol): return [DAY,'2026-10-02','2026-10-03']
    def chain(self,symbol,expiration): return dict(calls=[quote(symbol,expiration=expiration)],puts=[quote(symbol,'P',expiration=expiration)])


def small_research(*args,**kwargs):
    symbol=args[1]
    return dict(status='complete',market_state=dict(symbol=symbol,close=100.,ema_structure='mixed'),
        historical_analogs=dict(final_n=2,sample_warning='Small sample',outcome_summaries=[]),thresholds=[])


class DailyRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'data'
        self.config=load_config();self.provider=FixtureProvider()
    def tearDown(self): self.temp.cleanup()
    def run_pipeline(self,**kwargs):
        return run_daily_quant(root=self.root,config=self.config,now=NOW,calendar=FixtureCalendar(),
                               provider_factory=lambda:self.provider,**kwargs)

    def test_spy_and_qqq_research_actual_engines_schema(self):
        report=self.run_pipeline(code_revision='a'*40)
        self.assertEqual(report['status'],'complete')
        snapshot=read_artifact(archive_path(self.root,'research',DAY))
        self.assertEqual(snapshot['schema_version'],'daily-quant-v1')
        self.assertEqual(snapshot['generated_at'],NOW.isoformat())
        self.assertEqual(snapshot['config_sha256'],digest(self.config))
        self.assertEqual(snapshot['code_revision'],'a'*40)
        for symbol in ('SPY','QQQ'):
            data=snapshot['symbols'][symbol]
            self.assertEqual(data['market_state']['symbol'],symbol)
            self.assertIsInstance(data['market_state']['rsi_14'],float)
            self.assertEqual(len(data['thresholds']),60)
            self.assertEqual(len(data['historical_analogs']['sensitivity']),15)
            self.assertEqual(len(data['historical_analogs']['outcome_summaries']),5)
            self.assertEqual(data['historical_analogs']['config']['horizon'],3)
            self.assertTrue(data['historical_analogs']['config']['exact_structure'])
            self.assertNotIn('options',data)
            self.assertEqual(data['source_metadata']['end'],DAY)
        json.loads(canonical_bytes(snapshot),parse_constant=lambda value: self.fail('Nonstandard JSON numeric constant'))

    def test_default_configuration_matches_phase_three_exactly(self):
        from modules.historical_analogs import DEFAULT_TOLERANCES,NUMERIC_FEATURES
        self.assertEqual(self.config['analog']['tolerances'],DEFAULT_TOLERANCES)
        self.assertEqual(self.config['analog']['numerical_features'],list(NUMERIC_FEATURES))
        self.assertEqual(self.config['options'],dict(min_dte=0,max_dte=10,strike_band=.1))

    def test_config_rejects_unknown_keys_and_parameter_drift(self):
        for mutation in (lambda c:c.update(secret='DO_NOT_WRITE'),lambda c:c['analog'].update(horizon=5),
                         lambda c:c['options'].update(strike_band=float('nan'))):
            c=copy.deepcopy(self.config);mutation(c)
            with self.assertRaises(ValueError): validate_config(c)

    def test_immutability_and_no_network_on_rerun(self):
        with patch('modules.daily_quant.research_for_symbol',side_effect=small_research): self.run_pipeline()
        path=archive_path(self.root,'research',DAY);before=path.read_bytes()
        factory=Mock(side_effect=AssertionError('No network on complete repeat'))
        report=run_daily_quant(root=self.root,config=self.config,now=NOW,calendar=FixtureCalendar(),provider_factory=factory)
        self.assertEqual(report['status'],'skipped');factory.assert_not_called()
        self.assertEqual(before,path.read_bytes())
        with self.assertRaises(FileExistsError): write_artifact(path,{'changed':True})

    def test_force_rebuild_preserves_original_backup(self):
        with patch('modules.daily_quant.research_for_symbol',side_effect=small_research):
            self.run_pipeline();path=archive_path(self.root,'research',DAY);original=path.read_bytes()
            with patch.dict(os.environ,{'GITHUB_ACTIONS':'false'}): self.run_pipeline(force=True)
        self.assertTrue(read_artifact(path)['rebuild'])
        self.assertEqual(next((path.parent/'rebuild_backups').iterdir()).read_bytes(),original)
        self.assertEqual(rebuild_manifest(self.root)['research_sessions'],1)

    def test_actions_cannot_force_rebuild(self):
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true'}),self.assertRaisesRegex(ValueError,'developer-only'):
            self.run_pipeline(force=True)

    def test_weekend_and_holiday_no_files_or_provider(self):
        calendar=SessionCalendar()
        for date in ('2026-09-26','2026-12-25'):
            factory=Mock()
            report=run_daily_quant(root=self.root,config=self.config,now=datetime.fromisoformat(date+'T22:23:00+00:00'),calendar=calendar,provider_factory=factory)
            self.assertEqual(report['reason'],'non_trading_day');factory.assert_not_called()
            self.assertFalse(self.root.exists())

    def test_before_collection_window(self):
        report=run_daily_quant(root=self.root,now=datetime(2026,9,22,20,30,tzinfo=timezone.utc),provider_factory=Mock())
        self.assertEqual(report['reason'],'before_collection_window')

    def test_dst_and_standard_time_schedule(self):
        calendar=SessionCalendar()
        for date in ('2026-07-07','2026-12-22'):
            session,reason=calendar.eligible_session(datetime.fromisoformat(date+'T22:23:00+00:00'))
            self.assertEqual(session,date)
        session,reason=calendar.eligible_session(datetime(2026,11,27,19,tzinfo=timezone.utc))
        self.assertIsNone(session)  # Early close still waits until 17 ET.

    def test_lagging_provider_does_not_label_old_research_today(self):
        history=self.provider.history('SPY','TEN_YEARS',NOW.date()).iloc[:-1]
        result=research_for_symbol(history,'SPY',DAY,self.config,FixtureCalendar())
        self.assertEqual(result['status'],'no_new_session')

    def test_no_new_session_exits_without_daily_artifacts(self):
        original=self.provider.history
        self.provider.history=lambda *args:original(*args).iloc[:-1]
        self.provider.chain=Mock()
        report=self.run_pipeline()
        self.assertEqual(report['status'],'skipped')
        self.assertEqual(report['reason'],'latest_completed_session_not_returned')
        self.assertFalse(archive_path(self.root,'research',DAY).exists())
        self.provider.chain.assert_not_called()

    def test_partial_symbol_failure_separate_artifacts(self):
        def research(history,symbol,*args):
            if symbol=='QQQ': raise RuntimeError('SECRET_PAYLOAD')
            return small_research(history,symbol)
        with patch('modules.daily_quant.research_for_symbol',side_effect=research): report=self.run_pipeline()
        self.assertEqual(report['status'],'partial')
        payload=read_artifact(archive_path(self.root,'research',DAY))
        self.assertEqual(payload['symbols']['QQQ']['status'],'failed')
        self.assertEqual(payload['symbols']['SPY']['status'],'complete')
        self.assertTrue(archive_path(self.root,'options',DAY,'QQQ').exists())
        self.assertNotIn('SECRET_PAYLOAD',json.dumps(report)+json.dumps(payload))

    def test_provider_failure_no_fake_artifacts_or_secret_leak(self):
        factory=Mock(side_effect=RuntimeError('Bearer SECRET account123'))
        report=run_daily_quant(root=self.root,now=NOW,calendar=FixtureCalendar(),provider_factory=factory)
        self.assertEqual(report['status'],'failed')
        self.assertFalse(archive_path(self.root,'research',DAY).exists())
        self.assertNotIn('SECRET',json.dumps(report))

    def test_options_failure_keeps_research(self):
        self.provider.underlying=Mock(side_effect=RuntimeError('SECRET'))
        with patch('modules.daily_quant.research_for_symbol',side_effect=small_research): report=self.run_pipeline()
        self.assertEqual(report['status'],'partial')
        self.assertTrue(archive_path(self.root,'research',DAY).exists())
        self.assertEqual(rebuild_manifest(self.root)['option_snapshots'],0)

    def test_retry_collects_missing_options_without_rewriting_research(self):
        original=self.provider.underlying;self.provider.underlying=Mock(side_effect=RuntimeError())
        with patch('modules.daily_quant.research_for_symbol',side_effect=small_research): self.run_pipeline()
        path=archive_path(self.root,'research',DAY);before=path.read_bytes()
        self.provider.underlying=original
        report=self.run_pipeline()
        self.assertEqual(report['research']['status'],'skipped_existing')
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual(rebuild_manifest(self.root)['option_snapshots'],2)

    def test_manifest_uses_files_not_cached_manifest(self):
        with patch('modules.daily_quant.research_for_symbol',side_effect=small_research): self.run_pipeline()
        (self.root/'archive_manifest.json').write_text('{"research_sessions":999}')
        manifest=rebuild_manifest(self.root)
        self.assertEqual(manifest['research_sessions'],1)
        self.assertEqual(manifest['option_snapshots'],2)
        self.assertEqual(manifest['earliest_date'],DAY)
        self.assertEqual(manifest['latest_options']['SPY']['date'],DAY)
        (self.root/'daily_quant'/'2026-09-21.json').write_text('invalid')
        self.assertEqual(len(scan_archive(self.root)['issues']),1)

    def test_archive_paths_and_deterministic_gzip(self):
        path=archive_path(self.root,'options',DAY,'SPY')
        self.assertEqual(path.relative_to(self.root).as_posix(),'options/2026-09-22/SPY.json.gz')
        write_artifact(path,dict(a=1,b=None));first=path.read_bytes()
        other=path.with_name('other.json.gz');write_artifact(other,dict(b=None,a=1))
        self.assertEqual(first,other.read_bytes())
        self.assertEqual(read_artifact(path),dict(a=1,b=None))
        with self.assertRaises(ValueError): archive_path(self.root,'options',DAY,'../escape')
        with self.assertRaises(ValueError): archive_path(self.root,'research','../../escape')

    def test_lock_prevents_concurrent_writes(self):
        self.root.mkdir();(self.root/'.daily-quant.lock').touch()
        self.assertEqual(self.run_pipeline()['reason'],'another_run_or_stale_lock')

    def test_corrupt_existing_session_fails_without_overwriting(self):
        path=archive_path(self.root,'research',DAY);path.parent.mkdir(parents=True)
        path.write_text('corrupted')
        report=self.run_pipeline()
        self.assertEqual(report['reason'],'existing_artifact_invalid')
        self.assertEqual(path.read_text(),'corrupted')

    def test_no_streamlit_dependency_in_runner(self):
        command=[sys.executable,'-c',"import sys;sys.path.insert(0,'.runtime-packages');import modules.daily_quant;assert 'streamlit' not in sys.modules"]
        result=subprocess.run(command,cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)


class OptionsArchiveTests(unittest.TestCase):
    def normalize(self,raw,**kwargs):
        return normalize_contract(raw,'SPY',kwargs.get('expiration',DAY),kwargs.get('kind','call'),NOW.isoformat(),DAY)
    def archive(self,provider=None,config=None):
        return build_options_snapshot(provider or FixtureProvider(),'SPY',DAY,config or load_config()['options'],'daily-quant-config-v1','a'*64)

    def test_normalization_and_derived_mid_dte(self):
        row=self.normalize(quote())
        self.assertEqual(row['rejection_reasons'],[]);self.assertEqual(row['quality_warnings'],[])
        self.assertAlmostEqual(row['mid'],1.1);self.assertEqual(row['dte'],0)
        self.assertEqual(row['iv'],.25);self.assertEqual(row['open_interest'],300)

    def test_missing_fields_remain_null(self):
        raw=quote(bid=None,ask=None,volume=None,openInterest=None)
        raw['optionDetails']['greeks']=None
        row=self.normalize(raw)
        for field in ('bid','ask','mid','volume','open_interest','delta','iv'): self.assertIsNone(row[field])
        self.assertIn('incomplete_bid_ask',row['quality_warnings'])

    def test_negative_and_crossed_bid_ask(self):
        for bid,ask,reason in ((-1,1,'bid_negative'),(1,-1,'ask_negative'),(2,1,'crossed_bid_ask')):
            row=self.normalize(quote(bid=bid,ask=ask))
            self.assertIn(reason,row['rejection_reasons']);self.assertIsNone(row['mid'])

    def test_zero_bid_valid_and_no_attractiveness_filter(self):
        provider=FixtureProvider();provider.chain=lambda s,e:dict(calls=[quote(s,expiration=e,bid=0,ask=.01,volume=0,openInterest=0)],puts=[])
        snap=self.archive(provider)
        self.assertEqual(len(snap['valid_contracts']),2)
        self.assertEqual(snap['valid_contracts'][0]['mid'],.005)

    def test_invalid_strike_is_retained_rejected(self):
        provider=FixtureProvider()
        raw=quote();raw['optionDetails']=None
        provider.chain=lambda s,e:dict(calls=[raw],puts=[])
        snap=self.archive(provider)
        self.assertEqual(len(snap['rejected_contracts']),2)
        self.assertIn('invalid_strike',snap['rejected_contracts'][0]['rejection_reasons'])

    def test_duplicate_contracts_all_rejected(self):
        provider=FixtureProvider();provider.chain=lambda s,e:dict(calls=[quote(s,expiration=e),quote(s,expiration=e)],puts=[])
        snap=self.archive(provider)
        self.assertEqual(len(snap['valid_contracts']),0)
        self.assertEqual(snap['rejection_counts']['duplicate_contract_identifier'],4)

    def test_dte_and_strike_universe_boundaries(self):
        provider=FixtureProvider()
        provider.chain=lambda s,e:dict(calls=[quote(s,strike=k,expiration=e) for k in (89,90,100,110,111)],puts=[])
        snap=self.archive(provider)
        self.assertEqual(snap['requested_expirations'],[DAY,'2026-10-02'])
        self.assertEqual(snap['excluded_expiration_count'],1)
        self.assertEqual(snap['excluded_strike_count'],4)
        self.assertEqual(len(snap['valid_contracts']),6)
        self.assertEqual({r['dte'] for r in snap['valid_contracts']},{0,10})

    def test_contract_identity_checks(self):
        cases=[(quote('QQQ'),'contract_underlying_mismatch'),(quote(side='P'),'contract_type_mismatch'),
               (quote(expiration='2026-09-23'),'contract_expiration_mismatch')]
        for raw,reason in cases: self.assertIn(reason,self.normalize(raw)['rejection_reasons'])

    def test_invalid_nonfinite_greeks_and_iv(self):
        raw=quote();raw['optionDetails']['greeks'].update(delta='nan',impliedVolatility='Infinity')
        row=self.normalize(raw)
        self.assertIn('delta_nonfinite_or_nonnumeric',row['rejection_reasons'])
        self.assertIsNone(row['delta']);self.assertIsNone(row['iv'])

    def test_stale_missing_future_and_naive_timestamps(self):
        row=self.normalize(quote(bidTimestamp='2026-09-21T20:00:00Z',askTimestamp=None))
        self.assertIn('bid_timestamp_different_session',row['quality_warnings'])
        self.assertIn('ask_timestamp_missing',row['quality_warnings'])
        row=self.normalize(quote(bidTimestamp='2026-09-23T20:00:00Z',askTimestamp='2026-09-22T16:00:00'))
        self.assertIn('bid_timestamp_in_future',row['rejection_reasons'])
        self.assertIn('ask_timestamp_invalid',row['rejection_reasons'])

    def test_expired_contract_and_bad_expiration(self):
        self.assertIn('expired_before_snapshot',self.normalize(quote(),expiration='2026-09-21')['rejection_reasons'])
        self.assertIn('invalid_expiration',self.normalize(quote(),expiration='bad')['rejection_reasons'])

    def test_partial_expiration_failure_preserves_other_data(self):
        provider=FixtureProvider();original=provider.chain
        def chain(s,e):
            if e==DAY: raise ValueError('SECRET_PAYLOAD')
            return original(s,e)
        provider.chain=chain;snap=self.archive(provider)
        self.assertEqual(snap['status'],'partial');self.assertEqual(len(snap['valid_contracts']),2)
        self.assertNotIn('SECRET',json.dumps(snap))

    def test_unknown_fields_and_malformed_values_do_not_leak_secrets(self):
        raw=quote(Authorization='Bearer SECRET',bid='SECRET')
        raw['instrument']['symbol']='SECRET';row=self.normalize(raw)
        self.assertNotIn('SECRET',json.dumps(row));self.assertIn('bid_nonfinite_or_nonnumeric',row['rejection_reasons'])

    def test_underlying_validation(self):
        for value in (0,-1,None,float('inf')):
            provider=FixtureProvider();provider.underlying=lambda s:dict(instrument=dict(symbol=s,type='EQUITY'),outcome='SUCCESS',last=value)
            with self.assertRaises(ValueError): self.archive(provider)

    def test_no_expirations_is_explicit_empty_archive(self):
        provider=FixtureProvider();provider.expirations=lambda s:[]
        snap=self.archive(provider)
        self.assertEqual(snap['status'],'empty');self.assertEqual(snap['valid_contracts'],[])
        self.assertTrue(any('No available expirations' in w for w in snap['warnings']))

    def test_collection_date_cannot_be_backdated(self):
        with self.assertRaises(ValueError):
            build_options_snapshot(FixtureProvider(),'SPY','2026-09-21',load_config()['options'],'v1','hash')

    def test_optional_provider_fields_and_provenance(self):
        snap=self.archive()
        self.assertEqual(snap['quote_timing'],'last_available_not_guaranteed_close')
        self.assertIn('derived',snap['provenance']['mid'])
        self.assertIn('Public',snap['provenance']['provider_mid'])
        self.assertNotIn('historical_analogs',snap)
        self.assertEqual(snap['missing_field_counts']['delta'],0)


class DailyProviderTests(unittest.TestCase):
    def test_cli_failure_output_never_contains_exception_payload(self):
        from scripts.run_daily_quant import main
        output=io.StringIO()
        with patch('scripts.run_daily_quant.run_daily_quant',side_effect=RuntimeError('SECRET_TOKEN')),patch('sys.stdout',output):
            code=main([])
        self.assertEqual(code,1)
        self.assertNotIn('SECRET_TOKEN',output.getvalue())
        self.assertEqual(json.loads(output.getvalue())['status'],'failed')

    def test_workflow_timing_and_no_force(self):
        workflow=(Path(__file__).resolve().parents[1]/'.github/workflows/daily-quant.yml').read_text()
        self.assertIn("23 22 * * 1-5",workflow)
        self.assertIn('cancel-in-progress: false',workflow)
        self.assertIn('secrets.PUBLIC_API_SECRET',workflow)
        self.assertIn('if [ -z "$PUBLIC_API_SECRET" ]; then',workflow)
        self.assertIn('PUBLIC_API_SECRET is unavailable to this job',workflow)
        self.assertNotIn('--force-rebuild',workflow)
        self.assertIn('if: always()',workflow)

    def test_environment_missing_and_auth_error_are_safe(self):
        with patch.dict(os.environ,{},clear=True),self.assertRaisesRegex(ProviderUnavailable,'not configured'):
            DailyPublicProvider.from_environment()
        with patch.dict(os.environ,{'PUBLIC_API_SECRET':'VERY_SECRET'}),patch('public_api_sdk.PublicApiClient',side_effect=Exception('VERY_SECRET')):
            with self.assertRaises(ProviderUnavailable) as caught: DailyPublicProvider.from_environment()
        self.assertNotIn('VERY_SECRET',str(caught.exception))

    def test_read_only_transport_paths_no_account_data_export(self):
        client=Mock();provider=DailyPublicProvider(client,'PRIVATE_ACCOUNT')
        client.api_client.post.return_value=dict(baseSymbol='SPY',calls=[{'malformed':True}],puts=[])
        result=provider.chain('SPY',DAY)
        self.assertEqual(result['calls'],[{'malformed':True}])
        args=client.api_client.post.call_args
        self.assertTrue(args.args[0].endswith('/option-chain'))
        self.assertEqual(args.kwargs['json_data']['expirationDate'],DAY)
        self.assertNotIn('PRIVATE_ACCOUNT',json.dumps(result))

    def test_bad_envelope_failure_does_not_expose_response(self):
        client=Mock();provider=DailyPublicProvider(client,'PRIVATE_ACCOUNT')
        client.api_client.post.return_value={'error':'SECRET'}
        with self.assertRaises(ProviderUnavailable) as caught: provider.chain('SPY',DAY)
        self.assertNotIn('SECRET',str(caught.exception))


if __name__=='__main__': unittest.main()
