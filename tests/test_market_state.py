import io
import json
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd

from modules.market_state import market_state_features, validate_ohlc
from modules.market_outcomes import forward_outcomes, HORIZONS
from modules.market_state_research import build_research_dataset, export_csv, load_market_state

CUTOFF = '2030-01-01'


def bars(closes, symbol='SPY'):
    close=np.asarray(closes,dtype=float)
    return pd.DataFrame(dict(date=pd.bdate_range('2020-01-02',periods=len(close)),symbol=symbol,
        open=close,high=close+1,low=close-1,close=close))


class MarketStateTests(unittest.TestCase):
    def features(self, data):
        return market_state_features(data,CUTOFF)

    def test_returns_all_horizons(self):
        f=self.features(bars(np.arange(100,125)))
        for h in (1,2,3,5,10,20):
            self.assertTrue(f[f'return_{h}d'].iloc[:h].isna().all())
            self.assertAlmostEqual(f[f'return_{h}d'].iloc[-1],124/(124-h)-1)

    def test_ema_seed_and_warmup(self):
        for n in (9,21,50,200):
            f=self.features(bars([100]*(n-1)+[110]))
            self.assertTrue(f[f'ema_{n}'].iloc[:n-1].isna().all())
            self.assertAlmostEqual(f[f'ema_{n}'].iloc[-1],100+20/(n+1))

    def test_rsi_wilder_hand_values(self):
        # Seven +2 changes and seven -1 changes: seed gains=1, losses=0.5.
        prices=100+np.cumsum([0]+[2]*7+[-1]*7+[1])
        f=self.features(bars(prices))
        self.assertTrue(f.rsi_14.iloc[:14].isna().all())
        self.assertAlmostEqual(f.rsi_14.iloc[14],100-100/3)
        self.assertAlmostEqual(f.rsi_14.iloc[15],100-100/(1+28/13))

    def test_rsi_edge_cases(self):
        for prices,expected in ((range(100,120),100),(range(120,100,-1),0),([100]*20,50)):
            self.assertEqual(self.features(bars(prices)).rsi_14.iloc[-1],expected)

    def test_true_range_gaps(self):
        f=self.features(bars([100,105,98]))
        self.assertEqual(f.true_range.tolist(),[2,6,8])

    def test_atr_simple_mean_and_distance(self):
        f=self.features(bars([100]*50+[105]))
        self.assertTrue(f.atr_14.iloc[:13].isna().all())
        self.assertEqual(f.atr_14.iloc[13],2)
        self.assertAlmostEqual(f.atr_14.iloc[-1],32/14)
        self.assertAlmostEqual(f.atr_pct.iloc[-1],32/14/105)
        for n in (21,50):
            ema=100+10/(n+1)
            self.assertAlmostEqual(f[f'distance_ema_{n}_pct'].iloc[-1],105/ema-1)
            self.assertAlmostEqual(f[f'distance_ema_{n}_atr'].iloc[-1],(105-ema)/(32/14))

    def test_realized_volatility_sample_log_returns(self):
        logs=np.array([.01,-.02,.03,-.01,.02]*13)
        f=self.features(bars(100*np.exp(np.r_[0,logs.cumsum()])))
        for n in (10,20,60):
            expected=np.sqrt(sum((x-np.mean(logs[-n:]))**2 for x in logs[-n:])/(n-1))*np.sqrt(252)
            self.assertAlmostEqual(f[f'realized_vol_{n}d'].iloc[-1],expected)
            self.assertTrue(f[f'realized_vol_{n}d'].iloc[:n].isna().all())

    def test_rolling_range_and_location(self):
        f=self.features(bars(range(100,125)))
        self.assertTrue(f.high_20.iloc[:19].isna().all())
        self.assertEqual(f.high_20.iloc[-1],125)
        self.assertEqual(f.low_20.iloc[-1],104)
        self.assertAlmostEqual(f.range_position_20.iloc[-1],20/21)
        self.assertAlmostEqual(f.distance_high_20_pct.iloc[-1],124/125-1)
        self.assertAlmostEqual(f.distance_low_20_pct.iloc[-1],124/104-1)

    def test_zero_range_and_zero_atr(self):
        t=bars([100]*60)
        t['high']=t['low']=100
        f=self.features(t)
        self.assertTrue(pd.isna(f.range_position_20.iloc[-1]))
        self.assertTrue(pd.isna(f.distance_ema_21_atr.iloc[-1]))

    def test_structure_ordering_and_equality(self):
        for prices,expected in ((range(100,160),'bullish'),(range(160,100,-1),'bearish'),([100]*60,'mixed')):
            f=self.features(bars(prices))
            self.assertEqual(f.ema_structure.iloc[-1],expected)
            self.assertTrue(f.ema_structure.iloc[:49].isna().all())

    def test_anti_lookahead_every_predictor(self):
        original=bars(100+np.arange(250)*.2)
        changed=original.copy()
        changed.loc[221:,['open','high','low','close']]*=7
        a,b=self.features(original),self.features(changed)
        pd.testing.assert_frame_equal(a.iloc[:221],b.iloc[:221])
        pd.testing.assert_frame_equal(a.iloc[:221],self.features(original.iloc[:221]))
        self.assertNotEqual(forward_outcomes(original,CUTOFF).future_return_1s.iloc[220],
                            forward_outcomes(changed,CUTOFF).future_return_1s.iloc[220])
        self.assertFalse(any(c.startswith('future_') for c in a))

    def test_forward_returns_and_tail_unavailable(self):
        f=forward_outcomes(bars(range(100,125)),CUTOFF)
        for h in HORIZONS:
            self.assertAlmostEqual(f[f'future_return_{h}s'].iloc[0],(100+h)/100-1)
            cols=[c for c in f if c.endswith(f'_{h}s')]
            self.assertTrue(f[cols].iloc[-h:].isna().all().all())
            self.assertTrue(f[cols].iloc[:-h].notna().all().all())

    def test_excursions_exclude_signal_bar(self):
        t=bars([100,102,98,103,99,101])
        t.loc[0,['high','low']]=[1000,1]
        f=forward_outcomes(t,CUTOFF)
        self.assertAlmostEqual(f.future_high_excursion_1s.iloc[0],.03)
        self.assertAlmostEqual(f.future_low_excursion_1s.iloc[0],.01)
        self.assertAlmostEqual(f.future_high_excursion_3s.iloc[0],.04)
        self.assertAlmostEqual(f.future_low_excursion_3s.iloc[0],-.03)
        self.assertTrue(f.filter(like='_10s').isna().all().all())

    def test_negative_high_excursion_is_not_clipped(self):
        f=forward_outcomes(bars([100,95]),CUTOFF)
        self.assertAlmostEqual(f.future_high_excursion_1s.iloc[0],-.04)

    def test_dates_invalid_duplicate_unsorted(self):
        for dates in (['bad','2020-01-03'],['2020-01-02']*2,['2020-01-03','2020-01-02'],[1,2]):
            t=bars([100,101]);t['date']=dates
            with self.subTest(dates=dates),self.assertRaises(ValueError):
                self.features(t)

    def test_invalid_ohlc(self):
        for col,value in (('close',np.nan),('open',0),('low',-1),('high',99),('low',102),('close',np.inf),('open','bad')):
            t=bars([100,101]).astype({'open':object})
            t.loc[0,col]=value
            with self.subTest(col=col,value=value),self.assertRaises(ValueError):
                self.features(t)

    def test_missing_sessions_audited_without_filling(self):
        original=bars(range(100,125))
        t=original.drop(index=5)
        clean,audit=validate_ohlc(t,CUTOFF)
        self.assertEqual(len(clean),24)
        self.assertIn(str(original.date.iloc[5].date()),audit['possible_missing_weekdays'])
        with self.assertRaises(ValueError):
            validate_ohlc(t,CUTOFF,original.date)
        _,audit=validate_ohlc(original,CUTOFF,original.date)
        self.assertTrue(audit['calendar_verified'])

    def test_completion_cutoff_and_short_history(self):
        t=bars([100,101,102])
        f=market_state_features(t,t.date.iloc[-1])
        self.assertEqual(len(f),2)
        self.assertTrue(f.ema_200.isna().all())
        self.assertTrue(f.rsi_14.isna().all())
        with self.assertRaises(ValueError):
            market_state_features(t,t.date.iloc[0])

    def test_exports_separate_labels_and_metadata(self):
        dataset=build_research_dataset(bars(range(100,125)),CUTOFF,dict(source='test fixture'))
        f=pd.read_csv(io.StringIO(export_csv(dataset,'features')))
        o=pd.read_csv(io.StringIO(export_csv(dataset,'outcomes')))
        self.assertFalse(any(c.startswith('future_') for c in f))
        self.assertNotIn('ema_9',o)
        meta=json.loads(f.metadata_json.iloc[0])
        self.assertEqual(meta['symbol'],'SPY')
        self.assertIn('feature_conventions',meta)
        self.assertIn('source_ohlc_sha256',meta)

    def test_provider_integration_spy_qqq(self):
        with patch('modules.public_data.get_public_research_bars',return_value=bars(range(100,125)).drop(columns='symbol')) as provider:
            for symbol in ('SPY','QQQ'):
                for period in ('FIVE_YEARS','TEN_YEARS'):
                    result=load_market_state(symbol,period)
                    self.assertEqual(result['metadata']['symbol'],symbol)
                    provider.assert_called_with(symbol,period)

    def test_bad_symbol_or_period(self):
        for symbol,period in (('IWM','FIVE_YEARS'),('SPY','MAX')):
            with self.assertRaises(ValueError):
                load_market_state(symbol,period)


if __name__=='__main__':
    unittest.main()
