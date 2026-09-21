import io
import json
import unittest
import numpy as np
import pandas as pd

from modules.historical_analogs import (NUMERIC_FEATURES,DEFAULT_TOLERANCES,match_analogs,
    analog_research,sensitivity_analysis,sample_warning,export_analogs,summarize_outcomes)
from modules.market_outcomes import HORIZONS
from modules.market_state_research import build_research_dataset


def frames(n=40):
    features=pd.DataFrame(dict(date=pd.bdate_range('2020-01-02',periods=n),symbol='SPY',close=100.,
        return_5d=0.,rsi_14=50.,distance_ema_21_atr=0.,realized_vol_20d=.2,range_position_20=.5,ema_structure='mixed'))
    outcomes=features[['date','symbol']].copy()
    for h in HORIZONS:
        outcomes[f'future_return_{h}s']=.01
        outcomes[f'future_high_excursion_{h}s']=.02
        outcomes[f'future_low_excursion_{h}s']=-.02
        outcomes.loc[n-h:,[f'future_{kind}_{h}s' for kind in ('return','high_excursion','low_excursion')]]=np.nan
    return features,outcomes


class HistoricalAnalogTests(unittest.TestCase):
    def test_tolerance_matching(self):
        f,o=frames()
        f.loc[0,'return_5d']=.03
        f.loc[1,'rsi_14']=70
        r=analog_research(f,o,horizon=1)
        self.assertEqual(len(r['analogs']),37)
        self.assertNotIn(f.date.iloc[0],r['matches'].date.tolist())
        self.assertNotIn(f.date.iloc[1],r['matches'].date.tolist())
        self.assertIn('difference_return_5d',r['matches'])

    def test_exact_structure_default_and_opt_out(self):
        f,_=frames()
        f.loc[0,'ema_structure']='bullish'
        self.assertEqual(len(match_analogs(f,horizon=1)['matches']),38)
        self.assertEqual(len(match_analogs(f,horizon=1,exact_structure=False)['matches']),39)

    def test_inclusive_tolerance_boundaries(self):
        f,_=frames(5)
        f.loc[0,'return_5d']=.02
        f.loc[1,'return_5d']=-.02
        f.loc[2,'return_5d']=.020001
        r=match_analogs(f,horizon=1)
        self.assertEqual(r['matches'].date.tolist(),[f.date.iloc[i] for i in (0,1,3)])

    def test_standardization_population_sd_and_order(self):
        f,_=frames(31)
        f['return_5d']=list(np.arange(30,dtype=float))+[14.4]
        r=match_analogs(f,method='nearest',horizon=1,numerical_features=['return_5d'],neighbors=25)
        self.assertEqual(len(r['matches']),25)
        self.assertEqual(r['scaler']['mean'].iloc[0],14.5)
        scale=np.sqrt(sum((i-14.5)**2 for i in range(30))/30)
        self.assertAlmostEqual(r['scaler'].scale.iloc[0],scale)
        self.assertEqual(r['matches'].date.iloc[0],f.date.iloc[14])
        self.assertAlmostEqual(r['matches'].similarity_distance.iloc[0],.4/scale)
        self.assertTrue(r['matches'].similarity_distance.is_monotonic_increasing)

    def test_neighbor_n_limits(self):
        f,_=frames(230)
        for n in (25,50,100,200):
            r=match_analogs(f,method='nearest',neighbors=n,horizon=1)
            self.assertEqual(len(r['matches']),n)
        small,_=frames(6)
        self.assertEqual(len(match_analogs(small,method='nearest',neighbors=25,horizon=1)['matches']),5)

    def test_zero_variance_and_ties_deterministic(self):
        f,_=frames(30)
        r=match_analogs(f,method='nearest',neighbors=25,horizon=1)
        self.assertTrue((r['matches'].similarity_distance==0).all())
        self.assertTrue(r['matches'].date.is_monotonic_increasing)
        self.assertTrue(r['notes'])
        self.assertFalse(r['scaler'].used.any())

    def test_warning_boundaries(self):
        for n,text in ((0,'Very small'),(29,'Very small'),(30,'Small'),(99,'Small'),(100,'Moderate'),(249,'Moderate'),(250,'Larger')):
            self.assertTrue(sample_warning(n).startswith(text))

    def test_funnel_and_independent_counts(self):
        f,_=frames(8)
        f.loc[0,'ema_structure']='bullish'
        f.loc[[0,1],'return_5d']=.03
        f.loc[2,'rsi_14']=70
        r=match_analogs(f,horizon=1)
        self.assertEqual(r['funnel'].remaining.tolist(),[7,7,7,6,5,4,4,4,4])
        self.assertEqual(r['independent_passes'].set_index('feature').loc['return_5d','passed'],5)

    def test_empty_sample_no_automatic_widening(self):
        f,o=frames(15)
        f.loc[:13,'rsi_14']=90
        r=analog_research(f,o,horizon=1)
        self.assertTrue(r['analogs'].empty)
        self.assertTrue((r['summary'].n==0).all())
        self.assertTrue(r['summary'].median_return.isna().all())
        self.assertEqual(r['config']['tolerances'],DEFAULT_TOLERANCES)

    def test_summary_frequencies_and_percentiles(self):
        _,o=frames(5)
        for h in HORIZONS:
            o[f'future_return_{h}s']=[-.1,0,.1,.2,np.nan]
            o[f'future_high_excursion_{h}s']=[-.02,.02,.04,.08,np.nan]
            o[f'future_low_excursion_{h}s']=[-.2,-.1,0,.1,np.nan]
        row=summarize_outcomes(o).iloc[0]
        self.assertEqual(row['n'],4)
        self.assertEqual(row.positive_frequency,.5)
        self.assertEqual(row.negative_frequency,.25)
        self.assertAlmostEqual(row.mean_return,.05)
        self.assertAlmostEqual(row.median_return,.05)
        self.assertAlmostEqual(row.p10_return,-.07)
        self.assertAlmostEqual(row.p25_return,-.025)
        self.assertAlmostEqual(row.p75_return,.125)
        self.assertAlmostEqual(row.p90_return,.17)
        self.assertAlmostEqual(row.median_high_excursion,.03)
        self.assertAlmostEqual(row.median_low_excursion,-.05)
        self.assertAlmostEqual(row.p10_low_excursion,-.17)
        self.assertAlmostEqual(row.p90_high_excursion,.068)

    def test_latest_and_historical_strict_prior(self):
        f,o=frames()
        for target in (None,f.date.iloc[20]):
            r=analog_research(f,o,target_date=target,horizon=3)
            self.assertTrue((r['matches'].date<r['target'].date).all())
            self.assertNotIn(r['target'].date,r['matches'].date.tolist())
            self.assertEqual(r['target'].date,f.date.iloc[-1] if target is None else target)

    def test_asof_selected_horizon_maturity(self):
        f,o=frames(40)
        for h in HORIZONS:
            r=analog_research(f,o,target_date=f.date.iloc[20],horizon=h)
            self.assertEqual(r['matches'].date.max(),f.date.iloc[20-h])
            self.assertEqual(len(r['matches']),21-h)

    def test_each_displayed_horizon_masked_and_equal_target_is_known(self):
        f,o=frames(40)
        r=analog_research(f,o,target_date=f.date.iloc[20],horizon=1)
        a=r['analogs'].set_index('date')
        self.assertFalse(a.loc[f.date.iloc[19],'outcome_known_by_target_10s'])
        self.assertTrue(pd.isna(a.loc[f.date.iloc[19],'future_return_10s']))
        self.assertTrue(a.loc[f.date.iloc[10],'outcome_known_by_target_10s'])
        self.assertAlmostEqual(a.loc[f.date.iloc[10],'future_return_10s'],.01)
        self.assertEqual(r['summary'].set_index('horizon').loc[10,'n'],11)

    def test_post_target_features_cannot_change_distances_or_scaler(self):
        f,_=frames(80)
        f['return_5d']=np.arange(80)/10000
        changed=f.copy()
        changed.loc[41:,list(NUMERIC_FEATURES)]=1e6
        for method in ('tolerance','nearest'):
            a=match_analogs(f,target_date=f.date.iloc[40],method=method)
            b=match_analogs(changed,target_date=f.date.iloc[40],method=method)
            pd.testing.assert_series_equal(a['target'],b['target'])
            pd.testing.assert_frame_equal(a['matches'],b['matches'])
            pd.testing.assert_frame_equal(a['scaler'],b['scaler'])

    def test_after_target_raw_prices_cannot_leak(self):
        n=280
        close=100+np.arange(n)*.03+np.sin(np.arange(n)/5)
        raw=pd.DataFrame(dict(date=pd.bdate_range('2020-01-02',periods=n),symbol='QQQ',open=close,close=close,high=close+1,low=close-1))
        changed=raw.copy()
        changed.loc[221:,['open','high','low','close']]*=5
        a=build_research_dataset(raw,'2030-01-01')
        b=build_research_dataset(changed,'2030-01-01')
        for method in ('tolerance','nearest'):
            r1=analog_research(a['features'],a['outcomes'],target_date=raw.date.iloc[220],method=method)
            r2=analog_research(b['features'],b['outcomes'],target_date=raw.date.iloc[220],method=method)
            pd.testing.assert_series_equal(r1['target'],r2['target'])
            for key in ('matches','analogs','scaler','summary'):
                pd.testing.assert_frame_equal(r1[key],r2[key])

    def test_labels_never_change_membership_or_distance(self):
        f,o=frames(140)
        f['return_5d']=np.sin(np.arange(140))*.01
        changed=o.copy()
        changed.loc[:,changed.columns.str.startswith('future_')]=999.
        changed.iloc[0,2:]=np.nan
        for method in ('tolerance','nearest'):
            a=analog_research(f,o,target_date=f.date.iloc[120],method=method)
            b=analog_research(f,changed,target_date=f.date.iloc[120],method=method)
            pd.testing.assert_frame_equal(a['matches'],b['matches'])
            pd.testing.assert_frame_equal(a['scaler'],b['scaler'])

    def test_future_features_forbidden(self):
        f,o=frames()
        f['future_return_1s']=o.future_return_1s
        with self.assertRaises(ValueError):
            match_analogs(f,numerical_features=['future_return_1s'])
        r=match_analogs(f)
        self.assertNotIn('future_return_1s',r['matches'])

    def test_scaler_pool_before_category_filter(self):
        f,_=frames(5)
        f.return_5d=[0,1,2,3,0]
        f.loc[0,'ema_structure']='bullish'
        r=match_analogs(f,method='nearest',horizon=1,numerical_features=['return_5d'])
        self.assertEqual(r['scaler'].fit_n.iloc[0],4)
        self.assertEqual(r['scaler']['mean'].iloc[0],1.5)
        self.assertNotIn(f.date.iloc[0],r['matches'].date.tolist())

    def test_sensitivity_explicit_presets_and_nested_samples(self):
        f,o=frames(10)
        f.loc[:8,'return_5d']=np.arange(9)/250
        s=sensitivity_analysis(f,o,horizon=1)
        counts=s.groupby('preset').sample_n.first()
        self.assertEqual(counts['TIGHT'],4)
        self.assertEqual(counts['DEFAULT'],6)
        self.assertEqual(counts['WIDE'],8)
        self.assertEqual(len(s),15)
        self.assertEqual(set(s.multiplier),{.75,1.,1.5})

    def test_csv_metadata_and_masked_outcomes(self):
        f,o=frames(40)
        result=analog_research(f,o,target_date=f.date.iloc[20],horizon=1,method='nearest')
        data=pd.read_csv(io.StringIO(export_analogs(result,{'provider':'test'})))
        meta=json.loads(data.research_metadata_json.iloc[0])
        self.assertEqual(meta['config']['target_date'],str(f.date.iloc[20].date()))
        self.assertEqual(meta['source']['provider'],'test')
        self.assertIn('similarity_distance',data)
        self.assertTrue(data.future_return_10s.iloc[-1:].isna().all())

    def test_missing_candidate_and_target_features(self):
        f,_=frames()
        f.loc[0,'rsi_14']=np.nan
        r=match_analogs(f,horizon=1)
        self.assertEqual(r['audit']['missing_feature_dates'],1)
        f.loc[len(f)-1,'ema_structure']=pd.NA
        with self.assertRaises(ValueError):
            match_analogs(f)
        f.loc[len(f)-1,'rsi_14']=np.nan
        with self.assertRaises(ValueError):
            match_analogs(f,exact_structure=False)

    def test_missing_outcome_does_not_drop_match(self):
        f,o=frames()
        o=o.iloc[1:].copy()
        r=analog_research(f,o,horizon=1)
        self.assertEqual(len(r['matches']),39)
        self.assertEqual(r['summary'].set_index('horizon').loc[1,'n'],38)

    def test_bad_configuration_and_dates_rejected(self):
        f,o=frames()
        for config in (dict(target_date='1900-01-01'),dict(horizon=4),dict(neighbors=2),dict(method='ML'),
                       dict(tolerances={'return_5d':-1}),dict(tolerances={'return_5d':np.inf})):
            with self.subTest(config=config),self.assertRaises(ValueError):
                match_analogs(f,**config)
        for changed in (pd.concat([f,f.iloc[:1]]),f.iloc[::-1]):
            with self.assertRaises(ValueError):
                match_analogs(changed)
        o['symbol']='QQQ'
        with self.assertRaises(ValueError):
            analog_research(f,o)


if __name__=='__main__':
    unittest.main()
