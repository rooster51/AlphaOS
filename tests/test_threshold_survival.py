import io
import json
import unittest
import numpy as np
import pandas as pd
from modules.threshold_survival import (normalize_threshold,threshold_research,distance_grid,horizon_matrix,
    wilson_interval,extract_short_strikes,selected_trade_threshold,export_threshold_observations)
from modules.market_outcomes import HORIZONS
from modules.historical_analogs import analog_research
from modules.market_state_research import build_research_dataset


def sample(returns=(-.02,-.01,0,.02),lows=(-.03,-.01,-.02,.01),highs=(0,.01,.02,.03),positions=None,target_index=30):
    dates=pd.Series(pd.bdate_range('2020-01-02',periods=40))
    positions=list(range(len(returns))) if positions is None else positions
    frame=pd.DataFrame(dict(date=dates.iloc[positions].to_numpy(),symbol='QQQ',close=400.))
    for h in HORIZONS:
        frame[f'future_return_{h}s']=returns
        frame[f'future_low_excursion_{h}s']=lows
        frame[f'future_high_excursion_{h}s']=highs
        frame[f'outcome_known_by_target_{h}s']=True
    return dict(analogs=frame,session_dates=dates,target=pd.Series(dict(date=dates.iloc[target_index],symbol='QQQ',close=770.)),
        config={'horizon':1},target_index=target_index,target_mode='LATEST COMPLETED SESSION')


def trade(legs):
    return dict(symbol='QQQ',spot=999.,credit=.18,shares=0,fees=0,source='Manual entry',expiration='2030-01-01',
        legs=[dict(type=kind,strike=strike,qty=qty) for kind,strike,qty in legs])


