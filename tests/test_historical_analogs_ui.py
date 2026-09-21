from pathlib import Path
import unittest
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from modules.market_state_research import build_research_dataset


def dataset(symbol='SPY'):
    prices=100+np.arange(230)*.02+np.sin(np.arange(230)/5)
    frame=pd.DataFrame(dict(date=pd.bdate_range('2020-01-02',periods=len(prices)),symbol=symbol,
        open=prices,high=prices+1,low=prices-1,close=prices))
    return build_research_dataset(frame,'2030-01-01',dict(source='deterministic UI fixture',requested_period='FIVE_YEARS'))


class HistoricalAnalogUITests(unittest.TestCase):
    def app(self, data=None):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'streamlit_app.py'),default_timeout=60).run()
        if data is not None:
            app.session_state['market_state_result']=data
        return app.switch_page('pages/8_Quant_Lab.py').run()

    def run_analogs(self,app):
        next(b for b in app.button if b.label=='Find historical analogs').click().run()
        self.assertFalse(app.exception)
        return app.session_state['historical_analog_result']

    def test_requires_phase_two_dataset(self):
        app=self.app()
        self.assertFalse(app.exception)
        self.assertIn('Historical Analogs',[t.label for t in app.tabs])
        self.assertTrue(any('Generate a SPY or QQQ dataset' in i.value for i in app.info))

    def test_latest_tolerance_charts_funnel_and_sensitivity(self):
        data=dataset()
        app=self.app(data)
        r=self.run_analogs(app)
        self.assertEqual(r['target'].date,data['features'].date.iloc[-1])
        self.assertEqual(r['config']['method'],'tolerance')
        self.assertEqual(len(r['sensitivity']),15)
        for label in ('Observed outcomes','Matching transparency','Tolerance sensitivity','All analog observations'):
            self.assertIn(label,[t.label for t in app.tabs])
        self.assertGreaterEqual(len(app.get('plotly_chart')),2)
        self.assertTrue(any('Historically,' in m.value for m in app.markdown))
        self.assertTrue(any('Export historical analogs' in str(d.proto) for d in app.get('download_button')))

    def test_historical_nearest_mode_and_horizon(self):
        data=dataset('QQQ')
        app=self.app(data)
        next(s for s in app.selectbox if s.label=='Analog target mode').set_value('HISTORICAL TARGET DATE')
        date=data['features'].date.iloc[150]
        next(s for s in app.selectbox if s.label=='Historical target date').set_value(date)
        next(s for s in app.selectbox if s.label=='Analog method').set_value('Standardized nearest neighbors')
        next(s for s in app.selectbox if s.label=='Closest N analogs').set_value(25)
        next(s for s in app.selectbox if s.label=='Research horizon (observed sessions)').set_value(5)
        r=self.run_analogs(app)
        self.assertEqual(r['target'].date,date)
        self.assertEqual(len(r['analogs']),25)
        self.assertTrue((r['matches'].date<=data['features'].date.iloc[145]).all())
        self.assertEqual(next(m.value for m in app.metric if m.label=='Final analog sample'),'25')
        next(s for s in app.selectbox if s.label=='Distribution horizon').set_value(10).run()
        self.assertFalse(app.exception)
        self.assertTrue(any('10-session valid outcomes' in c.value for c in app.caption))

    def test_manual_tolerances_are_used_without_auto_widening(self):
        app=self.app(dataset())
        for n in app.number_input:
            if 'tolerance' in n.label:
                n.set_value(0.)
        r=self.run_analogs(app)
        self.assertEqual(set(r['config']['tolerances'].values()),{0.})
        self.assertEqual(len(r['matches']),0)
        self.assertTrue(any('No valid outcomes' in i.value for i in app.info))

    def test_new_dataset_hides_previous_results(self):
        app=self.app(dataset('SPY'))
        self.run_analogs(app)
        app.session_state['market_state_result']=dataset('QQQ')
        app.run()
        self.assertFalse(app.exception)
        self.assertNotIn('Final analog sample',[m.label for m in app.metric])

    def test_warmup_error_clears_previous_result(self):
        data=dataset()
        app=self.app(data)
        self.run_analogs(app)
        next(s for s in app.selectbox if s.label=='Analog target mode').set_value('HISTORICAL TARGET DATE')
        next(s for s in app.selectbox if s.label=='Historical target date').set_value(data['features'].date.iloc[0])
        next(b for b in app.button if b.label=='Find historical analogs').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        self.assertNotIn('historical_analog_result',app.session_state)


if __name__=='__main__':
    unittest.main()
