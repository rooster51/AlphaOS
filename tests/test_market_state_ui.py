from pathlib import Path
import unittest
from unittest.mock import patch
import pandas as pd
from streamlit.testing.v1 import AppTest

from modules.market_state_research import build_research_dataset


def fixture(symbol):
    return build_research_dataset(pd.DataFrame(dict(date=pd.bdate_range('2020-01-02',periods=220),
        symbol=symbol,open=100.,high=101.,low=99.,close=100.)), '2030-01-01',
        dict(source='unit test fixture',requested_period='FIVE_YEARS'))


class MarketStateUITests(unittest.TestCase):
    def app(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'streamlit_app.py'),default_timeout=60).run()
        return app.switch_page('pages/8_Quant_Lab.py').run()

    def test_spy_and_qqq_ui_and_exports(self):
        app=self.app()
        for symbol in ('SPY','QQQ'):
            next(s for s in app.selectbox if s.label=='Market-state symbol').set_value(symbol)
            with patch('modules.market_state_workspace.load_market_state',return_value=fixture(symbol)) as loader:
                next(b for b in app.button if b.label=='Generate market-state dataset').click().run()
                loader.assert_called_once_with(symbol,'FIVE_YEARS')
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['market_state_result']['metadata']['symbol'],symbol)
            self.assertIn('FEATURES AVAILABLE AT TIME T',[t.label for t in app.tabs])
            self.assertIn('FUTURE OUTCOMES — RESEARCH ONLY',[t.label for t in app.tabs])
            self.assertEqual(next(m.value for m in app.metric if m.label=='Close'),'$100.00')

    def test_ten_years_and_failed_refresh_clears_stale_result(self):
        app=self.app()
        next(s for s in app.selectbox if s.label=='Market-state history').set_value('TEN_YEARS')
        with patch('modules.market_state_workspace.load_market_state',return_value=fixture('SPY')) as loader:
            next(b for b in app.button if b.label=='Generate market-state dataset').click().run()
            loader.assert_called_once_with('SPY','TEN_YEARS')
        with patch('modules.market_state_workspace.load_market_state',side_effect=ValueError('Missing daily data')):
            next(b for b in app.button if b.label=='Generate market-state dataset').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        self.assertNotIn('market_state_result',app.session_state)

    def test_pulse_research_execution_preserved(self):
        times=[day+pd.Timedelta(hours=9,minutes=30+30*i)
               for day in pd.bdate_range('2024-01-02',periods=4) for i in range(13)]
        bars=pd.DataFrame(dict(timestamp=times,open=100.,high=101.,low=99.,close=100.))
        app=self.app()
        with patch('modules.alpaca_data.has_alpaca_config',return_value=True), \
             patch('modules.alpaca_data.get_alpaca_intraday_bars',return_value=(bars,'test fixture')):
            next(b for b in app.button if b.label=='Run Pulse Backtest').click().run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertIn('Strategy Rollup',[h.value for h in app.subheader])


if __name__=='__main__':
    unittest.main()