class ThresholdSurvivalTests(unittest.TestCase):
    def test_normalization_price(self):
        r=threshold_research(sample(),threshold_price=760)
        self.assertAlmostEqual(r['config']['threshold_return'],760/770-1)
        self.assertAlmostEqual(r['observations'].equivalent_historical_threshold.iloc[0],400*760/770)

    def test_percentage_price_equivalence(self):
        a=threshold_research(sample(),threshold_price=760)
        b=threshold_research(sample(),threshold_return=760/770-1)
        self.assertEqual(a['summary'],b['summary'])
        self.assertAlmostEqual(b['config']['threshold_price'],760)

    def test_put_terminal_counts_equality_and_denominator(self):
        r=threshold_research(sample(),threshold_return=-.01)
        s=r['summary']
        self.assertEqual((s['terminal_valid_n'],s['survived_n'],s['terminal_breached_n'],s['equality_n']),(4,2,1,1))
        self.assertEqual(s['survival_frequency'],.5)
        self.assertEqual(s['terminal_breach_frequency'],.25)

    def test_call_terminal_counts(self):
        r=threshold_research(sample(returns=(.02,.01,0,-.02),highs=(.03,.01,.02,-.01)),mode='call',threshold_return=.01)
        self.assertEqual((r['summary']['survived_n'],r['summary']['terminal_breached_n'],r['summary']['equality_n']),(2,1,1))

    def test_put_touch_includes_equality(self):
        s=threshold_research(sample(),threshold_return=-.01)['summary']
        self.assertEqual((s['touch_n'],s['no_touch_n'],s['touch_valid_n']),(3,1,4))
        self.assertEqual(s['touch_frequency'],.75)

    def test_call_touch_includes_equality(self):
        s=threshold_research(sample(returns=(.02,.01,0,-.02),highs=(.03,.01,.02,-.01)),mode='call',threshold_return=.01)['summary']
        self.assertEqual((s['touch_n'],s['no_touch_n']),(3,1))

    def test_breach_then_recovery_both_styles(self):
        put=threshold_research(sample(),threshold_return=-.01)['summary']
        call=threshold_research(sample(returns=(.02,.01,0,-.02),highs=(.03,.01,.02,-.01)),mode='call',threshold_return=.01)['summary']
        for s in (put,call):
            self.assertEqual(s['recovery_n'],1)
            self.assertEqual(s['recovery_frequency_all'],.25)
            self.assertAlmostEqual(s['recovery_frequency_touched'],1/3)

    def test_representation_equality_vs_distinct_return(self):
        r=threshold_research(sample(returns=(-.01,-.01+1e-14,-.01+1e-8,-.01-1e-8)),threshold_price=770*.99)
        self.assertEqual(r['summary']['equality_n'],2)
        self.assertEqual(r['summary']['survived_n'],1)
        self.assertEqual(r['summary']['terminal_breached_n'],1)

    def test_directional_acknowledgement(self):
        for mode,distance in (('put',.01),('call',-.01)):
            with self.assertRaises(ValueError):
                normalize_threshold(770,mode,threshold_return=distance)
            self.assertTrue(normalize_threshold(770,mode,threshold_return=distance,allow_opposite=True)['opposite_side'])
        self.assertFalse(normalize_threshold(770,'put',threshold_price=770)['opposite_side'])

    def test_invalid_thresholds(self):
        for kwargs in (dict(target_spot=0,threshold_price=1),dict(target_spot=770,threshold_price=-1),
                       dict(target_spot=770,threshold_return=-1),dict(target_spot=770,threshold_return=float('nan')),
                       dict(target_spot=770,threshold_price=760,threshold_return=-.01),dict(target_spot=770)):
            with self.assertRaises(ValueError):
                normalize_threshold(mode='put',**kwargs)

    def test_distance_grid_and_horizon_matrices(self):
        for mode,sign in (('put',-1),('call',1)):
            grid=distance_grid(sample(),mode)
            self.assertEqual(len(grid),30)
            self.assertTrue(((grid.threshold_return*sign)>0).all())
            for field in ('survival_frequency','touch_frequency'):
                matrix=horizon_matrix(grid,field)
                self.assertEqual(matrix.shape,(6,5))
                expected=threshold_research(sample(),mode,3,threshold_return=.01*sign)['summary'][field]
                self.assertEqual(matrix.loc[.01*sign,3],expected)

    def test_custom_grid_and_validation(self):
        grid=distance_grid(sample(),distances=[.0075,.0075,.0175],horizons=[3])
        self.assertEqual(len(grid),2)
        for distances in ([],[0],[-.1],[1],[np.inf],list(np.arange(1,32)/100)):
            with self.assertRaises(ValueError):
                distance_grid(sample(),distances=distances)

    def test_wilson_known_values(self):
        lo,hi=wilson_interval(50,100)
        self.assertAlmostEqual(lo,.4038315303659956)
        self.assertAlmostEqual(hi,.5961684696340044)
        self.assertEqual(wilson_interval(0,0),(None,None))
        lo,hi=wilson_interval(0,10)
        self.assertAlmostEqual(lo,0)
        self.assertAlmostEqual(hi,.2775327998628892)
        lo,hi=wilson_interval(10,10)
        self.assertAlmostEqual(lo,.7224672001371107)
        self.assertAlmostEqual(hi,1)

    def test_empty_sample_and_grid(self):
        a=sample();a['analogs']=a['analogs'].iloc[:0]
        r=threshold_research(a,threshold_return=-.01)
        self.assertEqual(r['summary']['terminal_valid_n'],0)
        self.assertIsNone(r['summary']['survival_frequency'])
        self.assertIsNone(r['summary']['touch_wilson_low'])
        self.assertTrue(distance_grid(a).survival_frequency.isna().all())

    def test_missing_outcomes_and_recovery_denominators(self):
        a=sample(returns=(0,np.nan,0,-.02),lows=(np.nan,-.03,-.03,-.03))
        s=threshold_research(a,threshold_return=-.01)['summary']
        self.assertEqual((s['terminal_valid_n'],s['touch_valid_n'],s['paired_valid_n']),(3,3,2))
        self.assertEqual((s['recovery_n'],s['paired_touch_n']),(1,2))
        self.assertEqual(s['recovery_frequency_all'],.5)
        self.assertEqual(s['recovery_frequency_touched'],.5)

    def test_missing_excursion_column_never_becomes_no_touch(self):
        a=sample();a['analogs']=a['analogs'].drop(columns='future_low_excursion_3s')
        s=threshold_research(a,threshold_return=-.01)['summary']
        self.assertEqual(s['touch_valid_n'],0)
        self.assertIsNone(s['no_touch_frequency'])

    def test_nonoverlap_uses_full_session_positions_and_boundary(self):
        a=sample(returns=[.01]*8,lows=[-.02]*8,highs=[.02]*8,positions=[0,1,2,3,5,6,7,10])
        a['analogs']=a['analogs'].iloc[::-1].copy()
        r=threshold_research(a,horizon=3,threshold_return=-.01)
        self.assertEqual(r['non_overlapping_observations'].session_position.tolist(),[0,3,6,10])
        self.assertEqual(r['non_overlapping_summary']['paired_valid_n'],4)

    def test_nonoverlap_skips_missing_pairs(self):
        a=sample(returns=[np.nan,.01,.01,.01],positions=[0,1,3,4])
        r=threshold_research(a,horizon=3,threshold_return=-.01)
        self.assertEqual(r['non_overlapping_observations'].session_position.tolist(),[1,4])

    def test_asof_maturity_rechecked_despite_true_flags(self):
        a=sample(positions=[0,5,8,10],target_index=10)
        r=threshold_research(a,horizon=3,threshold_return=-.01)
        self.assertEqual(r['summary']['terminal_valid_n'],2)
        self.assertTrue(r['observations'].future_return_3s.iloc[2:].isna().all())
        self.assertEqual(r['summary']['as_of_eligible_n'],2)
        self.assertTrue(pd.isna(r['observations'].future_return_10s.iloc[1]))

    def test_post_target_ohlc_mutation_invariance(self):
        n=260
        close=100+np.arange(n)*.02+np.sin(np.arange(n)/5)
        raw=pd.DataFrame(dict(date=pd.bdate_range('2020-01-02',periods=n),symbol='QQQ',open=close,high=close+1,low=close-1,close=close))
        later=raw.copy();later.loc[221:,['open','high','low','close']]*=10
        results=[]
        for data in (raw,later):
            ds=build_research_dataset(data,'2030-01-01')
            analogs=analog_research(ds['features'],ds['outcomes'],target_date=raw.date.iloc[220],method='nearest',horizon=1)
            results.append(threshold_research(analogs,horizon=10,threshold_price=100))
        self.assertEqual(results[0]['config'],results[1]['config'])
        self.assertEqual(results[0]['summary'],results[1]['summary'])
        pd.testing.assert_frame_equal(results[0]['observations'],results[1]['observations'])

    def test_pcs_short_strike_extraction(self):
        t=trade([('Put',760,-1),('Put',759,1)])
        self.assertEqual(extract_short_strikes(t,'QQQ'),[dict(leg_index=0,type='Put',mode='put',strike=760.,contracts=1.)])
        chosen=selected_trade_threshold(sample(),t,0)
        r=threshold_research(sample(),**chosen)
        self.assertAlmostEqual(r['config']['threshold_return'],760/770-1)  # ignores trade's stale 999 spot

    def test_ccs_short_strike_extraction(self):
        t=trade([('Call',780,-1),('Call',781,1)])
        self.assertEqual(selected_trade_threshold(sample(),t,0),dict(mode='call',threshold_price=780.))

    def test_iron_condor_separate_sides(self):
        t=trade([('Put',760,-1),('Put',759,1),('Call',780,-1),('Call',781,1)])
        choices=extract_short_strikes(t,'QQQ')
        self.assertEqual([c['mode'] for c in choices],['put','call'])
        self.assertEqual([c['strike'] for c in choices],[760,780])

    def test_historical_saved_trade_shortcut_blocked(self):
        a=sample();a['target_mode']='HISTORICAL TARGET DATE'
        with self.assertRaises(ValueError):
            selected_trade_threshold(a,trade([('Put',760,-1)]),0)

    def test_malformed_or_mismatched_trade(self):
        for t in (None,{},trade([('Put',-1,-1)]),trade([('Put',760,0)]),{**trade([('Put',760,-1)]),'symbol':'SPY'}):
            with self.subTest(trade=t),self.assertRaises(ValueError):
                extract_short_strikes(t,'QQQ')
        self.assertEqual(extract_short_strikes(trade([('Put',760,1)]),'QQQ'),[])

    def test_csv_contains_normalization_and_status(self):
        r=threshold_research(sample(),threshold_return=-.01)
        frame=pd.read_csv(io.StringIO(export_threshold_observations(r)))
        self.assertIn('equivalent_historical_threshold',frame)
        self.assertEqual(frame.terminal_status.tolist(),['breached','equal','survived','survived'])
        self.assertEqual(json.loads(frame.threshold_research_metadata.iloc[0])['config']['mode'],'put')


if __name__=='__main__':
    unittest.main()
