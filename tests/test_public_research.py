import unittest
from datetime import date
import numpy as np
import pandas as pd
from modules.public_research import align_daily_histories


class PublicHistoryTests(unittest.TestCase):
    def bars(self, start='2024-01-01', periods=120, freq='B'):
        return pd.DataFrame({'date':pd.date_range(start,periods=periods,freq=freq), 'close':100+np.arange(periods)})

    def test_intersection_no_fill(self):
        a = self.bars()
        b = a.iloc[5:].copy()
        p,audit = align_daily_histories({'A':a,'B':b},date(2025,1,1))
        self.assertEqual(len(p),115)
        self.assertEqual(audit[0]['Excluded during alignment'],5)

    def test_excludes_current_day(self):
        a = self.bars()
        p,_ = align_daily_histories({'A':a},a.date.iloc[-1].date())
        self.assertEqual(len(p),119)

    def test_rejects_duplicate_dates_and_sparse_data(self):
        a = self.bars()
        with self.assertRaises(ValueError):
            align_daily_histories({'A':pd.concat([a,a.iloc[:1]])},date(2030,1,1))
        with self.assertRaises(ValueError):
            align_daily_histories({'A':self.bars(freq='MS')},date(2040,1,1))

    def test_rejects_invalid_close(self):
        a = self.bars()
        a.loc[10,'close'] = np.nan
        with self.assertRaises(ValueError):
            align_daily_histories({'A':a},date(2030,1,1))
